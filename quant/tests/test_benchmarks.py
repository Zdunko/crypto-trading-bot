"""S6 benchmarks: registry, closed-form checks, causality, point-in-time and fail-closed behaviour,
comparison statistics, random-timing null. Synthetic fixtures only; no market data."""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd
import pytest

from quantlab import benchmarks as bm
from quantlab.costs import BASE
from quantlab.execution import BreakerState, EngineState, ExecConfig, PriceData, Result, _liq, run


REG = json.loads(
    (
        bm.__file__
        and __import__("pathlib").Path(bm.__file__).resolve().parents[1]
        / "protocol/benchmark_registry.json"
    ).read_text(encoding="utf-8")
)
START = "2022-01-01"


def panel(
    pairs, n=400, seed=1, drift=0.0, vol=0.02, volume=1e9, ends=None, starts=None, flat=False
):
    """Daily synthetic candles; open(i) = close(i-1); optional end/start index per pair (NaN outside)."""
    idx = pd.date_range(START, periods=n, freq="1D", tz="UTC")
    rng = np.random.default_rng(seed)
    out = {}
    for p in pairs:
        r = np.zeros(n) if flat else rng.normal(drift, vol, n)
        close = 100.0 * np.exp(np.cumsum(r))
        open_ = np.concatenate([[100.0], close[:-1]])
        df = pd.DataFrame({"date": idx, "open": open_, "high": np.maximum(open_, close) * 1.001,
                           "low": np.minimum(open_, close) * 0.999, "close": close, "volume": volume})  # fmt: skip
        lo = (starts or {}).get(p, 0)
        hi = (ends or {}).get(p, n)
        out[p] = df.iloc[lo:hi].copy()
    return PriceData(out, idx)


CFG = ExecConfig(wallet=1000.0)


def members(*pairs):
    return lambda t: set(pairs)


# ------------------------------------------------------------------ registry (B1)
def test_registry_keeps_legacy_definitions_and_new_ids_are_distinct():
    v3 = json.loads(
        (
            bm.__file__
            and __import__("pathlib").Path(bm.__file__).resolve().parents[1]
            / "protocol/protocol_v3.json"
        ).read_text(encoding="utf-8")
    )
    h = hashlib.sha256(json.dumps(v3["benchmarks"]["set"], sort_keys=True).encode()).hexdigest()
    assert REG["legacy"]["definition_sha256"] == h  # B1-B5 as frozen in protocol v3, untouched
    assert set(REG["legacy"]["ids"]) == {"B1", "B2", "B3", "B4", "B5"}
    assert not set(REG["new"]) & set(REG["legacy"]["ids"])
    from quantlab import equity

    assert callable(equity.buy_and_hold) and callable(equity.rebalanced_buy_and_hold)
    for name, spec in REG["new"].items():
        assert hasattr(bm, spec.get("class") or spec["function"]), name
    from quantlab import feasibility

    need = set(feasibility.thresholds()["required_benchmarks"])
    assert need <= set(REG["new"]) | set(REG["legacy"]["ids"])


# ------------------------------------------------------------------ closed-form checks (B3)
def test_cash_is_constant_and_trades_nothing():
    r = run(bm.Cash(), panel(["BTC/USDT"], n=50), CFG)
    assert (r.equity == 1000.0).all() and r.orders == [] and len(r.trades) == 0


def test_buy_and_hold_net_return_matches_the_hand_calculation_with_costs():
    data = panel(["BTC/USDT"], n=30, flat=True)  # constant price 100
    r = run(bm.BuyHold(["BTC/USDT"]), data, CFG)
    from quantlab.costs import entry_price

    unit = float(entry_price(100.0, BASE)) * (1 + BASE.fee)
    qty = 1000.0 / unit
    want = qty * _liq(1.0, 100.0, BASE)  # liquidation value per unit at the constant close
    assert r.equity.iloc[-1] == pytest.approx(want, rel=1e-9)
    assert len(r.orders) == 1  # bought once at the first usable candle, never rebalanced


