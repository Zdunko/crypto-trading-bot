"""
Signal logic, warm-up safety and causality of every project strategy.

All data is synthetic. These tests prove the rules do what the specs say and that no
signal depends on future candles; they say nothing about profitability.
"""

import numpy as np
import pandas as pd
import pytest
from breakout_donchian import BreakoutDonchian
from buy_and_hold import BuyAndHold
from mean_reversion_rsi_bb import MeanReversionRsiBb
from momentum_roc import MomentumRoc
from synth import random_walk_ohlcv
from trend_ema_cross import TrendEmaCross


META = {"pair": "BTC/USDT"}
SIGNAL_STRATEGIES = [TrendEmaCross, MeanReversionRsiBb, BreakoutDonchian, MomentumRoc]
ALL_STRATEGIES = [*SIGNAL_STRATEGIES, BuyAndHold]


def _run(strategy, df: pd.DataFrame) -> pd.DataFrame:
    out = strategy.populate_indicators(df.copy(), META)
    out = strategy.populate_entry_trend(out, META)
    return strategy.populate_exit_trend(out, META)


def _entries(strategy, frame: dict) -> list[int]:
    df = pd.DataFrame(frame)
    return strategy.populate_entry_trend(df, META)["enter_long"].astype(int).tolist()


def _exits(strategy, frame: dict) -> list[int]:
    df = pd.DataFrame(frame)
    return strategy.populate_exit_trend(df, META)["exit_long"].astype(int).tolist()


@pytest.fixture(scope="module")
def data() -> pd.DataFrame:
    return random_walk_ohlcv(1800, seed=11)


# ---------------------------------------------------------------- structure (all)
@pytest.mark.parametrize("cls", ALL_STRATEGIES)
def test_spot_long_only_no_averaging(cls):
    s = cls({})
    assert s.can_short is False
    assert s.position_adjustment_enable is False
    assert -0.99 <= s.stoploss < 0
    assert s.timeframe == "1h"
    assert s.minimal_roi == {"0": 100}  # ROI exit effectively disabled


# ---------------------------------------------------------------- trend
def test_trend_enters_only_on_cross_up():
    nan = np.nan
    frame = {
        "ema_fast": [1, 1, 3, 3, 1, nan],
        "ema_slow": [2, 2, 2, 2, 2, 2],
        "volume": [1] * 6,
    }
    assert _entries(TrendEmaCross({}), frame) == [0, 0, 1, 0, 0, 0]


def test_trend_exits_while_fast_below_slow():
    frame = {"ema_fast": [1, 3, 3, 1], "ema_slow": [2, 2, 2, 2], "volume": [1] * 4}
    assert _exits(TrendEmaCross({}), frame) == [1, 0, 0, 1]


def test_trend_ignores_zero_volume_candles():
    frame = {"ema_fast": [1, 3], "ema_slow": [2, 2], "volume": [1, 0]}
    assert _entries(TrendEmaCross({}), frame) == [0, 0]


# ---------------------------------------------------------------- mean reversion
def _mr_frame(**over):
    base = {
        "rsi": [25, 25, 35, 25, 25],
        "close": [90, 90, 90, 96, 90],
        "bb_lower": [95, 95, 95, 95, 95],
        "bb_middle": [100] * 5,
        "regime": ["sideways", "bull", "sideways", "sideways", "unknown"],
        "volume": [1] * 5,
    }
    base.update(over)
    return base


def test_mean_reversion_needs_oversold_below_band_and_sideways_regime():
    # row0 ok | row1 trending regime | row2 RSI not oversold | row3 inside band | row4 warm-up
    assert _entries(MeanReversionRsiBb({}), _mr_frame()) == [1, 0, 0, 0, 0]


def test_mean_reversion_exits_above_middle_band():
    frame = _mr_frame(close=[99, 100, 101, 120, 90])
    assert _exits(MeanReversionRsiBb({}), frame) == [0, 0, 1, 1, 0]


def test_mean_reversion_never_trades_bear_or_bull_regimes():
    frame = _mr_frame(regime=["bear", "bull", "bear", "bull", "bear"])
    assert sum(_entries(MeanReversionRsiBb({}), frame)) == 0


# ---------------------------------------------------------------- breakout
def test_breakout_needs_new_high_and_volume_confirmation():
    nan = np.nan
    frame = {
        "close": [101, 101, 99, 101, 101],
        "channel_high": [100, 100, 100, nan, 100],
        "volume_avg": [100, 100, 100, 100, nan],
        "volume": [200, 140, 200, 200, 200],  # row1 below 1.5x average
    }
    assert _entries(BreakoutDonchian({}), frame) == [1, 0, 0, 0, 0]


def test_breakout_exits_below_channel_low_only():
    frame = {"close": [95, 100, 105, np.nan], "channel_low": [96, 96, 96, 96], "volume": [1] * 4}
    assert _exits(BreakoutDonchian({}), frame) == [1, 0, 0, 0]


def test_breakout_channel_excludes_current_candle():
    df = random_walk_ohlcv(300, seed=3)
    out = BreakoutDonchian({}).populate_indicators(df.copy(), META)
    manual = df["high"].iloc[100:148].max()  # candles 100..147 form the channel for row 148
    assert out["channel_high"].iloc[148] == pytest.approx(manual)


