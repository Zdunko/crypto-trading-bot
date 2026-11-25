"""Amendment A1: the liquidity budget uses only COMPLETED candles (median of the previous 24)."""

import numpy as np
import pandas as pd
import pytest

from quantlab.execution import LIQ_LOOKBACK, ExecConfig, Order, PriceData, Strategy, run


N = 120
IDX = pd.date_range("2024-01-01", periods=N, freq="1h", tz="UTC")
CFG = {"breaker": False, "max_participation": 0.10}


def frame(volume, price=100.0, n=N, drop=()):
    v = np.full(n, volume, dtype=float) if np.isscalar(volume) else np.asarray(volume, dtype=float)
    df = pd.DataFrame(
        {"date": IDX[:n], "open": price, "high": price, "low": price, "close": price, "volume": v}
    )
    return df.drop(index=list(drop)).reset_index(drop=True) if drop else df


class Script(Strategy):
    def __init__(self, plan):
        self.plan = plan

    def on_candle(self, t, hist, view):
        return [Order(**o.__dict__) for o in self.plan.get(len(hist.times), [])]


def go(plan, df, **over):
    return run(Script(plan), PriceData({"A": df}, IDX), ExecConfig(**{**CFG, **over}))


def filled(res):
    return sum(p.open_value for p in res.state.positions.values())


def test_the_volume_of_the_executing_candle_and_later_candles_is_never_read():
    base = np.full(N, 100.0)
    plan = {40: [Order("A", "buy", notional=500.0)]}
    results = []
    for tweak in (lambda v: v, lambda v: v.__setitem__(slice(40, None), 1e-9), lambda v: v.__setitem__(slice(40, None), 1e9),
                  lambda v: v.__setitem__(40, np.nan)):  # fmt: skip
        v = base.copy()
        tweak(v)
        results.append(go(plan, frame(v)))
    assert len({round(filled(r), 9) for r in results}) == 1 and len({r.hash for r in results}) == 1


def test_budget_is_participation_times_the_median_of_the_previous_24_candles_in_base_units():
    # price 100, median volume 10 base units -> budget 1.0 unit -> max spend 1.0 * 100 * 1.0005 * 1.001
    res = go({40: [Order("A", "buy", notional=1000.0)]}, frame(10.0))
    assert filled(res) == pytest.approx(1.0 * 100.0 * 1.0005 * 1.001, rel=1e-9)
    # an outlier spike inside the window does not move the median
    v = np.full(N, 10.0)
    v[35] = 1e6
    assert filled(go({40: [Order("A", "buy", notional=1000.0)]}, frame(v))) == pytest.approx(
        filled(res), rel=1e-9
    )


def test_buy_notional_conversion_respects_fee_slippage_and_min_notional():
    res = go(
        {40: [Order("A", "buy", notional=1000.0)]}, frame(0.04)
    )  # budget 0.004 unit = 0.4 USDT < min 5
    assert not res.state.positions and res.rejects[-1]["reason"] == "illiquid"


@pytest.mark.parametrize("bad", [0.0, -5.0, np.nan, np.inf])
def test_missing_zero_or_invalid_volume_means_no_liquidity(bad):
    res = go({40: [Order("A", "buy", notional=100.0)]}, frame(bad))
    assert not res.state.positions and res.rejects[-1]["reason"] == "illiquid"


def test_insufficient_history_fails_closed_and_more_than_half_invalid_slots_give_zero_median():
    early = go({LIQ_LOOKBACK - 1: [Order("A", "buy", notional=100.0)]}, frame(1000.0))
    assert not early.state.positions
    ok = go({LIQ_LOOKBACK: [Order("A", "buy", notional=100.0)]}, frame(1000.0))
    assert ok.state.positions
    v = np.full(N, 1000.0)
    v[40 - 13 : 40] = np.nan  # 13 of the 24 previous slots invalid -> median 0
    assert not go({40: [Order("A", "buy", notional=100.0)]}, frame(v)).state.positions
    v[40 - 13] = 1000.0  # only 12 invalid -> median still positive
    assert go({40: [Order("A", "buy", notional=100.0)]}, frame(v)).state.positions


def test_a_missing_candle_inside_the_window_counts_as_zero_volume():
    holes = [20 + k for k in range(13)]  # 13 missing candles among the 24 before candle 40
    df = frame(1000.0, drop=holes)
    res = go({40: [Order("A", "buy", notional=100.0)]}, df)
    assert not res.state.positions


def test_all_orders_on_an_asset_share_one_budget_sells_first_then_buys():
    # budget 0.1 unit (volume 10 x 10 %... median 1.0 -> 0.1 unit)
    plan = {
        40: [Order("A", "buy", notional=200.0)],
        45: [Order("A", "sell"), Order("A", "buy", notional=200.0, add=True)],
    }
    res = go(plan, frame(1.0), max_participation=0.10)
    pos_qty = sum(p.qty for p in res.state.positions.values())
    sold = res.trades["amount"].sum()
    assert sold + pos_qty <= 0.2 + 1e-9  # at most one budget each on candle 40 and candle 45
    c45 = res.trades[res.trades["close_date"] == IDX[45]]["amount"].sum()
    assert (
        c45 <= 0.1 + 1e-12
    )  # the sell used (part of) the candle's budget, the buy got only the rest


def test_partial_sells_continue_on_following_candles_until_flat():
    plan = {40: [Order("A", "buy", notional=1000.0)], 70: [Order("A", "sell")]}
    res = go(plan, frame(np.r_[np.full(41, 1000.0), np.full(N - 41, 5.0)]))
    sells = res.trades
    qty = 1000.0 / (100.0 * 1.0005 * 1.001)
    assert len(sells) >= 15 and sells["amount"].max() <= 0.5 + 1e-12  # 10 % of the median volume 5
    assert sells["amount"].sum() == pytest.approx(qty, rel=1e-9) and not res.state.positions
    assert sells["close_date"].is_monotonic_increasing


def test_halt_liquidation_persists_across_missing_candles_and_zero_liquidity():
    price = np.r_[np.full(60, 100.0), np.full(N - 60, 40.0)]
    vol = np.r_[
        np.full(40, 1000.0), np.full(N - 40, 0.0)
    ]  # liquidity vanishes after the position is built
    df = pd.DataFrame(
        {"date": IDX, "open": price, "high": price, "low": price, "close": price, "volume": vol}
    )
    res = go({40: [Order("A", "buy", notional=900.0)]}, df, breaker=True, wallet=1000.0)
    assert any(e["type"] == "halt" for e in res.breaker_events)
    assert "A" in res.state.positions  # no liquidity -> still waiting, never expired, never dropped
    pending = [o for o in res.state.pending if o.reason == "halt"]
    assert len(pending) == 1
