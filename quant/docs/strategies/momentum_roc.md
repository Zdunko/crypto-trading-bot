# Momentum — `MomentumRoc`

**Hypothesis.** Assets with strong positive trailing returns keep outperforming for a while
(time-series momentum); requiring price above a long EMA filters weak bounces.

**Rules** (closed 1h candles, long only)
- `ROC = close / close[240 candles ago] − 1`.
- Entry: `ROC > 5 %` **and** `close > EMA(200)`.
- Exit: `ROC < 0`, or stoploss -10 %.
- Warm-up: 600 candles.

| Parameter | Fixed value | Allowed range (sensitivity only) |
|---|---|---|
| `roc_lookback` | 240 (10 days) | 120–480 |
| `roc_threshold` | 0.05 | 0.02–0.10 |
| `ema_trend_period` | 200 | 100–300 |

**Favourable:** persistent trends with orderly pullbacks. **Unfavourable:** sharp reversals
("momentum crashes") after a long run-up; V-shaped markets.

**Failure modes.** Entry condition holds on many consecutive candles, so re-entry right after a
stop-out is possible (capital churn; **no cooldown yet** — a protection to evaluate in Phase 4);
ROC exit at 0 is slow after a spike up.

**Cost sensitivity.** Moderate; churn after stops is the risk.

**Verified by unit test (synthetic data):** entry needs both conditions; exit when ROC < 0; ROC
equals its definition on a hand-checked candle; causality.
