"""Windows, regimes, bootstrap and criteria evaluation on hand-built inputs."""

import math

import numpy as np
import pandas as pd
import pytest
from synth import random_walk_ohlcv

from quantlab.metrics import profit_factor, sharpe
from quantlab.validation import (
    block_bootstrap_ci,
    bootstrap_ci,
    calendar_windows,
    daily_regimes,
    evaluate_criteria,
    pair_profit_shares,
    regime_stats,
    trade_regimes,
    verdict,
    window_stats,
)


CRIT = {
    "T1": {"min_trades": 200, "max_pair_profit_share": 0.30},
    "T4": {"max_drawdown": 0.20},
    "T5": {"min_profit_factor": 1.3},
    "T6": {"min_profit_factor": 1.0},
    "T7": {"min_positive_window_share": 0.6, "max_window_profit_share": 0.5},
    "T8": {"min_regime_trades": 30, "min_profit_factor": 0.8},
    "T9": {"min_positive_variant_share": 0.75},
}


def _good() -> dict:
    return {
        "base": {
            "trades": 250,
            "net_return": 0.4,
            "max_drawdown": 0.15,
            "sortino": 1.5,
            "profit_factor": 1.5,
        },
        "pair_share_max": 0.25,
        "bench": {"sortino": 1.0, "max_drawdown": 0.7},
        "stress": {"net_return": 0.1, "profit_factor": 1.1},
        "windows": [{"return": 0.1, "profit": 100.0}] * 4 + [{"return": -0.02, "profit": -20.0}],
        "regimes": {
            "bull": {"trades": 100, "profit_factor": 1.5},
            "unknown": {"trades": 5, "profit_factor": 0.1},
        },
        "variants": [0.1, 0.2, 0.3, -0.1],
        "bias_clean": True,
    }


def _windows(profits):
    return [{"return": p / 1000.0, "profit": p} for p in profits]


def _passed(rows):
    return {r["id"]: r["passed"] for r in rows}


# ------------------------------------------------------------------ criteria (frozen v2 thresholds)
def test_all_criteria_pass_on_a_good_strategy():
    rows = evaluate_criteria(_good(), CRIT)
    assert verdict(rows) == {"validated_on_evaluation": True, "failed": []}


@pytest.mark.parametrize(
    "mutate,failed",
    [
        (lambda m: m["base"].update(trades=199), "T1a"),  # v2: 200 trades
        (lambda m: m.update(pair_share_max=0.31), "T1b"),
        (lambda m: m["base"].update(net_return=0.0), "T2"),
        (lambda m: m["base"].update(sortino=0.9), "T3"),
        (lambda m: m["base"].update(max_drawdown=0.21), "T4"),  # v2: 20 % absolute
        (lambda m: m["bench"].update(max_drawdown=0.10), "T4"),  # and not above the benchmark
        (lambda m: m["base"].update(profit_factor=1.29), "T5"),  # v2: 1.3
        (lambda m: m["stress"].update(net_return=-0.01), "T6"),
        (lambda m: m["stress"].update(profit_factor=0.99), "T6"),
        (lambda m: m.update(windows=_windows([40.0] * 3 + [-5.0] * 4)), "T7a"),
        (
            lambda m: m.update(
                windows=[{"return": 0.1, "profit": 90.0}, {"return": 0.01, "profit": 10.0}]
            ),
            "T7b",
        ),
        (lambda m: m["regimes"].update(bear={"trades": 30, "profit_factor": 0.79}), "T8"),
        (lambda m: m.update(variants=[0.1, -0.1, -0.2, 0.3]), "T9"),
        (lambda m: m.update(bias_clean=None), "T10"),
    ],
)
def test_each_criterion_can_fail_independently(mutate, failed):
    m = _good()
    mutate(m)
    res = _passed(evaluate_criteria(m, CRIT))
    assert res[failed] is False
    assert [k for k, ok in res.items() if not ok] == [failed]


def test_regime_with_too_few_trades_is_not_judged_and_nan_never_passes():
    m = _good()
    m["regimes"]["bear"] = {"trades": 29, "profit_factor": 0.1}
    assert _passed(evaluate_criteria(m, CRIT))["T8"] is True
    m["base"]["sortino"] = float("nan")
    assert _passed(evaluate_criteria(m, CRIT))["T3"] is False


