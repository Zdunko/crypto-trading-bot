"""Family A on the Stage 0 engine: signal arithmetic, rebalancing, halt/liquidity behaviour,
causality, determinism and consistency with the frozen specification. Synthetic data only."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantlab.causality import mutation_mismatches, restart_mismatches
from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run
from quantlab.family_a import (
    VARIANTS,
    FamilyAConfig,
    FamilyAStrategy,
    daily_closes,
    episodes,
    exec_config,
    run_family_a,
    score_and_vol,
    target_weight,
)


N_DAYS = 330
IDX = pd.date_range("2023-01-01", periods=N_DAYS * 24, freq="1h", tz="UTC")
SPEC = json.loads(
    (Path(__file__).resolve().parents[1] / "protocol" / "protocol_v5_family_a.json").read_text()
)


def market(drift, vol, seed, volume=1e9):
    rng = np.random.default_rng(seed)
    daily = rng.normal(drift, vol, N_DAYS)
    hourly = np.repeat(daily / 24, 24) + rng.normal(0, vol / 40, len(IDX))
    close = 100 * np.exp(np.cumsum(hourly))
    open_ = np.concatenate([[100.0], close[:-1]])
    return pd.DataFrame({"date": IDX, "open": open_, "high": np.maximum(open_, close) * 1.001,
                         "low": np.minimum(open_, close) * 0.999, "close": close, "volume": volume})  # fmt: skip


def basket(drift=0.003, vol=0.02, n=3, volume=1e9):
    return {f"P{k}/USDT": market(drift, vol, 10 + k, volume) for k in range(n)}


# ------------------------------------------------------------------ signal arithmetic
def test_daily_closes_use_the_last_close_of_each_day_and_ignore_missing_hours():
    t = pd.date_range("2024-01-01", periods=48, freq="1h", tz="UTC")
    c = np.arange(48, dtype=float)
    c[23] = np.nan
    d = daily_closes(t, c)
    assert list(d) == [22.0, 47.0]  # hour 23 missing -> last available close of day 1


def test_trend_score_counts_satisfied_filters_and_fails_closed_without_history():
    cfg = FamilyAConfig()
    up = pd.Series(
        np.linspace(100, 200, 250), index=pd.date_range("2023-01-01", periods=250, freq="1D")
    )
    assert score_and_vol(up, cfg)[0] == 1.0
    assert score_and_vol(up.iloc[-120:], cfg)[0] == pytest.approx(
        2 / 3
    )  # no SMA200 -> not satisfied
    assert score_and_vol(up.iloc[-60:], cfg)[0] == pytest.approx(1 / 3)
    assert score_and_vol(up.iloc[-20:], cfg)[0] == 0.0
    assert score_and_vol(up.iloc[::-1].set_axis(up.index), cfg)[0] == 0.0  # falling market
    assert score_and_vol(up, FamilyAConfig(trend=False))[0] == 1.0  # V0


def test_volatility_is_the_annualised_std_of_30_daily_log_returns():
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.03, 31)
    s = pd.Series(
        100 * np.exp(np.cumsum(np.r_[0, r])),
        index=pd.date_range("2023-01-01", periods=32, freq="1D"),
    )
    _, sigma = score_and_vol(s, FamilyAConfig())
    assert sigma == pytest.approx(np.log(s).diff().dropna().iloc[-30:].std(ddof=1) * np.sqrt(365))
    assert np.isnan(score_and_vol(s.iloc[:20], FamilyAConfig())[1])


def test_target_weight_scaling_cap_and_fail_closed():
    cfg = FamilyAConfig()
    assert target_weight(1.0, 0.8, 8, cfg) == pytest.approx(0.5 / 8)  # 40 % / 80 %
    assert target_weight(1.0, 0.2, 8, cfg) == pytest.approx(1 / 8)  # never above 1/N: no leverage
    assert target_weight(2 / 3, 0.2, 8, cfg) == pytest.approx(2 / 3 / 8)
    assert (
        target_weight(1.0, float("nan"), 8, cfg) == 0.0 and target_weight(0.0, 0.3, 8, cfg) == 0.0
    )
    assert target_weight(1.0, 0.8, 8, FamilyAConfig(vol_scale=False)) == pytest.approx(1 / 8)  # A0


def test_weights_never_exceed_full_investment_for_any_input():
    rng = np.random.default_rng(1)
    for _ in range(500):
        n = int(rng.integers(1, 12))
        w = sum(
            target_weight(
                float(rng.integers(0, 4)) / 3, float(rng.uniform(0.01, 3)), n, FamilyAConfig()
            )
            for _ in range(n)
        )
        assert w <= 1.0 + 1e-12


# ------------------------------------------------------------------ strategy on the engine
def test_decisions_happen_only_at_midnight_and_only_after_the_warmup_filters_exist():
    res = run_family_a(basket(), "2023-01-02", "2023-11-27", "A1", exec_config())
    times = pd.to_datetime([o["time"] for o in res.orders])
    assert len(times) > 0 and (times == times.floor("1D")).all()
    assert times.min() >= pd.Timestamp("2023-02-01", tz="UTC")  # needs 30 daily returns first


def test_uptrend_basket_becomes_invested_and_a_downtrend_basket_stays_in_cash():
    up = run_family_a(
        basket(0.004, 0.015), "2023-01-02", "2023-11-27", "A0", exec_config(breaker=False)
    )
    assert up.equity.iloc[-1] > up.equity.iloc[0] and len(up.trades) + len(up.state.positions) > 0
    down = run_family_a(
        basket(-0.004, 0.015), "2023-01-02", "2023-11-27", "A1", exec_config(breaker=False)
    )
    assert not down.state.positions  # SMA filters keep the account in cash
    assert (
        down.equity.iloc[-1] >= 950
    )  # only small early whipsaw losses before the filters turn off


def test_rebalance_band_suppresses_small_adjustments_and_orders_are_counted_not_executed_blindly():
    data = basket(0.004, 0.015, n=2)
    tight = run_family_a(data, "2023-01-02", "2023-11-27", "A1", exec_config(breaker=False))
    import quantlab.family_a as fa

    wide = run(
        FamilyAStrategy(FamilyAConfig(band=0.30), 2),
        PriceData(data, pd.date_range("2023-01-01", periods=N_DAYS * 24, freq="1h", tz="UTC")),
        exec_config(breaker=False),
        start=24,
        end=N_DAYS * 24,
    )
    assert len(wide.orders) < len(tight.orders) and fa.FamilyAConfig().band == 0.05


def test_a_buy_adds_to_an_open_position_with_weighted_cost_basis_and_partial_sells_reconcile():
    idx = IDX[:80]
    df = pd.DataFrame({"date": idx, "open": np.r_[np.full(30, 100.0), np.full(50, 110.0)], "high": 120.0,
                       "low": 90.0, "close": np.r_[np.full(30, 100.0), np.full(50, 110.0)], "volume": 1e9})  # fmt: skip

    class Script(Strategy):
        def on_candle(self, t, hist, view):
            i = len(hist.times)
            return {2: [Order("A", "buy", notional=200.0)], 40: [Order("A", "buy", notional=200.0, add=True)],
                    50: [Order("A", "sell", fraction=0.5)], 60: [Order("A", "sell")]}.get(i, [])  # fmt: skip

    cfg = ExecConfig(breaker=False)
    res = run(Script(), PriceData({"A": df}, idx), cfg)
    assert not res.state.positions and len(res.trades) == 2
    assert res.trades["open_value"].sum() == pytest.approx(400.0)  # both buys fully accounted for
    assert res.equity.iloc[-1] == pytest.approx(cfg.wallet + res.trades["profit_abs"].sum())
    ep = episodes(res.trades)
    assert len(ep) == 1 and ep.iloc[0]["fills"] == 2


# ------------------------------------------------------------------ halt, cancellation, liquidity
def crashing_basket(volume):
    data = basket(0.004, 0.01, n=2, volume=volume)
    for df in data.values():  # a -30 % crash on day 200 after a strong uptrend
        df.loc[200 * 24 :, ["open", "high", "low", "close"]] *= 0.7
    return data


def test_halt_cancels_entries_liquidates_with_costs_and_never_restarts():
    res = run_family_a(crashing_basket(1e9), "2023-01-02", "2023-11-27", "A0", exec_config())
    halts = [e for e in res.breaker_events if e["type"] == "halt"]
    assert len(halts) == 1 and not any(e["type"] == "resume" for e in res.breaker_events)
    t_halt = pd.Timestamp(halts[0]["time"])
    assert not res.state.positions  # liquidated
    sells = res.trades[res.trades["exit_reason"] == "halt"]
    assert len(sells) > 0 and (sells["close_date"] >= t_halt).all()
    after = [o for o in res.orders if pd.Timestamp(o["time"]) > t_halt and o["side"] == "buy"]
    assert after == [] or all(
        r["reason"] == "halted"
        for r in res.rejects
        if r["side"] == "buy" and pd.Timestamp(r["time"]) > t_halt
    )
    # costs: halt liquidation sells at open*(1-slip) less fee, i.e. strictly below the reference price
    assert (
        sells["profit_abs"] / sells["open_value"]
        < sells["close_rate"] / sells["open_rate"] - 1 + 1e-12
    ).all()


def test_pending_entry_orders_are_cancelled_at_halt_and_the_halt_is_never_blocked_by_expiry():
    idx = IDX[:60]
    px = np.r_[np.full(20, 100.0), np.full(40, 60.0)]
    df = pd.DataFrame({"date": idx, "open": px, "high": px, "low": px, "close": px, "volume": 1e9})
    holes = df.drop(index=[21, 22, 23, 24, 25, 26]).reset_index(
        drop=True
    )  # no candles right after the crash
    other = pd.DataFrame(
        {"date": idx, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1e9}
    )

    class S(Strategy):
        def on_candle(self, t, hist, view):
            i = len(hist.times)
            return {
                1: [Order("A", "buy", notional=900.0)],
                21: [Order("B", "buy", notional=50.0)],
            }.get(i, [])

    res = run(S(), PriceData({"A": holes, "B": other}, idx), ExecConfig())
    halted_sells = res.trades[res.trades["exit_reason"] == "halt"]
    assert (
        len(halted_sells) == 1 and halted_sells.iloc[0]["close_date"] >= idx[27]
    )  # waited for a candle, no expiry
    assert "B" not in res.state.positions


def test_liquidity_cap_spreads_a_halt_liquidation_over_several_candles():
    idx = IDX[:120]
    px = np.r_[np.full(20, 100.0), np.full(100, 55.0)]
    vol = np.r_[
        np.full(20, 1000.0), np.full(100, 1.0)
    ]  # liquid when buying, thin when the crash comes
    df = pd.DataFrame({"date": idx, "open": px, "high": px, "low": px, "close": px, "volume": vol})

    class S(Strategy):
        def on_candle(self, t, hist, view):
            return [Order("A", "buy", notional=90.0)] if len(hist.times) == 1 else []

    res = run(S(), PriceData({"A": df}, idx), ExecConfig(wallet=100.0, max_participation=0.10))
    sells = res.trades[res.trades["exit_reason"] == "halt"]
    assert (
        len(sells) >= 5 and sells["amount"].max() <= 0.10 * 1.0 + 1e-12
    )  # capped fills, one per candle
    assert sells["close_date"].is_monotonic_increasing and not res.state.positions
    assert sum(t["amount"] for _, t in sells.iterrows()) == pytest.approx(
        0.9 / 1.0015 / 1.0005 / 1.0, rel=0.02
    )


# ------------------------------------------------------------------ causality and determinism
def make_strategy(_data):
    return FamilyAStrategy(FamilyAConfig(), 3)


@pytest.mark.parametrize("k", [120 * 24, 200 * 24, 280 * 24])
def test_family_a_decisions_never_depend_on_future_candles(k):
    data = basket()
    assert mutation_mismatches(make_strategy, data, IDX, exec_config(), k) == []
    assert (
        mutation_mismatches(
            lambda d: FamilyAStrategy(VARIANTS["V0"], 3), data, IDX, exec_config(), k
        )
        == []
    )


def test_family_a_restart_from_saved_state_reproduces_the_full_run():
    data = PriceData(basket(), IDX)
    for k in (150 * 24, 250 * 24):
        assert (
            restart_mismatches(
                lambda: FamilyAStrategy(FamilyAConfig(), 3),
                lambda s, h: None,
                data,
                exec_config(),
                k,
            )
            == []
        )


def test_family_a_is_deterministic():
    a = run_family_a(basket(), "2023-01-02", "2023-11-27", "A1")
    b = run_family_a(basket(), "2023-01-02", "2023-11-27", "A1")
    assert a.hash == b.hash and len(a.hash) == 64


# ------------------------------------------------------------------ specification consistency
def test_code_defaults_equal_the_frozen_specification():
    p = SPEC["parameters"]
    cfg = FamilyAConfig()
    assert list(cfg.trend_windows) == p["trend_windows"] and cfg.vol_window == p["vol_window"]
    assert (cfg.sigma_target, cfg.band, cfg.periods_per_year) == (
        p["sigma_target"],
        p["band"],
        p["periods_per_year"],
    )
    ex = exec_config()
    assert (
        ex.breaker
        and ex.halt_action == "flatten"
        and ex.max_participation == SPEC["execution"]["max_participation"]
    )
    br = SPEC["circuit_breaker"]
    assert (ex.dd_reduce, ex.dd_halt, ex.reduce_factor) == (
        br["reduce_at"],
        br["halt_at"],
        br["reduce_factor"],
    )
    assert br["enabled_in_all_evaluations"] is True and set(SPEC["variants"]) == set(VARIANTS)
