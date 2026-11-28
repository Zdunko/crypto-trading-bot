# Mean reversion — `MeanReversionRsiBb`

**Hypothesis.** In non-trending (sideways) markets, short-term oversold extremes revert to the
mean. Restricting to a sideways regime avoids "catching a falling knife" in trends.

**Rules** (closed 1h candles, long only)
- Entry: `RSI(14) < 30` **and** `close < lower Bollinger band(20, 2σ)` **and** regime == sideways
  (`ADX(14) < 25`, see [regime_filter](regime_filter.md)).
- Exit: `close > Bollinger middle band` (the mean), or stoploss -10 %.
- Warm-up: 600 candles (the regime component contains EMA(200)).

| Parameter | Fixed value | Allowed range (sensitivity only) |
|---|---|---|
| `rsi_entry` | 30 | 20–35 |
| `bb_period` | 20 | 14–30 |
| `adx_max` | 25 | 20–30 |

Conventions, not free parameters: RSI(14), ADX(14), band width 2σ.

**Favourable:** range-bound markets with stable volatility. **Unfavourable:** regime shifts and
crashes (ADX is lagging: a trend can start before ADX rises), news-driven capitulation.

**Failure modes.** Small average win vs. occasional large loss (negative skew); stops of -10 %
hit during crashes; exits at the mean can be shorter than the 0.30 % round-trip cost.
**Observation on synthetic random walks only (not market data):** entries occur on ~0.33 % of
candles, so the strategy may produce **too few trades** to validate — Phase 3 must check the
minimum-trades threshold before interpreting any return.

**Cost sensitivity.** High: small expected move per trade. Must be stressed at 2× costs.

**Verified by unit test (synthetic data):** needs all three conditions; trending/unknown regimes
never trade; exit above the middle band; causality; warm-up silence.