# ------------------------------------------------------------------ windows
def test_calendar_windows_full_partial_and_dropped():
    w = calendar_windows("2021-01-01", "2022-07-01", 6)
    assert [(str(a.date()), str(b.date())) for a, b in w][-1] == ("2022-01-01", "2022-07-01")
    assert len(w) == 3
    assert len(calendar_windows("2021-01-01", "2021-10-01", 6)) == 2  # 3-month tail kept
    assert len(calendar_windows("2021-01-01", "2021-08-01", 6)) == 1  # 1-month tail dropped


def test_window_stats_returns_and_profit():
    idx = pd.date_range("2021-01-01", "2021-07-01", freq="1h", inclusive="left", tz="UTC")
    eq = pd.Series(np.linspace(1000, 1100, len(idx)), index=idx)
    (w,) = window_stats(eq, calendar_windows("2021-01-01", "2021-07-01", 6), 1000.0)
    assert w["profit"] == pytest.approx(eq.iloc[-1] - 1000.0)
    assert w["return"] == pytest.approx(eq.iloc[-1] / 1000.0 - 1.0)


# ------------------------------------------------------------------ regimes
def _btc_daily_trend(n_days: int, slope: float) -> pd.DataFrame:
    n = n_days * 24
    px = 100.0 + slope * np.arange(n) + np.sin(np.arange(n)) * 0.2
    return pd.DataFrame(
        {
            "date": pd.date_range("2021-01-01", periods=n, freq="1h", tz="UTC"),
            "open": px,
            "high": px + 0.3,
            "low": px - 0.3,
            "close": px,
            "volume": 1.0,
        }
    )


def test_daily_regimes_bull_bear_and_applied_with_one_day_delay():
    bull = daily_regimes(_btc_daily_trend(400, 0.05))
    assert bull.iloc[-1] == "bull"
    assert daily_regimes(_btc_daily_trend(400, -0.05)).iloc[-1] == "bear"

    day = bull.index[-1]
    trades = pd.DataFrame({"open_date": [day + pd.Timedelta("5h")]})
    assert trade_regimes(trades, bull).iloc[0] == bull.loc[day - pd.Timedelta("1D")]  # D-1, not D


def test_regime_stats_groups_trades():
    labels = pd.Series(
        ["bull", "bear"], index=pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True)
    )
    trades = pd.DataFrame(
        {
            "open_date": pd.to_datetime(
                ["2024-01-02 03:00", "2024-01-03 03:00", "2024-03-01 00:00"], utc=True
            ),
            "profit_abs": [10.0, -5.0, 1.0],
            "profit_ratio": [0.1, -0.05, 0.01],
        }
    )
    s = regime_stats(trades, labels)
    assert s["bull"]["trades"] == 1 and s["bear"]["trades"] == 1 and s["unknown"]["trades"] == 1
    assert s["bear"]["profit_factor"] == pytest.approx(0.0)


def test_pair_profit_shares():
    t = pd.DataFrame({"pair": ["A", "A", "B"], "profit_abs": [30.0, 20.0, 50.0]})
    assert pair_profit_shares(t) == {"A": 0.5, "B": 0.5}
    assert pair_profit_shares(pd.DataFrame({"pair": ["A"], "profit_abs": [-1.0]})) == {}


# ------------------------------------------------------------------ uncertainty
def test_bootstrap_is_reproducible_and_brackets_the_estimate():
    rng = np.random.default_rng(0)
    profits = rng.normal(0.5, 3.0, 400)
    a = bootstrap_ci(profits, profit_factor, n=500, seed=1)
    assert a == bootstrap_ci(profits, profit_factor, n=500, seed=1)
    assert a[0] < profit_factor(profits) < a[1]
    assert all(math.isnan(x) for x in bootstrap_ci(np.array([1.0]), profit_factor, 10, 1))


def test_block_bootstrap_paired_difference():
    rng = np.random.default_rng(2)
    base = rng.normal(0.0005, 0.02, 500)
    strat = base + 0.001  # strictly better by a constant: difference CI must exclude 0

    def diff(a, b):
        return sharpe(a) - sharpe(b)

    lo, hi = block_bootstrap_ci([strat, base], diff, n=300, seed=3, block=10)
    assert 0 < lo < hi
    assert all(math.isnan(x) for x in block_bootstrap_ci([base[:15]], sharpe, 10, 1, block=10))


def test_regimes_on_random_walk_run_without_error():
    labels = daily_regimes(random_walk_ohlcv(24 * 400, seed=5))
    assert set(labels.unique()) <= {"bull", "bear", "sideways", "unknown"}