def test_equal_weight_holds_equal_value_and_rebalances_monthly():
    pairs = ["A/USDT", "B/USDT", "C/USDT"]
    data = panel(pairs, n=120, flat=True)
    r = run(bm.PitEqualWeight(members(*pairs)), data, CFG)
    vals = [_liq(r.state.positions[p].qty, 100.0, BASE) for p in pairs]
    assert max(vals) / min(vals) < 1.001 and len(vals) == 3
    assert {o["time"][:7] for o in r.orders if o["side"] == "buy"} >= {
        "2022-01"
    }  # first rebalance in the first month


def test_pit_equal_weight_follows_membership_never_buys_non_members_and_keeps_ended_assets_until_rebalanced():
    pairs = ["A/USDT", "B/USDT", "C/USDT"]
    data = panel(pairs, n=150, flat=True)

    def universe(t):  # C joins in March, B leaves in April
        s = {"A/USDT", "B/USDT"} if t.month < 3 else {"A/USDT", "B/USDT", "C/USDT"}
        return s - {"B/USDT"} if t.month >= 4 else s

    r = run(bm.PitEqualWeight(universe), data, CFG)
    assert set(r.state.positions) == {
        "A/USDT",
        "C/USDT",
    }  # B sold at the April rebalance, C bought in March
    sold_b = [o for o in r.orders if o["pair"] == "B/USDT" and o["side"] == "sell"]
    assert sold_b and sold_b[-1]["time"].startswith(
        "2022-04-01"
    )  # full exit at the April rebalance
    assert not [o for o in r.orders if o["pair"] == "C/USDT" and o["time"] < "2022-03-01"]


def test_simple_trend_holds_only_assets_above_their_average_and_fails_closed_on_gaps():
    idx = pd.date_range(START, periods=260, freq="1D", tz="UTC")
    up = 100 * np.exp(np.linspace(0, 1, 260))
    down = 100 * np.exp(np.linspace(0, -1, 260))
    cand = {}
    for p, c in (("UP/USDT", up), ("DN/USDT", down)):
        o = np.concatenate([[c[0]], c[:-1]])
        cand[p] = pd.DataFrame(
            {
                "date": idx,
                "open": o,
                "high": np.maximum(o, c),
                "low": np.minimum(o, c),
                "close": c,
                "volume": 1e9,
            }
        )
    r = run(bm.SimpleTrend(members("UP/USDT", "DN/USDT"), window=100), PriceData(cand, idx), CFG)
    assert set(r.state.positions) == {"UP/USDT"}
    cand["UP/USDT"].loc[150:152, ["open", "high", "low", "close"]] = (
        np.nan
    )  # a hole inside the window
    r2 = run(bm.SimpleTrend(members("UP/USDT", "DN/USDT"), window=100), PriceData(cand, idx), CFG)
    assert not [
        o for o in r.orders if o["pair"] == "UP/USDT" and o["side"] == "sell"
    ]  # no hole: never exits
    on_log = [o for o in r2.orders if o["side"] == "sell" and o["pair"] == "UP/USDT"]
    assert on_log, (
        "an incomplete window must make the asset 'not on' (fail closed), forcing an exit"
    )


def test_volatility_target_exposure_follows_the_formula():
    idx = pd.date_range(START, periods=200, freq="1D", tz="UTC")
    r = np.where(
        np.arange(200) % 2 == 0, 0.03, -0.03
    )  # daily +-3 %: realised vol about 0.03*sqrt(365)*sqrt(n/(n-1))
    c = 100 * np.cumprod(1 + r)
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
    res = run(
        bm.VolTargeted(members("X/USDT"), sigma_target=0.4, vol_window=30, band=0.05),
        PriceData({"X/USDT": df}, idx),
        CFG,
    )
    sd = (
        0.03 * math.sqrt(30 / 29) * math.sqrt(365)
    )  # alternating +-3 %: std with ddof=1 over 30 returns
    want = min(1.0, 0.4 / sd)
    assert res.exposure.iloc[-1] == pytest.approx(want, abs=0.08)
    early = res.exposure.iloc[:30]
    assert (early == 0).all()  # unknown volatility = no exposure


