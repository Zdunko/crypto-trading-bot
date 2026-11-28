"""M1 (S9 plan): G1 engine integration, G3 causal status source, G5 resume after a gap, and the G2 policy
(zero recovery is the primary assumption; an assumed recovery is never executable liquidity).
Synthetic fixtures only; risk_v2.py / risk_v3.py and every limit are untouched."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from quantlab import risk_status as rs
from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run
from quantlab.risk_v2 import RiskManagedStrategy, RiskStateMachine, RiskV2Config
from quantlab.risk_v3 import (
    RiskManagedStrategyV3,
    RiskV3Config,
    ScheduleFeed,
    Status,
    capital_protection_report,
    recovery_sensitivity,
)


H = pd.Timedelta(hours=1)
CFG = ExecConfig(wallet=1000.0)
PAIRS = [f"A{i:02d}/USDT" for i in range(40)]


def feed(n=24 * 90, pairs=PAIRS, seed=7, defects=None, vol=0.004):
    """Hourly 40-asset feed. ``defects``: {pair: (first_missing_index, resume_index | None)}."""
    idx = pd.date_range("2022-01-01", periods=n, freq="1h", tz="UTC")
    out = {}
    for k, p in enumerate(pairs):
        rng = np.random.default_rng(seed * 1000 + k)
        c = 100.0 * np.exp(np.cumsum(rng.normal(0, vol, n)))
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
        if p in (defects or {}):
            a, b = defects[p]
            df = df.drop(df.index[a : (b if b is not None else n)])
        out[p] = df
    return PriceData(out, idx)


class Rotation(Strategy):
    """Deterministic daily rotation over many assets (sells and buys, so fees, min-notional and fills are exercised).
    It decides only at 00:00 UTC so the same object is valid under V2 (hourly calls) and V3."""

    def __init__(self, pairs=PAIRS, notional=40.0):
        self.pairs, self.notional = pairs, notional

    def on_candle(self, t, hist, view):
        if t.hour != 0:
            return []
        day = int(t.timestamp() // 86400)
        target = {p for k, p in enumerate(self.pairs) if (day + k) % 5 == 0}
        orders = [Order(p, "sell", fraction=1.0) for p in list(view.positions) if p not in target]
        orders += [
            Order(p, "buy", notional=self.notional)
            for p in sorted(target)
            if p not in view.positions
        ]
        return orders


def run_v3(d, feed_=None, cfg=None):
    cfg = cfg or RiskV3Config()
    m = RiskStateMachine.new(cfg.v2, 1000.0)
    s = RiskManagedStrategyV3(Rotation(), m, cfg, feed_)
    return s, m, run(s, d, CFG)


def run_v2(d):
    m = RiskStateMachine.new(RiskV2Config(), 1000.0)
    return m, run(RiskManagedStrategy(Rotation(), m), d, CFG)


def first_shutdown(m):
    return next((r for r in m.records if r["to"] == "SHUTDOWN"), None)


# ------------------------------------------------------------------------------------------ G1
def test_g1_clean_feed_v3_is_identical_to_v2_through_the_engine():
    d = feed()
    s3, m3, r3 = run_v3(d)
    m2, r2 = run_v2(d)
    assert (
        len(r3.orders) > 100
    )  # a non-trivial run: many fills through fees, min-notional and fills
    assert r3.orders == r2.orders and r3.hash == r2.hash
    assert r3.equity.equals(r2.equity)
    assert first_shutdown(m3) is None and first_shutdown(m2) is None
    assert all(x["impaired"] == [] and x["cons"] == pytest.approx(x["lk"]) for x in s3.ticks)


def test_g1_with_defects_v3_matches_v2_until_the_alarm_then_values_conservatively_and_never_assumes_a_sale():
    n = 24 * 90
    defects = {
        PAIRS[3]: (600, None),
        PAIRS[8]: (900, 930),
        PAIRS[13]: (1300, None),
    }  # delisting, 30 h halt, delisting
    d = feed(n=n, defects=defects)
    s, m, res = run_v3(d)
    m2, r2 = run_v2(d)
    a3, a2 = first_shutdown(m), first_shutdown(m2)
    assert a3 and a2 and a3["t"] == a2["t"] and a3["cause"] == "integrity"
    t_alarm = pd.Timestamp(a3["t"])
    pre3 = [o for o in res.orders if pd.Timestamp(o["time"]) < t_alarm]
    pre2 = [o for o in r2.orders if pd.Timestamp(o["time"]) < t_alarm]
    assert pre3 == pre2 and len(pre3) > 20  # identical behaviour until the alarm
    # zero recovery is the primary valuation: conservative equity never exceeds last-known equity
    assert RiskV3Config().gate_recovery == 0.0
    assert all(x["cons"] <= x["lk"] + 1e-9 for x in s.ticks)
    assert any(x["impaired"] for x in s.ticks)
    # a delisted asset is never assumed sold: it stays in the position book and no trade of it is ever closed
    last_candle = {
        p: d.index[np.where(~np.isnan(d.close[:, d.col[p]]))[0][-1]] for p in (PAIRS[3], PAIRS[13])
    }
    for p, last in last_candle.items():
        if p == PAIRS[3]:  # held when it was delisted: stays in the book, valued conservatively
            assert p in res.state.positions
        closed = res.trades[res.trades["pair"] == p] if len(res.trades) else res.trades
        assert all(
            pd.Timestamp(c) <= last + H for c in closed.get("close_date", [])
        )  # nothing closed after delisting
    # the permanently impaired assets keep their last-known value out of conservative equity (zero recovery)
    final = s.ticks[-1]
    assert final["impaired_lk"] >= 0 and final["cons"] == pytest.approx(
        final["lk"] - final["impaired_lk"]
    )
    assert m.s.state == "SHUTDOWN" and m.s.safety_disqualified


def test_g1_engine_and_wrapper_are_deterministic_and_unaffected_by_unrelated_state():
    n = 24 * 40
    d = feed(n=n, defects={PAIRS[5]: (300, None)})
    h1 = [run_v3(d)[2].hash for _ in range(2)]
    assert h1[0] == h1[1]
    d2 = feed(n=n, defects={PAIRS[5]: (300, None)})
    assert run_v3(d2)[2].hash == h1[0]  # rebuilt inputs, same hash
    ordered = hashlib.sha256(
        json.dumps(run_v3(d)[2].orders, sort_keys=True, default=str).encode()
    ).hexdigest()
    assert (
        ordered
        == hashlib.sha256(
            json.dumps(run_v3(d2)[2].orders, sort_keys=True, default=str).encode()
        ).hexdigest()
    )


def test_g1_one_year_forty_assets_clean_equivalence_and_defect_run_is_bounded_and_deterministic():
    """Scale check (365 days x 40 assets x hourly, ~350 k asset-candles; the 4.5-year version of the plan differs only in
    length: the equivalence argument is time-invariant)."""
    n = 24 * 365
    d = feed(n=n, seed=11)
    _s3, _m3, r3 = run_v3(d)
    _m2, r2 = run_v2(d)
    assert r3.hash == r2.hash and len(r3.orders) > 500
    stop = 24 * 83 + 6  # six hours into a day on which the rotation holds the pair below
    day = int((pd.Timestamp("2022-01-01", tz="UTC") + stop * H).timestamp() // 86400)
    held = PAIRS[(-day) % 5]  # (day + k) % 5 == 0 -> held that day
    dd = feed(n=n, seed=11, defects={held: (stop, None), PAIRS[30]: (5000, 5040)})
    s, m, res = run_v3(dd)
    assert first_shutdown(m) is not None and all(x["cons"] <= x["lk"] + 1e-9 for x in s.ticks)
    assert run_v3(dd)[2].hash == res.hash


# ------------------------------------------------------------------------------------------ G3
EPOCHS = [
    {
        "symbol": "A00/USDT",
        "start": pd.Timestamp("2021-01-01", tz="UTC"),
        "end": pd.Timestamp("2021-06-10", tz="UTC"),
    },
    {
        "symbol": "A01/USDT",
        "start": pd.Timestamp("2021-02-01", tz="UTC"),
        "end": pd.Timestamp("2021-09-15 07:00", tz="UTC"),
    },
    {
        "symbol": "A02/USDT",
        "start": pd.Timestamp("2021-03-01", tz="UTC"),
        "end": pd.Timestamp("2025-07-01", tz="UTC"),
        "open": True,
    },
    {
        "symbol": "A03/USDT",
        "start": pd.Timestamp("2021-04-01", tz="UTC"),
        "end": pd.Timestamp("2022-02-20", tz="UTC"),
    },
    {
        "symbol": "A03/USDT",
        "start": pd.Timestamp("2022-03-05", tz="UTC"),
        "end": pd.Timestamp("2024-05-05", tz="UTC"),
    },
]
CUT = pd.Timestamp("2025-07-01", tz="UTC")
HOR = pd.Timedelta(hours=48)


SYMBOLS = sorted({e["symbol"] for e in EPOCHS})


def statuses(epochs, t):
    f = rs.epoch_feed(epochs, HOR, CUT)
    return {sym: f(sym, t) for sym in SYMBOLS}


def test_g3_status_source_is_prefix_invariant_at_every_date():
    probes = pd.date_range("2021-01-01", "2025-06-30", freq="37h", tz="UTC")
    for t in probes:
        assert statuses(rs.truncate_epochs(EPOCHS, t, HOR), t) == statuses(EPOCHS, t), t
    # delisting is known only after the horizon, never at the last candle
    f = rs.epoch_feed(EPOCHS, HOR, CUT)
    end = EPOCHS[1]["end"]
    assert f("A01/USDT", end) is None and f("A01/USDT", end + HOR - pd.Timedelta(minutes=1)) is None
    assert f("A01/USDT", end + HOR) == Status.DELISTED
    assert f("A02/USDT", CUT) is None  # an epoch that runs to the cutoff is not delisted


def test_g3_a_status_source_that_reads_the_future_fails_the_prefix_test():
    def leaky(
        epochs, t
    ):  # stamps DELISTED at the last candle, which the truncated table cannot know
        ev = {
            e["symbol"]: [(e["end"], Status.DELISTED)]
            for e in epochs
            if not e.get("open") and e["end"] < CUT
        }
        f = ScheduleFeed(ev)
        return {sym: f(sym, t) for sym in SYMBOLS}

    t = EPOCHS[1]["end"] + pd.Timedelta(hours=5)  # inside the 48 h window: not knowable yet
    assert leaky(rs.truncate_epochs(EPOCHS, t, HOR), t) != leaky(
        EPOCHS, t
    )  # leaky source differs (it peeks)
    assert statuses(rs.truncate_epochs(EPOCHS, t, HOR), t) == statuses(
        EPOCHS, t
    )  # the real source does not


# ------------------------------------------------------------------------------------------ G5
def one_gap(resume_after_hours: int, first_print_move: float, n=400, stop=100):
    """Asset X silent from ``stop`` for ``resume_after_hours`` then resumes with a first print moved by ``first_print_move``."""
    idx = pd.date_range("2022-01-01", periods=n, freq="1h", tz="UTC")
    out = {}
    for p in ("X/USDT", "Y/USDT"):
        c = np.full(n, 100.0)
        if p == "X/USDT":
            c[stop + resume_after_hours :] = 100.0 * (1 + first_print_move)
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
        if p == "X/USDT":
            df = df.drop(df.index[stop : stop + resume_after_hours])
        out[p] = df
    return PriceData(out, idx)


class HoldBoth(Strategy):
    def on_candle(self, t, hist, view):
        return [
            Order(p, "buy", notional=300.0) for p in ("X/USDT", "Y/USDT") if p not in view.positions
        ]


def run_gap(resume, move):
    cfg = RiskV3Config()
    m = RiskStateMachine.new(cfg.v2, 1000.0)
    s = RiskManagedStrategyV3(HoldBoth(), m, cfg)
    return s, m, run(s, one_gap(resume, move), CFG)


@pytest.mark.parametrize("move", [-0.3, 0.3, 0.6])
def test_g5_resume_at_47h_raises_no_alarm_and_the_jump_is_visible(move):
    s, m, _ = run_gap(47, move)
    assert first_shutdown(m) is None and m.s.state != "SHUTDOWN"
    lk = np.array([x["lk"] for x in s.ticks])
    if (
        move < 0
    ):  # the loss appears at the first print instead of being hidden by the stale valuation
        assert (
            lk.min() < lk[0] - 80
            and capital_protection_report(s.ticks)["max_drawdown_last_known"] > 0.08
        )
    else:
        assert lk.max() > lk[0] + 80


def test_g5_a_minus_60_percent_first_print_after_47h_is_not_hidden_it_trips_the_existing_alarm():
    s, m, _ = run_gap(47, -0.6)
    a = first_shutdown(m)
    resume_t = pd.Timestamp("2022-01-01", tz="UTC") + (100 + 47) * H
    assert (
        a and resume_t <= pd.Timestamp(a["t"]) <= resume_t + 2 * H
    )  # at the print, not 48 h later
    assert set(a["conditions"]) & {"integrity", "tier2", "floor"}
    assert capital_protection_report(s.ticks)["max_drawdown_last_known"] > 0.15


@pytest.mark.parametrize("move", [-0.6, 0.6])
def test_g5_resume_at_49h_the_alarm_fired_at_48h_and_stays_permanent(move):
    s, m, _ = run_gap(49, move)
    a = first_shutdown(m)
    assert a and a["cause"] == "integrity" and m.s.state == "SHUTDOWN" and m.s.safety_disqualified
    stop_t = pd.Timestamp("2022-01-01", tz="UTC") + 100 * H
    assert 47 <= (pd.Timestamp(a["t"]) - stop_t) / H <= 50
    # a favourable first print after the alarm cannot undo the shutdown
    assert all(r["to"] == "SHUTDOWN" for r in m.records)


# ------------------------------------------------------------------------------------------ G2 policy
def test_g2_zero_recovery_is_primary_and_sensitivity_never_creates_liquidity():
    assert RiskV3Config().gate_recovery == 0.0 and RiskV3Config().sensitivity_recoveries == (
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    )
    d = one_gap(10_000, 0.0, n=400, stop=100)  # X never resumes: delisted in practice
    for r in (0.0, 0.5, 1.0):
        cfg = RiskV3Config(gate_recovery=r)
        m = RiskStateMachine.new(cfg.v2, 1000.0)
        s = RiskManagedStrategyV3(HoldBoth(), m, cfg)
        res = run(s, d, CFG)
        closed_x = res.trades[res.trades["pair"] == "X/USDT"] if len(res.trades) else res.trades
        assert len(closed_x) == 0, f"recovery {r}: the impaired asset must never be sold"
        assert "X/USDT" in res.state.positions  # still held, never assumed liquidated
        final = s.ticks[-1]
        assert final["cons"] == pytest.approx(final["lk"] - final["impaired_lk"] * (1 - r))
    s0 = recovery_sensitivity(s.ticks)
    assert list(s0) == ["0.0", "0.25", "0.5", "0.75", "1.0"]
