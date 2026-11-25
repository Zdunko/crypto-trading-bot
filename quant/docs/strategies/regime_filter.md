# Shared component — market regime filter (`market_regime`)

**Purpose.** (1) Gate mean reversion to sideways markets. (2) Segment Phase 3 results into
bull / bear / sideways so a strategy cannot hide a failure in one regime behind another.

**Definition** (closed candles, causal)
- `trending = ADX(14) >= 25`.
- bull = trending and `close > EMA(200)`; bear = trending and `close < EMA(200)`;
  sideways = not trending; unknown = indicators still in warm-up (never traded).

| Parameter | Fixed value | Allowed range (sensitivity only) |
|---|---|---|
| `adx_trend` | 25 | 20–30 |
| `ema_period` | 200 | 100–300 |

**Limitations.** Lagging by construction; thresholds are conventions, not estimates; near the ADX
threshold the label flips often (whipsaw). For Phase 3 segmentation the regime should be computed
on a **market proxy (BTC/USDT)** and applied to all pairs; per-pair regimes are used inside
strategies only.

**Verified by unit test:** warm-up rows are `unknown`; synthetic strong up/down trends map to
bull/bear; flat oscillation is sideways; the regime at row t is identical with or without
future candles.
