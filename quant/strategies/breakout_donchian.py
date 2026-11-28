"""Breakout: buy a close above the prior N-bar high on high volume, exit below the prior low."""

from freqtrade.strategy import IStrategy
from pandas import DataFrame


class BreakoutDonchian(IStrategy):
    """Spec: quant/docs/strategies/breakout_donchian.md. Parameters are fixed, not tuned."""

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
    startup_candle_count = 100

    channel_period = 48
    exit_period = 24
    volume_mult = 1.5

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # shift(1): the channel only contains candles that closed BEFORE the current one.
        dataframe["channel_high"] = dataframe["high"].rolling(self.channel_period).max().shift(1)
        dataframe["channel_low"] = dataframe["low"].rolling(self.exit_period).min().shift(1)
        dataframe["volume_avg"] = dataframe["volume"].rolling(self.channel_period).mean().shift(1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        breakout = dataframe["close"] > dataframe["channel_high"]
        strong = dataframe["volume"] > self.volume_mult * dataframe["volume_avg"]
        dataframe["enter_long"] = 0
        dataframe.loc[breakout & strong & (dataframe["volume"] > 0), "enter_long"] = 1
        dataframe.loc[dataframe["enter_long"] == 1, "enter_tag"] = "donchian_breakout"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        broke_down = dataframe["close"] < dataframe["channel_low"]
        dataframe["exit_long"] = 0
        dataframe.loc[broke_down & (dataframe["volume"] > 0), "exit_long"] = 1
        dataframe.loc[dataframe["exit_long"] == 1, "exit_tag"] = "donchian_breakdown"
        return dataframe
