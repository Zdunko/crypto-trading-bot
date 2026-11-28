# Strategy specifications (Phase 2)

Written **before** any backtest. Parameter values below are fixed priors from common practice,
not fitted to data. The "allowed range" column is used only for the Phase 3 sensitivity check
(does the result survive nearby values?), never to pick the best value.

| Spec | Code | Role |
|---|---|---|
| [trend_ema_cross](trend_ema_cross.md) | `strategies/trend_ema_cross.py` | Trend following |
| [mean_reversion_rsi_bb](mean_reversion_rsi_bb.md) | `strategies/mean_reversion_rsi_bb.py` | Mean reversion |
| [breakout_donchian](breakout_donchian.md) | `strategies/breakout_donchian.py` | Breakout |
| [momentum_roc](momentum_roc.md) | `strategies/momentum_roc.py` | Momentum |
| [regime_filter](regime_filter.md) | `strategies/quant_common.py::market_regime` | Shared regime component |
| [volatility_risk](volatility_risk.md) | `strategies/quant_common.py::atr_stake_fraction` | Shared risk component |
| [phase3_validation_thresholds](phase3_validation_thresholds.md) | `protocol/protocol.json` | **Frozen v2** pass/fail protocol |
| — | `strategies/buy_and_hold.py` | In-framework benchmark (not tradable) |

Common to all strategies: spot, long only, 1h candles, no position averaging, no leverage,
ROI exit disabled (`minimal_roi = {"0": 100}`), fixed `stoploss = -0.10` (same for all, for
comparability), all signals evaluated on **closed** candles, `max_open_trades` from config.
Round-trip cost assumption: **0.30 %** (0.15 % per side, see `configs/backtest.json`); every
strategy's average gross profit per trade must clearly exceed it to be worth anything.

Status of every claim in these specs: **hypothesis** unless it says *verified by unit test*.
No market-data result exists yet.
