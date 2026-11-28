# Breakout — `BreakoutDonchian`

**Hypothesis.** A close above the prior N-bar high, confirmed by unusually high volume, marks the
start of a volatility expansion that tends to continue.

**Rules** (closed 1h candles, long only)
- Channel uses only candles **before** the current one (`shift(1)`).
- Entry: `close > highest high of the previous 48 candles` **and**
  `volume > 1.5 × mean volume of the previous 48 candles`.
- Exit: `close < lowest low of the previous 24 candles`, or stoploss -10 %.
- Warm-up: 100 candles.

| Parameter | Fixed value | Allowed range (sensitivity only) |
|---|---|---|
| `channel_period` | 48 (2 days) | 24–96 |
| `exit_period` | 24 (1 day) | 12–48 |
| `volume_mult` | 1.5 | 1.0–2.0 |

**Favourable:** transitions from low to high volatility with follow-through.
**Unfavourable:** false breakouts in ranges ("fake-outs"), thin-liquidity spikes.

**Failure modes.** Buying local tops that immediately revert; the volume filter is noisy on
illiquid pairs; entry occurs after the move has started (slippage above the 0.05 % buffer is
likely on breakout candles — **assumption that must be stress-tested**).

**Cost sensitivity.** Moderate trade count; slippage matters more than fees because entries are
by construction at local extremes.

**Verified by unit test (synthetic data):** entry needs new high **and** volume confirmation;
the channel excludes the current candle (checked against a manual window); exit rule; causality.
