"""Benchmark: buy on the first possible candle and never sell. Not a tradable strategy."""

from freqtrade.strategy import IStrategy
from pandas import DataFrame


class BuyAndHold(IStrategy):
    """
    In-framework buy-and-hold reference for Freqtrade backtests (limited by max_open_trades).
    The Phase 3 benchmark is an equal-weight buy-and-hold computed over ALL pairs from OHLCV.
    The wide stoploss is deliberate and this class is the only entry in BENCHMARK_ALLOWLIST
    of quantlab.strategy_policy.
    """

    INTERFACE_VERSION = 3

    can_short = False
    position_adjustment_enable = False
    timeframe = "1h"
    minimal_roi = {"0": 100}
    stoploss = -0.99
    trailing_stop = False
    use_exit_signal = False
    startup_candle_count = 0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe.loc[dataframe["volume"] > 0, "enter_long"] = 1
        dataframe.loc[dataframe["enter_long"] == 1, "enter_tag"] = "buy_and_hold"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe
