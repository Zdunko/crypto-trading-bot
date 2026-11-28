"""
Shared building blocks for the project strategies.

Pure pandas / TA-Lib functions: no Freqtrade imports, causal only (a value at row ``t``
depends on rows ``<= t``). Lives next to the strategies so that
``--strategy-path quant/strategies`` works without any extra PYTHONPATH.
"""

from __future__ import annotations

import math

import pandas as pd
import talib


REGIME_BULL = "bull"
REGIME_BEAR = "bear"
REGIME_SIDEWAYS = "sideways"
REGIME_UNKNOWN = "unknown"  # indicators not yet defined (warm-up)


def market_regime(
    dataframe: pd.DataFrame,
    ema_period: int = 200,
    adx_period: int = 14,
    adx_trend: float = 25.0,
) -> pd.Series:
    """
    Classify every candle as bull / bear / sideways / unknown.

    trending = ADX >= ``adx_trend``; bull = trending and close above EMA; bear = trending and
    close below EMA; sideways = not trending. Rows where an indicator is still undefined
    are ``unknown`` and must never be traded.
    """
    close = dataframe["close"]
    ema = talib.EMA(close, timeperiod=ema_period)
    adx = talib.ADX(dataframe["high"], dataframe["low"], close, timeperiod=adx_period)
    trending = adx >= adx_trend

    regime = pd.Series(REGIME_SIDEWAYS, index=dataframe.index, dtype="object")
    regime[trending & (close > ema)] = REGIME_BULL
    regime[trending & (close < ema)] = REGIME_BEAR
    regime[ema.isna() | adx.isna()] = REGIME_UNKNOWN
    return regime


def atr_stake_fraction(
    atr_pct: float,
    risk_per_trade: float = 0.01,
    stop_atr_mult: float = 2.0,
    max_fraction: float = 0.33,
) -> float:
    """
    Volatility-scaled position size as a fraction of equity.

    The stop sits ``stop_atr_mult * atr_pct`` below entry, so a position of fraction ``f``
    loses ``f * stop_atr_mult * atr_pct`` of equity if stopped. Solving for the loss budget
    ``risk_per_trade`` gives ``f``. Capped at ``max_fraction``; returns 0.0 for any invalid
    input (never size up on bad data).
    """
    values = (atr_pct, risk_per_trade, stop_atr_mult, max_fraction)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        return 0.0
    if atr_pct <= 0 or risk_per_trade <= 0 or stop_atr_mult <= 0 or max_fraction <= 0:
        return 0.0
    return min(risk_per_trade / (stop_atr_mult * atr_pct), max_fraction)