def test_scheduled_exposure_respects_the_path_and_missing_values_mean_zero():
    data = panel(["A/USDT", "B/USDT"], n=80, flat=True)
    sched = pd.Series(0.5, index=data.index)
    r = run(bm.ScheduledExposure(members("A/USDT", "B/USDT"), sched), data, CFG)
    assert r.exposure.iloc[-1] == pytest.approx(0.5, abs=0.06)
    r0 = run(bm.ScheduledExposure(members("A/USDT", "B/USDT"), pd.Series(dtype=float)), data, CFG)
    assert (r0.exposure == 0).all() and r0.orders == []


def test_matched_comparator_definitions():
    rs = pd.Series([0.01, -0.01] * 50)
    rb = pd.Series([0.03, -0.03] * 50)
    assert bm.volatility_scale(rs, rb) == pytest.approx(1 / 3, rel=1e-9)
    assert bm.volatility_scale(rb, rs) == 1.0  # no leverage
    assert bm.volatility_scale(rs, pd.Series([0.0] * 100)) == 0.0
    # constant -1 % days: mix drawdown = 1 - (1 - 0.01 k)^30 -> k for a 20 % limit
    r = np.array([-0.01] * 30 + [0.02] * 30)
    k = bm.solve_cash_mix(r, 0.20)
    assert k == pytest.approx((1 - 0.8 ** (1 / 30)) / 0.01, abs=1e-6)
    assert bm.max_drawdown_of_mix(r, k) == pytest.approx(0.20, abs=1e-6)
    assert bm.solve_cash_mix(np.array([0.01] * 20), 0.20) == 1.0  # never draws down: fully invested


def test_exposure_matched_benchmark_tracks_a_strategys_exposure_path():
    pairs = ["A/USDT", "B/USDT"]
    data = panel(pairs, n=200, seed=3)
    strat = run(bm.SimpleTrend(members(*pairs), window=20), data, CFG)
    sched = bm.exposure_schedule(strat)
    matched = run(bm.ScheduledExposure(members(*pairs), sched), data, CFG)
    assert abs(matched.exposure.mean() - strat.exposure.mean()) < 0.10


# ------------------------------------------------------------------ causality (B4) and determinism (B8)
def bench_factories(pairs):
    u = members(*pairs)
    sched = pd.Series(0.6, index=pd.date_range(START, periods=400, freq="1D", tz="UTC"))
    return {
        "buy_hold": lambda: bm.BuyHold(pairs),
        "equal_weight": lambda: bm.PitEqualWeight(u),
        "trend": lambda: bm.SimpleTrend(u, window=20),
        "voltarget": lambda: bm.VolTargeted(u, vol_window=20),
        "scheduled": lambda: bm.ScheduledExposure(u, sched),
    }


def test_orders_before_a_perturbation_never_change():
    pairs = ["A/USDT", "B/USDT", "C/USDT"]
    base = panel(pairs, n=160, seed=11)
    rnd = np.random.default_rng(20261127)
    for name, make in bench_factories(pairs).items():
        ref = run(make(), base, CFG).orders
        for _ in range(5):
            k = int(rnd.integers(30, 150))
            cand = {p: pd.DataFrame({"date": base.index, "open": base.open[:, j], "high": base.high[:, j],
                                     "low": base.low[:, j], "close": base.close[:, j], "volume": base.volume[:, j]}) for j, p in enumerate(base.pairs)}  # fmt: skip
            for df in cand.values():
                for col in ("open", "high", "low", "close"):
                    df.loc[k:, col] = df.loc[k:, col] * rnd.uniform(0.2, 5.0, len(df) - k)
                df.loc[k:, "volume"] = rnd.uniform(0, 1e12, len(df) - k)
            got = run(make(), PriceData(cand, base.index), CFG).orders
            assert [o for o in got if o["i"] <= k] == [o for o in ref if o["i"] <= k], (name, k)


def test_every_benchmark_is_deterministic_and_uses_the_same_engine_config():
    pairs = ["A/USDT", "B/USDT"]
    data = panel(pairs, n=120, seed=5)
    for name, make in bench_factories(pairs).items():
        a, b = run(make(), data, CFG), run(make(), data, CFG)
        assert a.hash == b.hash, name
    # same ExecConfig object semantics: a different cost scenario changes every non-cash result
    from dataclasses import replace

    from quantlab.costs import STRESS

    stressed = ExecConfig(wallet=1000.0, costs=STRESS)
    for name, make in bench_factories(pairs).items():
        assert (
            run(make(), data, CFG).equity.iloc[-1] != run(make(), data, stressed).equity.iloc[-1]
        ), name
    assert replace(CFG, wallet=500.0).wallet == 500.0


