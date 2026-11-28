# M4 report — H1 (MAX3) L2 economic viability and realistic execution (single approved replay, 2026-11-27)

Result file `docs/phase4c/m4_l2_results.json` (sha256 `2d64e8e8591548d475d27f3039d8d5b31613f8e3f2718818d3debad92d0541a4`). Registration frozen and pushed before any hourly data was fetched (commit `70f36f1`, spec sha256 `8f181685...`). Data: Binance Vision 1d (15,699 files) and 1h (15,369 files) klines for 411 symbols, every file verified against the S4 manifest; last candle opens 2025-06-29 23:00; holdout never read. Engine run hashes are identical in a second in-process pass and in a separate process.

## Decision: **L2 NO-GO for both configurations**
| | H1-h7 | H1-h28 |
|---|---|---|
| A1 net return > 0 under normal and double costs (V3) | pass (+72.4 % / +71.0 %) | pass (+92.5 % / +91.3 %) |
| A2 Sortino >= BTC buy-and-hold and equal weight | pass (1.70 vs 1.16 / 0.52) — **an artefact of the shutdown, see below** | pass (1.30) — same artefact |
| A3 max drawdown <= 20 % and not above BTC | pass (18.3 %) | **fail (22.9 %)** |
| A4 Risk Management V3 never reaches SHUTDOWN | **fail: shut down 2021-02-23** | **fail: shut down 2021-05-19** |
| A5 incremental value vs low-volatility portfolio (one-sided HAC p <= 0.05) | **fail (p 0.86; uninformative, see below)** | **fail (p 0.61; uninformative)** |
| A6 fill ratio >= 0.95 | pass (1.00) | pass (1.00) |

## What actually happened (net of fees and slippage, 10,000 USDT, long-only spot)
- **With Risk Management V3 (the operable stack):** the portfolio is 100 % invested in about 23 volatile coins; its drawdown reached the tier-3 floor (18 %) within weeks (h = 7: 53 days; h = 28: 138 days) and V3 went to SHUTDOWN, which in a backtest is terminal. The remaining 4+ years were spent in cash (mean exposure 1.6 % / 2.9 %). The headline gain (+72 % / +92 %) was earned in the first weeks of 2021 and then frozen; CAGR 12.9 % / 15.7 %, Sharpe 0.91 / 0.84, Sortino 1.70 / 1.30, Calmar 0.70 / 0.68 are therefore **statistics of a short bull window followed by cash, not of a viable strategy**.
- **Without any risk layer (non-gating diagnostic):** h = 7: net **-11.5 %** (normal costs) and **-27.5 %** (double), max drawdown 88 %, annual one-way turnover 15.9x, cost drag 4.8 % per year (9.6 % double); h = 28: net +130 % (normal) / +109 % (double), max drawdown 83 %, Sharpe 0.63, Sortino 0.87, turnover 7.8x, cost drag 2.3 % (4.7 %) per year.
- **Passive comparators (same period and costs):** BTC buy-and-hold +268 % (CAGR 33.6 %, max drawdown 76.6 %, Sortino 1.16); point-in-time equal weight -24.9 % (max drawdown 91.7 %); cash 0 %; ex-post risk-matched BTC/cash mix +58 % (h = 7, BTC weight 24 %) / +83 % (h = 28, weight 32 %), max drawdown 26 % / 34 %. The unprotected MAX3 portfolio beat equal weight but **lost to BTC buy-and-hold** on return at either horizon and with deeper-than-acceptable drawdowns.
- **Costs and liquidity:** realistic costs consumed 2-5 % of equity per year unprotected (4.8 %/yr at h = 7 doubles to 9.6 %); h = 7 does not survive double costs. Fills: with V3 the fill ratio is 1.00; unprotected runs filled 89-91 % of intended buys (rejects: expired on missing candles, insufficient funds after partial sells). Participation at 10,000 USDT is far below the 10 % cap; capacity at larger sizes was not tested.

## Capital protection
V3 behaved as designed and protected capital in the sense that the unprotected portfolio drew down 83-88 % while the V3 stack stopped at 18-23 %. The cost of that protection is that the strategy, run with the owner's risk limits, **cannot stay invested**: a fully invested portfolio of volatile altcoins breaches an 18 % drawdown tier in weeks. h = 28 additionally exceeded the 20 % limit (22.9 %) because of gap overshoot before the flatten completed. No write-offs occurred (no held asset was delisted before the shutdown). Zero recovery was the primary valuation; last-known and conservative drawdowns coincide.

## Incremental value beyond volatility exposure
**Not established, and not decidable from this replay.** Under V3 both the MAX3 and the low-volatility portfolios were shut down (h = 7: both at the same hour, 2021-02-23 09:00, so their equity curves are identical afterwards; h = 28: 2021-05-19 and 2021-10-14), so the registered paired test compares two mostly-cash series (p 0.86 / 0.61, annualised difference -3 % / -3 %, OLS alpha on the low-volatility portfolio 0.4 % / 6.2 % per year with t 0.18 / 0.71). The registered design did not include an unprotected low-volatility run, so the question "does MAX3 beat low volatility when both stay invested?" cannot be answered without a further evaluation, which would consume budget and needs approval.

## Verification of the L1 result (all flags pass; verdicts unchanged)
- **V1 independent re-implementation (pandas):** identical IC series, maximum daily difference 0.0 (tolerance 1e-9), same days.
- **V2 placebo:** within-day permutation of the signal gives mean IC -0.0004 / +0.0002 (max |mean| 0.006 / 0.005 over 100 permutations) against the observed 0.117 / 0.092; entry delayed by one more day keeps the IC (0.114 / 0.088).
- **V3 survivorship:** 83 of 411 assets failed (13.5 % of member-days); IC restricted to survivors is 0.124 / 0.095 (not lower), so the IC is not produced by delisted assets.
- **V4 liquidity:** IC in the more liquid half 0.124 / 0.095, in the less liquid half 0.106 / 0.085: not an illiquidity artefact.
Conclusion: the unexpectedly large IC is not an alignment, survivorship or liquidity artefact of this pipeline. Together with the -0.91 rank correlation with volatility it is consistent with a broad "calmer coins outperformed" relation in 2021-2025.

## Limitations (all preserved)
Research-only data; kline data without order book (spread and impact are inside the scenario slippage); one-hour latency model; 10,000 USDT account; one history (2021-2025); the L2 design itself: under V3 the evaluated portfolios are in cash for most of the sample, which makes A2 flatter the strategy and A5 uninformative — these are design weaknesses of the registered criteria, reported here and not corrected after the fact (the replay is consumed). Passive comparators use daily accounting without partial fills. T1-T10 were neither evaluated nor changed.

## What this result does NOT license
No L3, no paper or live trading, no deployment, no new hypothesis or variant (for example a volatility-targeted or lower-exposure version of H1, or an unprotected comparison with the low-volatility portfolio) without a new owner approval, a new registration and, where the budget requires it, a budget decision. L1 PASS stands as a signal-existence result; L2 shows that, as a fully invested long-only portfolio under the existing risk limits, it is not economically viable.
