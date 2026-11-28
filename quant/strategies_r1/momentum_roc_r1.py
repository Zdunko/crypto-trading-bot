"""R1 = MomentumRoc (rules unchanged) + the Phase 4 risk overlay (see quant_risk.py, protocol v3)."""

from freqtrade.strategy import IStrategy
from momentum_roc import MomentumRoc
from quant_risk import RiskOverlayMixin


class MomentumRocR1(RiskOverlayMixin, MomentumRoc, IStrategy):
    """Entry/exit rules come from MomentumRoc; sizing, exposure, filters and stops from the overlay."""

    INTERFACE_VERSION = 3

    can_short = False
    position_adjustment_enable = False
    stoploss = -0.25  # emergency floor only; the effective stop is the ATR chandelier
    use_custom_stoploss = True
    startup_candle_count = (
        600  # exchange limit: 5 OHLCV calls per pair; BTC regime history is read separately
    )