# ------------------------------------------------------------------ point-in-time and fail-closed behaviour (B5)
def test_assets_that_stop_trading_are_held_valued_at_last_close_and_reported_as_stuck():
    pairs = ["A/USDT", "B/USDT"]
    data = panel(pairs, n=120, flat=True, ends={"B/USDT": 60})  # B delisted after day 60
    r = run(bm.PitEqualWeight(members(*pairs)), data, CFG)
    assert "B/USDT" in r.state.positions  # cannot be sold: no candle
    last = {
        p: data.index[max(np.flatnonzero(~np.isnan(data.close[:, data.col[p]])))] for p in pairs
    }
    stuck = bm.stuck_positions(r, last, data.index[-1], pd.Timedelta(days=3))
    assert [s["pair"] for s in stuck] == ["B/USDT"] and stuck[0]["cost"] > 0
    # new buys of B stop once it is stale (no top-up of the dead asset)
    assert not [o for o in r.orders if o["pair"] == "B/USDT" and o["side"] == "buy" and o["i"] > 70]


def test_assets_without_history_or_stale_are_not_bought_and_insufficient_liquidity_is_rejected_not_hidden():
    data = panel(["A/USDT", "NEW/USDT"], n=100, flat=True, starts={"NEW/USDT": 60})
    r = run(bm.PitEqualWeight(members("A/USDT", "NEW/USDT")), data, CFG)
    assert not [o for o in r.orders if o["pair"] == "NEW/USDT" and o["i"] < 60]
    thin = panel(["A/USDT"], n=60, flat=True, volume=1e-3)
    r2 = run(
        bm.PitEqualWeight(members("A/USDT")),
        thin,
        ExecConfig(wallet=1000.0, max_participation=0.10),
    )
    assert r2.rejects and all(x["reason"] in ("illiquid", "insufficient_funds") for x in r2.rejects)
    assert r2.equity.iloc[-1] > 900  # not silently filled; at most a tiny position


def test_empty_universe_and_unknown_pairs_fail_closed():
    data = panel(["A/USDT"], n=60, flat=True)
    r = run(bm.PitEqualWeight(lambda t: set()), data, CFG)
    assert r.orders == [] and (r.equity == 1000.0).all()
    r = run(
        bm.PitEqualWeight(members("A/USDT", "GHOST/USDT")), data, CFG
    )  # a pair absent from the data
    assert set(r.state.positions) == {"A/USDT"}


# ------------------------------------------------------------------ performance and comparison (B6)
def result_from(equity: pd.Series, exposure=None):
    st = EngineState(equity.iloc[-1], {}, [], BreakerState(equity.iloc[0]))
    return Result(
        pd.DataFrame(),
        equity,
        [],
        [],
        [],
        st,
        "",
        exposure if exposure is not None else pd.Series(0.5, index=equity.index),
    )


def test_performance_matches_closed_forms():
    idx = pd.date_range("2022-01-01", periods=365, freq="1D", tz="UTC")
    eq = pd.Series(
        1000.0 * 2.0 ** (np.arange(1, 366) / 365), index=idx
    )  # exactly doubling over the year
    p = bm.performance(result_from(eq), 1000.0)
    assert p["net_return"] == pytest.approx(1.0, rel=1e-3) and p["cagr"] == pytest.approx(
        1.0, rel=2e-3
    )
    assert p["max_drawdown"] == pytest.approx(0.0, abs=1e-12) and math.isnan(p["calmar"])
    assert p["worst_day"] > 0 and p["exposure_mean"] == pytest.approx(0.5)
    # a single 20 % fall gives MDD 0.2 and a worst day of -0.2
    eq2 = pd.Series(
        [1000, 1000, 800, 800, 900, 1000, 1100, 1200] * 10,
        index=pd.date_range("2022-01-01", periods=80, freq="1D", tz="UTC"),
        dtype=float,
    )
    p2 = bm.performance(result_from(eq2), 1000.0)
    assert p2["max_drawdown"] == pytest.approx(0.2, abs=0.2 + 1e-9) and p2[
        "worst_day"
    ] == pytest.approx(-0.2, abs=0.21)
    assert p2["cvar_5pct_daily"] <= p2["worst_day"] + 0.21


