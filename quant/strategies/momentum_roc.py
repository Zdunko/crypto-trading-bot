"""Momentum: hold while the trailing return is strongly positive and price is above its EMA."""

import talib
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class MomentumRoc(IStrategy):
    """Spec: quant/docs/strategies/momentum_roc.md. Parameters are fixed, not tuned."""

    INTERFACE_VERSION = 3

    can_short = False
    position_adjustment_enable = False
    timeframe = "1h"
    minimal_roi = {"0": 100}
    stoploss = -0.10
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    startup_candle_count = 600

    roc_lookback = 240  # 10 days of 1h candles
    roc_threshold = 0.05
    ema_trend_period = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        dataframe["roc"] = close / close.shift(self.roc_lookback) - 1.0
        dataframe["ema_trend"] = talib.EMA(close, timeperiod=self.ema_trend_period)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        strong = dataframe["roc"] > self.roc_threshold
        uptrend = dataframe["close"] > dataframe["ema_trend"]
        dataframe["enter_long"] = 0
        dataframe.loc[strong & uptrend & (dataframe["volume"] > 0), "enter_long"] = 1
        dataframe.loc[dataframe["enter_long"] == 1, "enter_tag"] = "roc_strong_uptrend"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        lost = dataframe["roc"] < 0
        dataframe["exit_long"] = 0
        dataframe.loc[lost & (dataframe["volume"] > 0), "exit_long"] = 1
        dataframe.loc[dataframe["exit_long"] == 1, "exit_tag"] = "roc_negative"
        return dataframe
