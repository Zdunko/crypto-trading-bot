"""Trend following: long when the fast EMA crosses above the slow EMA, exit on the cross back."""

import talib
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class TrendEmaCross(IStrategy):
    """Spec: quant/docs/strategies/trend_ema_cross.md. Parameters are fixed, not tuned."""

    INTERFACE_VERSION = 3

    can_short = False
    position_adjustment_enable = False
    timeframe = "1h"
    minimal_roi = {"0": 100}  # ROI exit disabled: exits come from the signal or the stoploss
    stoploss = -0.10
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    startup_candle_count = 400

    ema_fast_period = 24
    ema_slow_period = 120

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        dataframe["ema_fast"] = talib.EMA(close, timeperiod=self.ema_fast_period)
        dataframe["ema_slow"] = talib.EMA(close, timeperiod=self.ema_slow_period)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast, slow = dataframe["ema_fast"], dataframe["ema_slow"]
        crossed_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        dataframe["enter_long"] = 0
        dataframe.loc[crossed_up & (dataframe["volume"] > 0), "enter_long"] = 1
        dataframe.loc[dataframe["enter_long"] == 1, "enter_tag"] = "ema_cross_up"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        below = dataframe["ema_fast"] < dataframe["ema_slow"]
        dataframe["exit_long"] = 0
        dataframe.loc[below & (dataframe["volume"] > 0), "exit_long"] = 1
        dataframe.loc[dataframe["exit_long"] == 1, "exit_tag"] = "ema_cross_down"
        return dataframe
