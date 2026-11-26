"""Risk layer V3 on synthetic fixtures: elapsed-time stale detection, separated clocks, explicit statuses,
no assumed liquidation, three valuations, recovery sensitivity, concealment, S2 equivalence, determinism."""

from __future__ import annotations

import json
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantlab import risk_v3 as r3
from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run
from quantlab.risk_v2 import RiskManagedStrategy, RiskStateMachine, RiskV2Config
from quantlab.risk_v3 import ConfigError, RiskManagedStrategyV3, RiskV3Config, ScheduleFeed, Status


CFG = ExecConfig(wallet=1000.0)
H = pd.Timedelta(hours=1)
Q = Path(__file__).resolve().parents[1]


def data(n=400, stops=None, step="1h", seed=None, vol=0.0, pairs=("X/USDT", "Y/USDT"), resume=None):
    idx = pd.date_range("2022-01-01", periods=n, freq=step, tz="UTC")
    out = {}
    for k, p in enumerate(pairs):
        rng = np.random.default_rng((seed or 0) * 10 + k)
        c = 100.0 * np.exp(np.cumsum(rng.normal(0, vol, n))) if vol else np.full(n, 100.0)
        o = np.concatenate([[100.0], c[:-1]])
        df = pd.DataFrame(
            {
                "date": idx,
                "open": o,
                "high": np.maximum(o, c),
                "low": np.minimum(o, c),
                "close": c,
                "volume": 1e9,
            }
        )
        stop = (stops or {}).get(p)
        if stop is not None:
            df = df.drop(df.index[stop : (resume or {}).get(p, n)])
        out[p] = df
    return PriceData(out, idx)


class HoldBoth(Strategy):
    def __init__(self, pairs=("X/USDT", "Y/USDT"), notional=300.0):
        self.pairs, self.notional, self.calls = pairs, notional, []

    def on_candle(self, t, hist, view):
        self.calls.append(t)
        return [
            Order(p, "buy", notional=self.notional) for p in self.pairs if p not in view.positions
        ]


def v3(d, inner=None, cfg=None, feed=None, **kw):
    cfg = cfg or RiskV3Config()
    machine = RiskStateMachine.new(cfg.v2, 1000.0)
    strat = RiskManagedStrategyV3(inner or HoldBoth(), machine, cfg, feed, **kw)
    return strat, machine, run(strat, d, CFG)


def v2(d, inner=None):
    machine = RiskStateMachine.new(RiskV2Config(), 1000.0)
    return machine, run(RiskManagedStrategy(inner or HoldBoth(), machine), d, CFG)


def first_shutdown(machine):
    return next((r for r in machine.records if r["to"] == "SHUTDOWN"), None)


# ------------------------------------------------------------------ R1 elapsed time, R2 clocks
def test_stale_alarm_fires_after_48_elapsed_hours_hourly_and_matches_v2():
    d = data(stops={"X/USDT": 100})
    _s, m3, _r = v3(d)
    m2, _ = v2(d)
    a3, a2 = first_shutdown(m3), first_shutdown(m2)
    assert a3 and a2 and a3["t"] == a2["t"] and a3["cause"] == "integrity"
    delay = (pd.Timestamp(a3["t"]) - d.index[100]) / H
    assert 47 <= delay <= 50


def test_elapsed_time_not_candle_count_with_a_matching_monitor_interval():
    four = pd.Timedelta(hours=4)
    d = data(n=200, step="4h", stops={"X/USDT": 40})
    cfg = RiskV3Config(monitor_interval=four)
    _s, m, _ = v3(d, cfg=cfg)
    a = first_shutdown(m)
    delay_h = (pd.Timestamp(a["t"]) - d.index[40]) / H
    assert 48 <= delay_h <= 52  # 48 elapsed hours, i.e. 12 candles of 4 h, not 48 candles


