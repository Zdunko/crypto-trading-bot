# M4 (L2) pre-registration report — written and frozen BEFORE any hourly data was fetched or any L2 result existed

Registration: `protocol/m4_l2_preregistration.json` (spec sha256 `8f18168550ca9af879296c2de2655be36ac8a5bc4b786da610968b749d9c7435`), owner approval record `protocol/m4_owner_approval.json`, amendments A15 (ledger) and A16 (budget caps/approvals; earlier freeze records unedited).

## What will be evaluated (no new hypothesis, no new configuration)
The two registered configurations (7- and 28-day horizons) as long-only spot portfolios: top quintile of S = -MAX3 among valid point-in-time members, equal notional, rebalanced every h days, signal of day D-1 used at 01:00 UTC on day D (one hour latency), frozen Stage 0 engine on hourly candles (fee 0.10 % + slippage 0.05 % per side; double: 0.20 % + 0.10 %; 10 % participation cap with partial fills; 3-candle deferral; minimum notional 5), Risk Management V3 with zero recovery and the frozen engine breaker. No averaging: survivors are not topped up. Spread is not observable in klines; it sits inside the scenario slippage and the double scenario doubles it. Wallet 10,000 USDT.

Comparators: cash, BTC buy-and-hold, point-in-time equal weight (monthly), ex-post risk-matched BTC/cash mix (non-tradable), and a low-volatility portfolio built exactly like the strategy from the lowest 28-day realised volatility (same K, rebalance, execution, V3) for the incremental-value test.

Acceptance (per configuration, all must hold; NOT T1-T10): A1 net return > 0 under normal and double costs; A2 Sortino >= BTC and equal weight; A3 max drawdown <= 20 % and not above BTC; A4 V3 never reaches SHUTDOWN; A5 paired net daily return difference vs the low-volatility portfolio positive with one-sided HAC p <= 0.05; A6 filled/intended buy notional >= 0.95. The unprotected portfolio (no V3, no breaker) is a non-gating diagnostic.

Verification diagnostics (inside the same single replay, never changing a verdict): V1 independent pandas re-implementation of signal, returns and IC (tolerance 1e-9); V2 within-day permutation placebo (100 permutations) and one-day-delayed entry; V3 survivorship split (assets that still print in the last 30 days); V4 liquid vs illiquid half (trailing 90-day median quote volume).

## Budget
N stays 45 of 52. The approved protocol (section 8) allows one market run per family plus one approved diagnostic replay per family; the single L1 run is consumed and this M4 programme is the family's one approved replay (recorded as `diagnostic_replays_used` 0 -> 1 after the run). **Interpretation, recorded openly:** if the owner reads "additional diagnostic experiments" as covering this replay, the run must not be executed; it adds no configuration and no hypothesis.

## Synthetic validation (before registration; 18 tests, `tests/test_l2_portfolio.py`)
Causal and prefix-invariant target schedule; tie rules; one-hour latency; closed-form cost drag on flat prices (normal and double); no averaging; participation cap and partial fills; V3 flattening in a crash versus the unprotected run; zero-recovery write-off and shutdown for a delisted holding; passive-equity and metric closed forms; paired test and alpha regression recovering a planted edge and the null; every acceptance criterion flips the decision; independent re-implementation equals the registered IC (1e-9) with gaps and delistings; placebo; guard; end-to-end determinism. One defect was found and fixed before registration: the delisting status feed stamped the event 24 hours too early (the epoch table's `end_ms` is the open of the last daily candle); the feed now stamps last-candle-end + 48 h.

## Known limitations (registered)
Research-only data; no order book (spread/impact inside the scenario slippage); one-hour latency is a model; a 10,000 USDT account (capacity at larger size untested); the L1 signal is largely a low-volatility signal (the comparison with the low-volatility portfolio tests exactly this); passive comparators use daily accounting without partial fills; epoch-table semantics mean the signal is not computed on an asset's final candle day (conservative). No L3, no forward test, no T1-T10 claim.
