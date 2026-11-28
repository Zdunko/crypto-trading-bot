# S8 — Data and commercial feasibility (free, legally usable history)

Rule applied (pre-registered): only primary texts **actually read** count as verified; unreachable hosts are recorded as unverified; nothing is filled in from memory; research-only and commercially usable data are kept apart; nothing is purchased or contacted.

## Verification attempt (2026-11-27)
Three read-only fetch attempts covering 12 primary URLs failed before any page content was returned (`getaddrinfo ENOTFOUND`: the hosts are outside the session's network allowlist). No clause could be read.

| Source (primary URL attempted) | Result | Status |
|---|---|---|
| Kraken: support article "Downloadable historical OHLCVT data", /legal, /features/api | host not resolvable | **unverified** |
| Coinbase: /legal/market_data_terms, Exchange docs introduction | host not resolvable | **unverified** |
| FRED: series CBBTCUSD page and /legal/ | host not resolvable | **unverified** |
| Bitstamp: /api/, /terms-and-conditions/ | host not resolvable | **unverified** |
| OKX: docs-v5 and API agreement | host not resolvable | **unverified** |
| Bitfinex: docs introduction | host not resolvable | **unverified** |
| Binance Vision Dataset Terms v1.0 (read in S3) | full text read earlier | **verified**: research / personal non-production backtesting only |

The environment change that would allow these reads (adding the hosts to the network allowlist) is an owner decision; the alternative is that the owner pastes the current texts. Either costs nothing. Until then no source other than Binance Vision has a verified licence status.

## Classification
| Class | Data | Status | Consequence |
|---|---|---|---|
| Research-only (verified) | Binance Vision klines (current PIT dataset, 593 symbols, 2017-2025) | verified restriction | the whole existing research base cannot support a commercial-deployment claim; any strategy validated on it must be re-validated on licence-cleared data (R4 of the S5 roadmap) |
| Possibly commercially usable, **unverified** | the trading venue's own real-time/historical API under the owner's account terms; forward self-collection of that venue's feed; exchange-published historical downloads (Kraken, Coinbase, Bitstamp, OKX, Bitfinex) | not read | cannot be relied on; each needs its text read and, where unclear, a written answer (S5 question list) |
| Possibly free and open, **unverified** | public-domain or open-licence aggregates (FRED-hosted series, academic datasets) | not read; redistribution rights of underlying exchange data usually inherit from the exchange | not assumed usable |
| Paid vendors | tick/aggregate vendors | not investigated beyond S5; no purchase allowed | out of scope (€0 budget) |

## What longer history could and could not buy (statistical value, hypotheses)
- A legal extension would mostly cover BTC (and ETH) before 2017-2019. That adds **calendar time but almost no cross-section**: pre-2017 there are few liquid assets, and they are highly correlated (see D4/D5 results).
- Longer history raises the power of a *time-series* claim roughly with years; it does not turn assets into independent observations. The S8 report quantifies this with the simulated design effect.
- Whether such history is legally usable for commercial deployment is **unknown**; the plan treats it as a condition, not as a fact.

## Roadmap items that follow (no action taken)
1. Owner chooses how the primary texts become readable (allow hosts or paste). 2. Store each text with date and sha256 under `quant/docs/legal/` (not done: no text was read). 3. Send the S5 question list in writing for the venue actually intended for trading. 4. Re-validate any research result on licence-cleared data before any paper step.