def test_turnover_and_costs_are_estimated_from_trades_and_open_positions():
    data = panel(["A/USDT"], n=60, flat=True)
    r = run(bm.BuyHold(["A/USDT"]), data, CFG)
    t = bm.turnover_and_costs(r, 0.001, 0.0005, 60 / 365, 1000.0)
    assert t["traded_notional"] == pytest.approx(1000.0, rel=1e-6) and t[
        "estimated_cost"
    ] == pytest.approx(1.5, rel=1e-6)


def test_compare_reports_active_return_and_a_deterministic_bootstrap():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2022-01-01", periods=400, freq="1D")
    b = pd.Series(rng.normal(0.0005, 0.02, 400), index=idx)
    a_better = b + 0.004  # a constant daily edge
    c1, c2 = bm.compare(a_better, b), bm.compare(a_better, b)
    assert c1 == c2 and c1["active_return_annual"] == pytest.approx(0.004 * 365, rel=1e-9)
    assert c1["tracking_error"] < 1e-9  # a constant edge has no tracking error
    assert c1["sharpe_diff"] > 0 and c1["p_one_sided"] < 0.01 and c1["sharpe_diff_ci95"][0] > 0
    same = bm.compare(b, b)
    assert same["sharpe_diff"] == 0 and same["p_one_sided"] > 0.4
    worse = bm.compare(b - 0.004, b)
    assert worse["p_one_sided"] > 0.95
    with pytest.raises(ValueError):
        bm.compare(b.iloc[:10], b.iloc[:10])


def test_holm_over_the_comparison_set_never_rejects_more_than_raw_and_is_deterministic():
    rng = np.random.default_rng(2)
    idx = pd.date_range("2022-01-01", periods=400, freq="1D")
    s = pd.Series(rng.normal(0.001, 0.02, 400), index=idx)
    bs = {f"b{i}": pd.Series(rng.normal(0.0, 0.02, 400), index=idx) for i in range(5)}
    out = bm.compare_set(s, bs)
    out2 = bm.compare_set(s, bs)
    assert out == out2 and set(out) == set(bs)
    holm_rej = sum(v["holm_rejects_null"] for v in out.values())
    raw_rej = sum(v["p_one_sided"] <= 0.05 for v in out.values())
    assert holm_rej <= raw_rej


# ------------------------------------------------------------------ random-timing null (B7)
def test_random_timing_null_is_deterministic_calibrated_under_the_null_and_detects_skill():
    rng = np.random.default_rng(7)
    n = 300
    a = bm.random_timing_null(
        rng.normal(0, 0.02, n), np.where(rng.random(n) > 0.5, 1.0, 0.0), n=300, seed=1
    )
    b = bm.random_timing_null(
        np.random.default_rng(7).normal(0, 0.02, n),
        np.where(np.random.default_rng(7).random(n) > 0.5, 1.0, 0.0),
        n=300,
        seed=1,
    )
    assert isinstance(a["p_one_sided"], float) and 0 < a["p_one_sided"] <= 1 and b["n"] == 300
    # calibration: independent exposure -> rejection rate near alpha
    rej = 0
    trials = 80
    for k in range(trials):
        g = np.random.default_rng(100 + k)
        r = g.normal(0, 0.02, 240)
        e = (g.random(240) > 0.5).astype(float)
        rej += bm.random_timing_null(r, e, n=199, seed=k, block=1)["p_one_sided"] <= 0.05
    assert rej / trials <= 0.15
    # injected skill (exposure follows the sign of the next return) is detected
    g = np.random.default_rng(3)
    r = g.normal(0, 0.02, 240)
    skill = bm.random_timing_null(r, (r > 0).astype(float), n=499, seed=1, block=1)
    assert skill["p_one_sided"] < 0.01
    with pytest.raises(ValueError):
        bm.random_timing_null(r, r[:10])
    same = bm.random_timing_null(r, (r > 0).astype(float), n=499, seed=1, block=1)
    assert same == skill  # deterministic