# ---------------------------------------------------------------- momentum
def test_momentum_needs_strong_roc_and_uptrend():
    frame = {
        "roc": [0.06, 0.04, 0.06, np.nan],
        "close": [110, 110, 90, 110],
        "ema_trend": [100, 100, 100, 100],
        "volume": [1] * 4,
    }
    assert _entries(MomentumRoc({}), frame) == [1, 0, 0, 0]


def test_momentum_exits_when_roc_turns_negative():
    frame = {"roc": [0.1, 0.0, -0.01, np.nan], "volume": [1] * 4}
    assert _exits(MomentumRoc({}), frame) == [0, 0, 1, 0]


def test_momentum_roc_matches_definition():
    df = random_walk_ohlcv(400, seed=5)
    out = MomentumRoc({}).populate_indicators(df.copy(), META)
    expected = df["close"].iloc[300] / df["close"].iloc[60] - 1.0
    assert out["roc"].iloc[300] == pytest.approx(expected)


# ---------------------------------------------------------------- buy and hold
def test_buy_and_hold_enters_every_tradable_candle_and_never_exits():
    df = random_walk_ohlcv(50)
    out = _run(BuyAndHold({}), df)
    assert out["enter_long"].sum() == 50
    assert out["exit_long"].sum() == 0
    assert BuyAndHold({}).use_exit_signal is False


# ---------------------------------------------------------------- cross-cutting
# Columns each rule reads. A signal must stay silent while ANY of its own inputs is NaN.
# (Entry and exit legitimately warm up at different speeds, e.g. 24- vs 48-bar channels.)
SIGNAL_INPUTS = {
    TrendEmaCross: (["ema_fast", "ema_slow"], ["ema_fast", "ema_slow"]),
    MeanReversionRsiBb: (["rsi", "bb_lower"], ["bb_middle"]),
    BreakoutDonchian: (["channel_high", "volume_avg"], ["channel_low"]),
    MomentumRoc: (["roc", "ema_trend"], ["roc"]),
}


@pytest.mark.parametrize("cls", SIGNAL_STRATEGIES)
def test_no_signals_while_their_inputs_are_undefined(cls, data):
    out = _run(cls({}), data)
    entry_cols, exit_cols = SIGNAL_INPUTS[cls]
    entry_undefined = out[entry_cols].isna().any(axis=1)
    exit_undefined = out[exit_cols].isna().any(axis=1)
    assert entry_undefined.any() and exit_undefined.any(), "test data has no warm-up window"
    assert out.loc[entry_undefined, "enter_long"].sum() == 0
    assert out.loc[exit_undefined, "exit_long"].sum() == 0


def test_mean_reversion_is_silent_in_unknown_regime(data):
    out = _run(MeanReversionRsiBb({}), data)
    assert (out["regime"] == "unknown").any()
    assert out.loc[out["regime"] == "unknown", "enter_long"].sum() == 0


@pytest.mark.parametrize("cls", SIGNAL_STRATEGIES)
def test_signals_are_causal_truncating_the_future_changes_nothing(cls, data):
    """Look-ahead bias check: signals up to row t must not depend on candles after t."""
    s = cls({})
    full = _run(s, data)
    for cut in (700, 1000, 1400):
        part = _run(s, data.iloc[:cut])
        for col in ("enter_long", "exit_long"):
            assert full[col].iloc[:cut].tolist() == part[col].tolist(), (cls.__name__, col, cut)


@pytest.mark.parametrize("cls", SIGNAL_STRATEGIES)
def test_startup_candle_count_covers_every_indicator_lookback(cls, data):
    """Indicators must be fully defined once the declared warm-up is over."""
    s = cls({})
    out = _run(s, data)
    tail = out.iloc[s.startup_candle_count :]
    cols = [c for c in out.columns if c not in data.columns and c != "regime"]
    cols = [c for c in cols if pd.api.types.is_numeric_dtype(out[c])]
    assert not tail[cols].isna().any().any()


@pytest.mark.parametrize("cls", SIGNAL_STRATEGIES)
def test_strategies_are_deterministic(cls, data):
    s = cls({})
    a, b = _run(s, data), _run(s, data)
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.parametrize("cls", SIGNAL_STRATEGIES)
def test_recursive_indicators_converge_within_declared_startup_candles(cls, data):
    """
    Offline analogue of `freqtrade recursive-analysis`: indicators computed from only
    `startup_candle_count` candles must match those computed from the full history.
    """
    s = cls({})
    full = _run(s, data)
    short = _run(s, data.tail(s.startup_candle_count + 1).reset_index(drop=True))
    cols = [c for c in full.columns if c not in data.columns and c not in SKIP_RECURSION_COLS]
    cols = [c for c in cols if pd.api.types.is_float_dtype(full[c])]
    assert cols
    for col in cols:
        a, b = full[col].iloc[-1], short[col].iloc[-1]
        assert abs(a - b) <= 1e-3 * max(abs(a), 1e-12), (cls.__name__, col, a, b)


SKIP_RECURSION_COLS = {"enter_long", "exit_long"}