def test_default_monitoring_refuses_coarser_cadence_and_daily_decisions_run_on_hourly_monitoring():
    with pytest.raises(ConfigError):
        v3(data(n=60, step="1D"))
    with pytest.raises(ConfigError):
        v3(data(n=60, step="4h"))
    inner = HoldBoth()
    d = data(n=24 * 10)
    s, m, _ = v3(d, inner=inner, decision_every=pd.Timedelta(days=1))
    assert len(inner.calls) == 10 and all(
        t.hour == 0 for t in inner.calls
    )  # strategy decides daily
    assert len(s.ticks) == 24 * 10  # risk is evaluated every hour
    a = v3(data(n=24 * 20, stops={"X/USDT": 24 * 3}), decision_every=pd.Timedelta(days=1))[1]
    assert first_shutdown(a) is not None
    delay = (pd.Timestamp(first_shutdown(a)["t"]) - pd.Timestamp("2022-01-04", tz="UTC")) / H
    assert 47 <= delay <= 50  # a daily strategy is protected within 48 HOURS (S2 needed 48 days)


# ------------------------------------------------------------------ R3 statuses
def test_explicit_statuses_alarm_immediately_and_recovery_before_the_horizon_is_tolerated():
    d = data(n=300)
    t0 = d.index[100]
    for st in (Status.SUSPENDED, Status.DELISTED, Status.UNTRADEABLE):
        s, m, _ = v3(d, feed=ScheduleFeed({"X/USDT": [(t0, st)]}))
        a = first_shutdown(m)
        assert a and pd.Timestamp(a["t"]) == t0 and a["cause"] == "integrity", st
        assert next(x for x in s.ticks if x["t"] == t0)["impaired"] == ["X/USDT"], st
    # silent for 30 h then back: no alarm, no shutdown
    gap = data(n=300, stops={"X/USDT": 100}, resume={"X/USDT": 130})
    _s, m, _ = v3(gap)
    assert first_shutdown(m) is None
    # silent beyond the horizon, then resumes: the shutdown stays permanent
    late = data(n=400, stops={"X/USDT": 100}, resume={"X/USDT": 200})
    _s, m, _ = v3(late)
    assert first_shutdown(m) is not None and m.s.state == "SHUTDOWN" and m.s.safety_disqualified


def test_missing_history_is_impaired():
    s = RiskManagedStrategyV3(HoldBoth(), RiskStateMachine.new(RiskV2Config(), 1000.0))
    s.tracker.last_seen["Z/USDT"] = None
    assert s.classify("Z/USDT", pd.Timestamp("2022-01-02", tz="UTC")) == Status.MISSING
    assert (
        Status.MISSING in r3.IMPAIRED
        and Status.TRADABLE not in r3.IMPAIRED
        and Status.GAP not in r3.IMPAIRED
    )


# ------------------------------------------------------------------ R4 never assume liquidation
def test_impaired_position_stays_in_the_book_and_the_machine_never_looks_flat():
    d = data(n=500, stops={"X/USDT": 100})
    s, m, res = v3(d)
    assert "X/USDT" in res.state.positions and "Y/USDT" not in res.state.positions
    assert s.unliquidatable == {"X/USDT"}
    assert {r["to"] for r in m.records} <= {"SHUTDOWN"} and m.s.state == "SHUTDOWN"
    assert not [
        o
        for o in res.orders
        if o["side"] == "buy" and pd.Timestamp(o["time"]) > pd.Timestamp(first_shutdown(m)["t"])
    ]


def test_tier2_flatten_with_a_stuck_asset_ends_in_shutdown_not_in_a_recovered_state():
    n = 600
    idx = pd.date_range("2022-01-01", periods=n, freq="1h", tz="UTC")
    fall = np.full(n, 100.0)
    fall[60:] = 100.0 * np.exp(
        -0.002 * np.arange(1, n - 59)
    )  # Y falls steadily: tier 2 within a few days
    out = {}
    for p, c in (("X/USDT", np.full(n, 100.0)), ("Y/USDT", fall)):
        o = np.concatenate([[100.0], c[:-1]])
        df = pd.DataFrame(
            {
                "date": idx,
                "open": o,
                "high": np.maximum(o, c),
                "low": np.minimum(o, c),
                "close": c,
                "volume": 1e9,
            }
        )
        out[p] = df.drop(df.index[200:]) if p == "X/USDT" else df  # X silent from candle 200
    big = HoldBoth(notional=450.0)
    _s, m, _ = v3(PriceData(out, idx), inner=big)
    states = {r["to"] for r in m.records}
    assert "SHUTDOWN" in states and not states & {"NORMAL", "REENTRY"}


