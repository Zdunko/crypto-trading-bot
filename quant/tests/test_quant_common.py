"""Tests for the shared regime filter and the volatility-based sizing component."""

import math

import numpy as np
import pandas as pd
import pytest
from quant_common import (
    REGIME_BEAR,
    REGIME_BULL,
    REGIME_SIDEWAYS,
    REGIME_UNKNOWN,
    atr_stake_fraction,
    market_regime,
)
from synth import random_walk_ohlcv


def _trend_frame(direction: float, n: int = 600) -> pd.DataFrame:
    close = 100.0 + direction * np.arange(n) * 0.5 + np.sin(np.arange(n)) * 0.2
    return pd.DataFrame({"close": close, "high": close + 0.3, "low": close - 0.3})


def test_warmup_rows_are_unknown_and_never_tradable():
    regime = market_regime(_trend_frame(1.0))
    assert (regime.iloc[:30] == REGIME_UNKNOWN).all()
    assert regime.iloc[-1] != REGIME_UNKNOWN


def test_strong_uptrend_is_bull_and_downtrend_is_bear():
    assert market_regime(_trend_frame(1.0)).iloc[-1] == REGIME_BULL
    assert market_regime(_trend_frame(-1.0)).iloc[-1] == REGIME_BEAR


def test_flat_oscillation_is_sideways():
    n = 600
    close = 100.0 + np.sin(np.arange(n) * 0.9) * 0.5
    df = pd.DataFrame({"close": close, "high": close + 0.2, "low": close - 0.2})
    assert market_regime(df).iloc[-1] == REGIME_SIDEWAYS


def test_regime_is_causal():
    df = random_walk_ohlcv(900)
    full = market_regime(df)
    cut = market_regime(df.iloc[:600])
    assert full.iloc[:600].tolist() == cut.tolist()


def test_atr_stake_scales_inversely_with_volatility():
    calm = atr_stake_fraction(0.005, risk_per_trade=0.01, stop_atr_mult=2.0, max_fraction=1.0)
    wild = atr_stake_fraction(0.02, risk_per_trade=0.01, stop_atr_mult=2.0, max_fraction=1.0)
    assert calm == pytest.approx(1.0)
    assert wild == pytest.approx(0.25)
    assert wild < calm


def test_atr_stake_loss_at_stop_equals_risk_budget():
    atr_pct, mult, risk = 0.02, 2.0, 0.01
    fraction = atr_stake_fraction(atr_pct, risk, mult, max_fraction=1.0)
    assert fraction * mult * atr_pct == pytest.approx(risk)


def test_atr_stake_is_capped():
    assert atr_stake_fraction(0.0001, max_fraction=0.33) == 0.33


@pytest.mark.parametrize("bad", [0.0, -0.01, math.nan, math.inf, None, "x"])
def test_atr_stake_invalid_input_sizes_to_zero(bad):
    assert atr_stake_fraction(bad) == 0.0
