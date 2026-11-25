"""Cost model, equity reconstruction, benchmark and metric definitions - hand-checkable cases."""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from freqtrade.data.btanalysis import load_backtest_data

from quantlab.costs import BASE, STRESS, CostScenario, apply_costs
from quantlab.equity import build_equity, buy_and_hold, close_matrix, hourly_index
from quantlab.metrics import (
    max_drawdown,
    monthly_returns,
    net_return,
    profit_factor,
    sharpe,
    sortino,
    summarize,
    trade_stats,
)


FIXTURE = (
    Path(__file__).resolve().parents[2] / "tests/testdata/backtest_results/backtest-result.json"
)
IDX = hourly_index("2024-01-01", "2024-01-03")  # 48 hourly rows


def _trade(**kw):
    base = {
        "pair": "A/USDT",
        "open_date": IDX[2],
        "close_date": IDX[10],
        "amount": 10.0,
        "open_rate": 100.0,
        "close_rate": 110.0,
        "fee_open": BASE.fee,
        "fee_close": BASE.fee,
        "exit_reason": "exit_signal",
    }
    base.update(kw)
    return base


def _candles(price: float | np.ndarray = 100.0, n: int = 48) -> dict[str, pd.DataFrame]:
    px = np.full(n, price) if np.isscalar(price) else np.asarray(price, dtype=float)
    df = pd.DataFrame(
        {"date": IDX[:n], "open": px, "high": px, "low": px, "close": px, "volume": 1.0}
    )
    return {"A/USDT": df}


# ------------------------------------------------------------------ costs
def test_costs_applied_once_with_exact_arithmetic():
    out = apply_costs(pd.DataFrame([_trade()]), BASE)
    open_eff = 100.0 * 1.0005
    close_eff = 110.0 * (1 - 0.0005)
    open_value = 10 * open_eff * 1.001
    close_value = 10 * close_eff * 0.999
    assert out["profit_abs"].iloc[0] == pytest.approx(close_value - open_value)
    assert out["profit_ratio"].iloc[0] == pytest.approx(close_value / open_value - 1)
    # per side cost = fee + slippage = 0.15 %
    assert BASE.per_side == pytest.approx(0.0015) and STRESS.per_side == pytest.approx(0.003)


def test_stop_exit_pays_extra_slippage_only_on_exit():
    stop = apply_costs(pd.DataFrame([_trade(exit_reason="stop_loss")]), BASE)
    normal = apply_costs(pd.DataFrame([_trade()]), BASE)
    assert stop["close_rate_eff"].iloc[0] == pytest.approx(110 * (1 - 0.001))
    assert stop["open_rate_eff"].iloc[0] == normal["open_rate_eff"].iloc[0]


def test_zero_slippage_matches_freqtrade_formula():
    scenario = CostScenario("fee-only", fee=0.001, slippage=0.0, stop_extra=0.0)
    out = apply_costs(pd.DataFrame([_trade()]), scenario)
    ft = 10 * 110 * 0.999 - 10 * 100 * 1.001
    assert out["profit_abs"].iloc[0] == pytest.approx(ft)


def test_double_counting_guard_rejects_lumped_fee():
    lumped = pd.DataFrame([_trade(fee_open=0.0015, fee_close=0.0015)])
    with pytest.raises(ValueError, match="double-counting"):
        apply_costs(lumped, BASE)
    with pytest.raises(ValueError, match="lack columns"):
        apply_costs(pd.DataFrame([{"pair": "A"}]), BASE)


def test_profit_ratio_formula_matches_upstream_fixture():
    """Our ratio formula reproduces Freqtrade's own profit_ratio on upstream test results."""
    df = load_backtest_data(FIXTURE)
    open_v = df.amount * df.open_rate * (1 + df.fee_open)
    close_v = df.amount * df.close_rate * (1 - df.fee_close)
    assert np.abs(close_v / open_v - 1 - df.profit_ratio).max() < 1e-7


# ------------------------------------------------------------------ equity
def test_equity_ends_at_wallet_plus_realised_profit_and_is_flat_without_trades():
    wallet = 1000.0
    closes = close_matrix(_candles(), IDX)
    flat = build_equity(pd.DataFrame(columns=list(_trade())), closes, wallet, BASE)
    assert (flat == wallet).all()

    costed = apply_costs(pd.DataFrame([_trade()]), BASE)
    eq = build_equity(costed, closes, wallet, BASE)
    assert eq.iloc[-1] == pytest.approx(wallet + costed["profit_abs"].sum())
    assert eq.iloc[0] == wallet  # nothing open before the entry candle
    assert eq.iloc[9] != wallet  # open position marked to market
    assert eq.iloc[10] == pytest.approx(wallet + costed["profit_abs"].sum())  # realised at exit


