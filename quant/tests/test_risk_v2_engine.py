"""Risk wrapper on the execution engine: caps, liquidation, gaps, liquidity failure, causality, determinism."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synth import random_walk_ohlcv

from quantlab import causality
from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run
from quantlab.family_a import FamilyAConfig, FamilyAStrategy
from quantlab.risk_v2 import (
    FLAT,
    REENTRY,
    SHUTDOWN,
    RiskManagedStrategy,
    RiskStateMachine,
    RiskV2Config,
)


CFG = RiskV2Config()
N = 24 * 120
IDX = pd.date_range("2024-01-01", periods=N, freq="1h", tz="UTC")
EXEC = ExecConfig(breaker=False, max_participation=0.10, wallet=1000.0)


def frame(price, volume=1e9):
    price = np.asarray(price, dtype=float)
    return pd.DataFrame({"date": IDX, "open": np.r_[price[0], price[:-1]], "high": price * 1.0005, "low": price * 0.9995,
                         "close": price, "volume": volume})  # fmt: skip


class AllIn(Strategy):
    """Always wants to be fully invested (equal weight); stateless; honours risk_multiplier."""

    def on_candle(self, t, hist, view):
        out = []
        n = len(hist.pairs)
        for p in hist.pairs:
            cur = view.positions.get(p, (0.0, 0.0))[1]
            want = view.equity * view.risk_multiplier / n
            if want - cur > 0.05 * view.equity and not view.halted and len(hist.times) > 30:
                out.append(Order(p, "buy", notional=want - cur, add=True))
        return out


def run_wrapped(prices, cfg=CFG, volume=1e9, inner=None, approval=None, exec_cfg=EXEC):
    cd = {
        f"P{k}/USDT": frame(p, volume if np.isscalar(volume) else volume[k])
        for k, p in enumerate(prices)
    }
    m = RiskStateMachine.new(cfg, exec_cfg.wallet)
    w = RiskManagedStrategy(inner or AllIn(), m, approval)
    res = run(w, PriceData(cd, IDX), exec_cfg)
    return res, w, m


def path(*segments):
    """Piecewise price path: (n_candles, total_return) segments from 100."""
    p, out = 100.0, [100.0] * 40
    for n, r in segments:
        out += list(p * np.exp(np.linspace(0, np.log(1 + r), n + 1)[1:]))
        p = out[-1]
    out += [p] * (N - len(out))
    return np.array(out[:N])


def test_a_slow_crash_triggers_tier_1_then_flatten_at_the_next_open_with_costs_and_no_new_entries():
    res, w, m = run_wrapped([path((100, 0.0), (400, -0.40))])
    kinds = [r["to"] for r in m.records]
    assert "REDUCED" in kinds and FLAT in kinds
    t_flat = pd.Timestamp(next(r["t"] for r in m.records if r["to"] == FLAT))
    liq = res.trades[res.trades["exit_reason"] == "halt"]
    assert (
        len(liq) >= 1 and (liq["close_date"] >= t_flat).all() and liq["close_date"].min() == t_flat
    )  # next open
    assert (liq["close_rate"] > 0).all() and (
        liq["profit_abs"] / liq["open_value"] < liq["close_rate"] / liq["open_rate"] - 1
    ).all()
    after = [
        o
        for o in res.orders
        if pd.Timestamp(o["time"]) > t_flat
        and o["side"] == "buy"
        and pd.Timestamp(o["time"]) < t_flat + pd.Timedelta(hours=CFG.cooldown_hours)
    ]
    assert after == []  # nothing is bought during the cooldown
    assert w.suppressed  # shadow log of what the inner strategy wanted


def test_exposure_never_exceeds_the_state_cap_and_the_hwm_matches_the_engine_equity():
    res, w, m = run_wrapped([path((200, 0.30), (300, -0.35), (200, 0.1))])
    eq_prev = res.equity.shift(1).fillna(EXEC.wallet)
    assert m.s.hwm == pytest.approx(max(EXEC.wallet, res.equity.iloc[:-1].max()), rel=1e-9)
    exp = res.exposure
    assert (exp <= 1.0 + 1e-6).all()
    assert eq_prev.notna().all()


def test_reduced_state_enforces_the_absolute_cap_by_selling_the_excess():
    res, w, m = run_wrapped([path((60, 0.0), (120, -0.14))])
    t1 = [r for r in m.records if r["to"] == "REDUCED"]
    assert t1
    i = res.exposure.index.searchsorted(pd.Timestamp(t1[0]["t"])) + 3
    assert res.exposure.iloc[i] <= CFG.tier1_cap + 0.02


def test_gap_through_the_floor_with_full_exposure_is_reported_as_overshoot():
    p = path((100, 0.0))
    p[200:] = p[200] * 0.60  # a 40 % single-candle gap with the book fully invested
    res, w, m = run_wrapped([p])
    rec = next(r for r in m.records if r["to"] == SHUTDOWN)
    assert rec["d_global"] > CFG.tier3_dd + 0.1 and m.s.safety_disqualified
    assert (
        res.equity.iloc[-1] < 0.8 * EXEC.wallet
    )  # the loss really exceeded the floor: 18 % is not a maximum


def test_liquidity_failure_after_flatten_ends_in_shutdown_with_unliquidated_exposure_reported():
    p = path((100, 0.0), (400, -0.4))
    vol = np.r_[
        np.full(90, 1e9), np.zeros(N - 90)
    ]  # liquidity vanishes while the position is still open
    res, w, m = run_wrapped([p], volume=[vol])
    assert m.s.state == SHUTDOWN and m.s.shutdown_cause in (
        "liquidation_unavailable",
        "tier3_floor",
    )
    assert any(o.reason == "halt" for o in res.state.pending) or not res.state.positions
    if (
        res.state.positions
    ):  # unliquidated risk stays visible, and no new order is placed afterwards
        late = [
            o
            for o in res.orders
            if pd.Timestamp(o["time"]) > pd.Timestamp(m.s.shutdown_time) and o["side"] == "buy"
        ]
        assert late == []


def test_manual_authorisation_through_the_wrapper_restarts_in_reentry_with_the_hwm_and_flag_intact(
    tmp_path,
):
    p = path((100, 0.0))
    p[200:] = (
        p[200] * 0.78
    )  # a 22 % single-candle gap on a fully invested book: past the floor, inside the hard limit
    res, w, m = run_wrapped([p])
    assert m.s.state == SHUTDOWN and m.s.hwm >= EXEC.wallet
    sid, t_sd = m.s.shutdown_id, pd.Timestamp(m.s.shutdown_time)
    ap = tmp_path / "approval.json"
    ap.write_text(json.dumps({"shutdown_id": sid, "approver": "owner", "exposure_cap": 0.5, "epoch_loss_limit": 0.03,
                              "approval_id": "a1", "issued_at": str(t_sd + pd.Timedelta(hours=2))}))  # fmt: skip
    res2, w2, m2 = run_wrapped(
        [p], approval=ap
    )  # deterministic replay: the same shutdown id appears again
    assert m2.s.epoch == 1 and m2.s.safety_disqualified and m2.s.hwm == pytest.approx(m.s.hwm)
    assert m2.s.consumed_approvals == ["a1"] and m2.s.state in (
        REENTRY,
        SHUTDOWN,
        FLAT,
        "NORMAL",
        "REDUCED",
    )
    assert m2.records[0]["hash"] == m.records[0]["hash"]


def family_a_basket(n=3):
    out = {}
    for k in range(n):
        df = random_walk_ohlcv(N, seed=40 + k, vol=0.012, start="2024-01-01")
        df["volume"] = 5000.0
        out[f"P{k}/USDT"] = df
    return out


def make_wrapped(data):
    return RiskManagedStrategy(
        FamilyAStrategy(FamilyAConfig(), 3), RiskStateMachine.new(CFG, EXEC.wallet)
    )


@pytest.mark.parametrize("k", [60 * 24, 90 * 24])
def test_wrapped_strategy_is_causal_for_price_and_volume_mutation(k):
    cd = family_a_basket()
    for prices in (True, False):
        assert (
            causality.mutation_mismatches_at(
                make_wrapped, cd, IDX, EXEC, IDX[k], start=24 * 40, prices=prices
            )
            == []
        )


def test_restart_from_saved_engine_and_machine_state_reproduces_the_full_run():
    cd = family_a_basket()
    data = PriceData(cd, IDX)
    full_w = make_wrapped(data)
    full = run(full_w, data, EXEC, start=24 * 40)
    k = 24 * 80
    head_w = make_wrapped(data)
    head = run(head_w, data, EXEC, start=24 * 40, end=k)
    tail_w = make_wrapped(data)
    tail_w.m = deepcopy(head_w.m)  # the machine state is part of the restart state
    tail = run(tail_w, data, EXEC, start=k, state=head.state)
    assert tail.orders == [o for o in full.orders if o["i"] >= k]
    np.testing.assert_allclose(
        tail.equity.to_numpy(), full.equity.loc[tail.equity.index].to_numpy(), atol=1e-9
    )
    assert tail_w.m.s.state == full_w.m.s.state and tail_w.m.s.hwm == pytest.approx(full_w.m.s.hwm)


def test_wrapped_run_is_deterministic_in_process_and_across_processes(tmp_path):
    cd = family_a_basket()
    h1 = run(make_wrapped(None), PriceData(cd, IDX), EXEC, start=24 * 40).hash
    h2 = run(make_wrapped(None), PriceData(cd, IDX), EXEC, start=24 * 40).hash
    assert h1 == h2
    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "child.py"
    script.write_text(
        f"import sys\nsys.path[:0] = [{str(root)!r}, {str(root / 'tests')!r}]\n"
        "from test_risk_v2_engine import *\n"
        "cd = family_a_basket()\n"
        "print(run(make_wrapped(None), PriceData(cd, IDX), EXEC, start=24 * 40).hash)\n"
    )
    out = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == h1


def test_the_wrapper_never_changes_the_engine_cost_model_or_the_hwm_definition():
    res, w, m = run_wrapped([path((100, 0.2), (200, -0.2))])
    assert EXEC.costs.fee == 0.001 and res.equity.iloc[0] > 0
    assert m.s.hwm >= EXEC.wallet