# ------------------------------------------------------------------ R5 valuations, R6 sensitivity, R7 concealment
@pytest.mark.parametrize("r", [0.0, 0.5, 1.0])
def test_three_valuations_are_separate_and_closed_form(r):
    cfg = RiskV3Config(gate_recovery=r)
    d = data(n=300)
    t0 = d.index[100]
    s, _m, res = v3(d, cfg=cfg, feed=ScheduleFeed({"X/USDT": [(t0, Status.DELISTED)]}))
    tk = next(x for x in s.ticks if x["t"] == t0)
    assert tk["impaired"] == ["X/USDT"] and tk["impaired_lk"] > 250
    assert tk["cons"] == pytest.approx(tk["lk"] - tk["impaired_lk"] * (1 - r), rel=1e-12)
    wo = s.writeoffs["X/USDT"]
    assert wo["realized_loss"] == pytest.approx(wo["last_known"] * (1 - r)) and wo["recovery"] == r
    assert s.realized_losses(res.trades)["write_offs"] == pytest.approx(wo["realized_loss"])
    assert all(x["cons"] <= x["lk"] + 1e-9 for x in s.ticks)


def test_recovery_sensitivity_is_monotone_and_hits_both_ends():
    lk = [1000, 1010, 1020, 1015, 1012, 1010]
    imp = [0, 0, 0, 300, 300, 300]
    ticks = [{"lk": a, "cons": a - b, "impaired_lk": b} for a, b in zip(lk, imp, strict=True)]
    s = r3.recovery_sensitivity(ticks)
    dds = [s[str(r)]["max_drawdown"] for r in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert all(a >= b for a, b in pairwise(dds))
    assert dds[-1] == pytest.approx(r3._max_dd(np.array(lk, float)))
    assert dds[0] == pytest.approx(
        r3._max_dd(np.array([a - b for a, b in zip(lk, imp, strict=True)], float))
    )
    assert s["0.0"]["trips"]["t4_limit_exceeded"] and not s["1.0"]["trips"]["t4_limit_exceeded"]
    assert s["0.5"]["final_equity"] == pytest.approx(1010 - 150)


def test_stale_valuation_cannot_conceal_a_breach_of_the_drawdown_limit():
    d = data(n=300)
    t0 = d.index[100]
    s, m, _ = v3(d, feed=ScheduleFeed({"X/USDT": [(t0, Status.SUSPENDED)]}))
    rep = r3.capital_protection_report(s.ticks)
    assert (
        rep["last_known_view_passes"]
        and not rep["conservative_view_passes"]
        and rep["concealed_by_stale_valuation"]
    )
    assert (
        rep["verdict_pass"] is False
        and rep["max_drawdown_last_known"] < 0.05
        and rep["max_drawdown_conservative"] > 0.2
    )
    a = first_shutdown(m)
    assert (
        pd.Timestamp(a["t"]) == t0 and "floor" in a["conditions"]
    )  # tripped at once on the conservative equity
    m2, _ = v2(d)  # the frozen S2 layer does not see it (no stale alarm for 48 h, equity unchanged)
    a2 = first_shutdown(m2)
    assert a2 is None
    clean = r3.capital_protection_report(v3(d)[0].ticks)
    assert clean["verdict_pass"] and not clean["concealed_by_stale_valuation"]


# ------------------------------------------------------------------ R8-R10 S2 preserved, thresholds, determinism
def test_no_threshold_changed_and_v3_requires_the_unchanged_s2_config():
    c = RiskV3Config()
    assert c.v2 == RiskV2Config()
    v = c.v2
    assert (v.tier1_dd, v.tier2_dd, v.tier3_dd, v.hard_dd) == (0.10, 0.15, 0.18, 0.25)
    assert (v.data_gap_candles, v.liquidity_alarm_candles, v.cooldown_hours) == (48, 24, 336)
    assert c.stale_horizon == pd.Timedelta(hours=48) and c.gate_recovery == 0.0
    with pytest.raises(ConfigError):
        RiskManagedStrategyV3(
            HoldBoth(), RiskStateMachine.new(RiskV2Config(tier3_dd=0.2), 1000.0), c
        )
    with pytest.raises(ConfigError):
        RiskV3Config(gate_recovery=1.5)


@pytest.mark.parametrize("seed", range(6))
def test_without_impairment_v3_is_identical_to_the_v2_wrapper(seed):
    d = data(n=1500, seed=seed + 1, vol=0.02)  # volatile: tiers 1/2/3 and re-entries get exercised
    _s, m3, r3_ = v3(d)
    m2, r2_ = v2(d)
    assert r3_.hash == r2_.hash
    strip = lambda recs: [{k: v for k, v in r.items() if k != "hash"} for r in recs]  # noqa: E731
    assert strip(m3.records) == strip(m2.records) and len(m2.records) > 0


def test_spec_file_matches_the_code():
    spec = json.loads((Q / "protocol/risk_v3_spec.json").read_text(encoding="utf-8"))
    assert (
        spec["version"] == r3.VERSION == "3.0.0"
        and spec["config_sha256"] == RiskV3Config().sha256()
    )
    assert spec["v2_config_unchanged"] is True


def test_deterministic_across_processes_and_tracker_rebuild_equals_incremental(tmp_path):
    script = tmp_path / "run.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(Q)!r}); sys.path.insert(0, {str(Q / 'tests')!r})\n"
        "from test_risk_v3 import data, v3\n"
        "s, m, r = v3(data(n=600, seed=3, vol=0.02, stops={'X/USDT': 300}))\n"
        "print(r.hash)\n",
        encoding="utf-8",
    )
    hs = [
        subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, check=True
        ).stdout.strip()
        for _ in range(2)
    ]
    assert hs[0] == hs[1] and len(hs[0]) == 64
    d = data(n=300, stops={"X/USDT": 100})
    s, _m, _res = v3(d)
    from quantlab.execution import History

    hist = History(d, len(d.index) - 1)
    rebuilt = r3.StaleTracker.from_history(["X/USDT"], hist, H)
    assert rebuilt.last_seen["X/USDT"] == s.tracker.last_seen["X/USDT"]