def test_open_position_is_valued_at_liquidation_value():
    px = np.full(48, 100.0)
    px[5] = 120.0
    closes = close_matrix(_candles(px), IDX)
    costed = apply_costs(pd.DataFrame([_trade(close_rate=100.0)]), BASE)
    eq = build_equity(costed, closes, 1000.0, BASE)
    liq = 10 * 120.0 * (1 - BASE.fee - BASE.slippage)
    assert eq.iloc[5] == pytest.approx(1000.0 + liq - costed["open_value"].iloc[0])


def test_trade_open_at_period_end_is_still_marked_and_not_realised():
    t = _trade(open_date=IDX[40], close_date=IDX[47] + pd.Timedelta("5h"))
    closes = close_matrix(_candles(), IDX)
    costed = apply_costs(pd.DataFrame([t]), BASE)
    eq = build_equity(costed, closes, 1000.0, BASE)
    assert eq.iloc[-1] < 1000.0  # still open: only costs, no realised profit counted


# ------------------------------------------------------------------ benchmark
def test_buy_and_hold_pays_entry_and_exit_cost_once():
    candles = _candles()
    eq, pairs = buy_and_hold(candles, IDX, 1000.0, BASE)
    assert pairs == ["A/USDT"]
    expected = 1000.0 * (1 - BASE.fee - BASE.slippage) / ((1 + BASE.slippage) * (1 + BASE.fee))
    assert eq.iloc[-1] == pytest.approx(expected)
    # a flat market loses exactly the round-trip cost (about 0.3 %), nothing else
    assert 0.996 < eq.iloc[-1] / 1000.0 < 0.998


def test_buy_and_hold_equal_weights_and_skips_late_pairs():
    a = _candles(100.0)["A/USDT"]
    b = _candles(50.0)["A/USDT"].assign(close=lambda d: d["close"] * 2.0)  # doubles
    late = a.iloc[10:]
    eq, pairs = buy_and_hold({"A/USDT": a, "B/USDT": b, "L/USDT": late}, IDX, 1000.0, BASE)
    assert pairs == ["A/USDT", "B/USDT"]
    gross = 500 * 1.0 + 500 * 2.0
    assert eq.iloc[-1] == pytest.approx(
        gross * (1 - BASE.fee - BASE.slippage) / ((1 + BASE.slippage) * (1 + BASE.fee))
    )


# ------------------------------------------------------------------ metrics
def test_max_drawdown_known_value():
    eq = pd.Series([100, 120, 90, 100, 130, 65.0])
    assert max_drawdown(eq) == pytest.approx(0.5)  # 130 -> 65


def test_profit_factor_and_trade_stats():
    assert profit_factor([10, -5, 5, -5]) == pytest.approx(1.5)
    assert profit_factor([1, 2]) == math.inf
    assert math.isnan(profit_factor([]))
    trades = pd.DataFrame(
        {
            "profit_abs": [10.0, -5.0],
            "profit_ratio": [0.1, -0.05],
            "open_date": [IDX[0], IDX[0]],
            "close_date": [IDX[2], IDX[4]],
        }
    )
    s = trade_stats(trades)
    assert s["trades"] == 2 and s["win_rate"] == 0.5
    assert s["expectancy_pct"] == pytest.approx(0.025)
    assert s["avg_duration_h"] == pytest.approx(3.0)


def test_sharpe_sortino_known_values():
    r = np.array([0.01, -0.01, 0.02, 0.0])
    assert sharpe(r) == pytest.approx(r.mean() / r.std(ddof=1) * math.sqrt(365))
    down = math.sqrt(np.mean(np.minimum(r, 0) ** 2))
    assert sortino(r) == pytest.approx(r.mean() / down * math.sqrt(365))
    assert math.isnan(sortino(np.array([0.01, 0.02])))  # no downside -> undefined, not inf


def test_monthly_returns_and_summary():
    idx = hourly_index("2024-01-01", "2024-03-01")
    eq = pd.Series(np.linspace(1000, 1210, len(idx)), index=idx)
    m = monthly_returns(eq, 1000.0)
    assert list(m.index) == ["2024-01", "2024-02"]
    assert (1 + m).prod() == pytest.approx(eq.iloc[-1] / 1000.0)
    s = summarize(eq, None, 1000.0)
    assert s["net_return"] == pytest.approx(net_return(eq, 1000.0))
    assert s["max_drawdown"] == pytest.approx(0.0)
