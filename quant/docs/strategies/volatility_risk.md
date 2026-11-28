# Shared component — volatility-scaled position size (`atr_stake_fraction`)

**Purpose.** Risk the same fraction of equity on each trade regardless of how volatile the pair
is. Wild pairs get smaller positions, calm pairs larger ones, with a hard cap.

**Formula.** Stop distance = `stop_atr_mult × atr_pct` (ATR as a fraction of price).
`fraction = risk_per_trade / (stop_atr_mult × atr_pct)`, capped at `max_fraction`;
invalid input (NaN, ≤ 0, non-numeric) → 0.0.

| Parameter | Fixed value | Allowed range |
|---|---|---|
| `risk_per_trade` | 1 % of equity | 0.5–2 % |
| `stop_atr_mult` | 2.0 | 1.5–3.0 |
| `max_fraction` | 0.33 (one third of equity per position) | ≤ 0.33 (hard rule) |

Worked example (arithmetic, not market data): ATR 2 % of price, mult 2 → stop 4 % → fraction
0.01 / 0.04 = 0.25. ATR 0.5 % → 1.0, capped to 0.33.

**Status.** Pure function with unit tests only. The Phase 2 strategies still use the fixed -10 %
stoploss and the config stake; wiring into `custom_stake_amount` / `custom_stoploss` is Phase 4.

**Failure modes.** ATR lags volatility spikes (position too large at the start of a crash);
stops can gap through on illiquid pairs so realised loss exceeds the budget; capping makes
risk per trade smaller than 1 % in calm markets (intended).

**Verified by unit test:** inverse scaling with volatility; loss at the stop equals the risk
budget; cap applied; invalid inputs return 0.0.