# ------------------------------------------------------------------ R11 property tests
@pytest.mark.parametrize("seed", range(30))
def test_invariants_on_random_scenarios(seed):
    rnd = np.random.default_rng(seed)
    n = int(rnd.integers(300, 700))
    stops = {"X/USDT": int(rnd.integers(50, n - 100))} if rnd.random() < 0.7 else {}
    resume = (
        {"X/USDT": stops["X/USDT"] + int(rnd.integers(5, 120))}
        if stops and rnd.random() < 0.4
        else None
    )
    d = data(
        n=n, seed=seed + 100, vol=float(rnd.choice([0.0, 0.005, 0.02])), stops=stops, resume=resume
    )
    feed = (
        ScheduleFeed({"Y/USDT": [(d.index[int(rnd.integers(80, n - 50))], Status.SUSPENDED)]})
        if rnd.random() < 0.3
        else None
    )
    r = float(rnd.choice([0.0, 0.5]))
    s, m, res = v3(d, cfg=RiskV3Config(gate_recovery=r), feed=feed)
    assert all(x["cons"] <= x["lk"] + 1e-9 for x in s.ticks)
    assert all(abs(x["cons"] - (x["lk"] - x["impaired_lk"] * (1 - r))) < 1e-9 for x in s.ticks)
    hwm = [rec["hwm"] for rec in m.records]
    assert hwm == sorted(hwm)
    sh = first_shutdown(m)
    if sh is not None:
        assert not [
            o
            for o in res.orders
            if o["side"] == "buy" and pd.Timestamp(o["time"]) > pd.Timestamp(sh["t"])
        ]
        assert m.s.state == "SHUTDOWN" and m.s.safety_disqualified
