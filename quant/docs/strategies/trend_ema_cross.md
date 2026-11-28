# Trend following — `TrendEmaCross`

**Hypothesis.** Crypto returns show positive serial correlation over days to weeks (trends), so
holding while a fast EMA is above a slow EMA captures part of large moves and avoids part of
bear markets.

**Rules** (closed 1h candles, long only)
- Entry: `EMA(24)` crosses above `EMA(120)` (fast > slow now, fast ≤ slow on the previous candle).
- Exit: `EMA(24) < EMA(120)`, or stoploss -10 %.
- Warm-up: 400 candles (EMA(120) converges in ~3–4 periods).

| Parameter | Fixed value | Allowed range (sensitivity only) |
|---|---|---|
| `ema_fast_period` | 24 (1 day) | 12–48 |
| `ema_slow_period` | 120 (5 days) | 72–200 |

**Favourable:** sustained directional markets (bull runs, strong bear-to-bull transitions).
**Unfavourable:** sideways, choppy markets — repeated cross/whipsaw entries, each paying 0.30 %.

**Failure modes.** Lag: enters late and exits after a large part of the move is gone; many small
losses in ranges with few large wins (low win rate is expected, so judge by expectancy and
profit factor, not win rate); gap/flash moves can skip the -10 % stop.

**Cost sensitivity.** Trade count is low (crossovers only). Whipsaw clusters in ranges are the
main cost driver. Stress test at 2× costs (0.60 % round trip).

**Verified by unit test (synthetic data):** entry only on the crossing candle; exit while fast <
slow; no signals while EMAs undefined; signals unchanged when future candles are removed.
