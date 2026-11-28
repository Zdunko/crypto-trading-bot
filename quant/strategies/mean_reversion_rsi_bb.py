"""Mean reversion: buy oversold dips below the lower Bollinger band, only in a sideways regime."""

import talib
from freqtrade.strategy import IStrategy
from pandas import DataFrame
from quant_common import REGIME_SIDEWAYS, market_regime


class MeanReversionRsiBb(IStrategy):
    """Spec: quant/docs/strategies/mean_reversion_rsi_bb.md. Parameters are fixed, not tuned."""

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
    startup_candle_count = 600  # EMA(200) inside the regime filter needs ~3x its period

    rsi_entry = 30
    bb_period = 20
    adx_max = 25
    # Conventions (not free parameters): RSI(14), ADX(14), Bollinger width 2 sigma.

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        dataframe["rsi"] = talib.RSI(close, timeperiod=14)
        _upper, middle, lower = talib.BBANDS(
            close, timeperiod=self.bb_period, nbdevup=2.0, nbdevdn=2.0
        )
        dataframe["bb_lower"] = lower
        dataframe["bb_middle"] = middle
        dataframe["regime"] = market_regime(dataframe, adx_trend=self.adx_max)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dip = (dataframe["rsi"] < self.rsi_entry) & (dataframe["close"] < dataframe["bb_lower"])
        sideways = dataframe["regime"] == REGIME_SIDEWAYS
        dataframe["enter_long"] = 0
        dataframe.loc[dip & sideways & (dataframe["volume"] > 0), "enter_long"] = 1
        dataframe.loc[dataframe["enter_long"] == 1, "enter_tag"] = "oversold_sideways"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        reverted = dataframe["close"] > dataframe["bb_middle"]
        dataframe["exit_long"] = 0
        dataframe.loc[reverted & (dataframe["volume"] > 0), "exit_long"] = 1
        dataframe.loc[dataframe["exit_long"] == 1, "exit_tag"] = "back_to_mean"
        return dataframe
