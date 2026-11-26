# Design-only proposal: next strategy family (nothing is implemented or evaluated)

Status: proposal for the owner's decision. No code, no market run, no budget registration (research budget state is unchanged: N 43, 0 further families). The draft pre-registration `proposals/b2_draft_preregistration.json` and its gate result `proposals/b2_draft_gate_result.json` are **arithmetic on assumptions I chose**, not results; a gate pass does not authorise anything (`authorizes_market_evaluation: false`).

## 1. Why the gate shapes the choice
The frozen gate (A7) needs, at the 5th percentile, >= 200 raw and >= 80 effective episodes, and a minimum detectable annualised Sharpe <= 1.5 at the 95th percentile. Over the 4.5-year research window the MDE condition alone requires the strategy to be invested almost continuously (about >= 75 % of days with little serial correlation) and to generate many independent entries. Sparse single-asset or few-asset signals (Family A: 8 assets, 14 episodes, 15.6 % of days invested) fail by construction, whatever their economics.
| Candidate | Entries | Invested share | Gate (assumption-based) | Verdict |
|---|---|---|---|---|
| Single-asset or basket trend filter (Family A variants) | ~0.4/asset-year, 8 assets | 10-20 % | raw ~14 <200, MDE >> 1.5 | **rejected family, never re-tested** |
| Cash-and-trend timing of BTC only | a handful | low | fails | rejected on arithmetic |
| **Cross-sectional momentum on the point-in-time universe (B2)** | 80-300 assets, ~2-4 entries/asset-year | 90-100 % | raw p05 948, effective p05 174, MDE p95 1.34 | **recommended to propose** |
| Low-volatility / inverse-volatility tilt of the universe | many | ~100 % | would pass similarly | alternative; weaker rationale in crypto, kept as reserve |
B2 is the same economic idea as the earlier, unapproved "Family B", redesigned under protocol V2 (point-in-time data, gate first). Approving it is a decision to lift the earlier Family B hold.

## 2. Economic rationale (hypothesis, not a result)
Among liquid USDT spot assets, those with the strongest completed 60-day return (skipping the most recent 7 days) continue to outperform the universe average over the next week. Mechanism: uneven information diffusion and flow-driven trends in a retail-heavy cross-section; the skip removes short-term reversal. The counterparty is late-reacting flow; the premium is compensation for crash risk and crowded exits, not free money. Literature support is from memory and **not verified in this session**; it is not relied on.

## 3. Specification sketch (to be frozen in a pre-registration, not coded)
Universe: S4 point-in-time membership (1 M USDT threshold, max stale 3 days), universe guard on. Signal: 60-day completed return, 7-day skip. Portfolio: equal weight in the top quintile, weekly rebalance, long-only, cash when nothing qualifies. Execution: Stage 0 engine, BASE and STRESS costs, participation cap 10 %, S2 risk layer unchanged. Configurations (N += 3): B2-1 primary; B2-2 same without the skip (descriptive); B2-3 random selection with equal turnover (signal-free control).
**Parameter complexity:** 4 convention parameters (lookback 60, skip 7, top fraction 0.2, rebalance 7), 0 free parameters, no search space; each with a stated source; none tuned.

## 4. Expected failure modes (written before any result)
1. Momentum crashes in sharp rebounds; long-only cannot hedge.
2. Cost drag: weekly turnover at 0.15 % per side may exceed the gross premium (rough drag several percent per year).
3. The premium lives in small illiquid assets that the 1 M USDT filter and the 10 % participation cap remove.
4. One market cycle (2021-2025, 2 bear episodes): a regime artefact; all regime-conditional statements underpowered.
5. T4 (drawdown <= 20 % and not above the best benchmark) is very hard for a fully invested long-only crypto book: the S2 risk layer will flatten at tier 3 (18 %) and set SAFETY_DISQUALIFIED, which shortens the traded window and weakens power. A "validated" outcome is unlikely (my prior, an assumption: below 5 %); the realistic value of the run is information on relative skill versus the point-in-time equal-weight benchmark.
6. Data: daily/hourly volume discrepancy (X1) in five months, identity-epoch restarts remove crashed assets for about 60 days (mild optimistic selection), stale held positions are valued at the last close (R1 finding).
7. Survivorship by listing: Binance chose what to list; delisted assets are in the data but the selection is not random.

## 5. Gate sensitivity (honest limits of the arithmetic)
The pass above depends on the assumed ranges. Varying one input: invested share 0.9-1.0 -> MDE p95 1.34 (pass); 0.8-0.9 -> 1.42; 0.7-0.8 -> 1.51 (fail); 0.5-0.7 -> 1.75. Entry rate 0.5-1.0/asset-year -> effective p05 51 (fail); 0.8-1.5 -> 80 (borderline). The S2 risk layer cutting exposure after drawdowns lowers the invested share, so a real run could be underpowered even though the plan passes.

## 6. Benchmark comparisons planned (all registered in `benchmark_registry.json`)
Legacy B1-B5 (T3/T4 unchanged), cash, BTC buy-and-hold, point-in-time equal weight (the key comparator for selection skill), simple trend, volatility-targeted, exposure-matched, volatility-matched, cash-mix at the T4 limit, random-timing null for the exposure schedule and the random-selection control B2-3. Metrics: net return, CAGR, MDD, Sharpe, Sortino, Calmar, turnover, costs, exposure, CVaR/worst day, active return, tracking error, information ratio, paired block-bootstrap Sharpe difference with Holm over the benchmark set, DSR with N = 46.

## 7. Allocation of the remaining research budget
Current: N = 43, cap 52, 0 of 3 further families used. Proposal: B2 takes 3 configurations (N -> 46). The remaining 6 configurations stay **unallocated** (two possible families of three, or none); nothing is pre-committed. Stop rule: two consecutive rejections under V2 end the strategy search and the owner decides between more data, wider scope or ending the line. No re-run of B2 after seeing results; infrastructure bugs found before the run are fixed before it.

## 8. What I would not do, and what needs your approval
Not implemented: signal code, a B2 strategy class, any backtest, any registration in `research_budget.json`/`spec_registry.json`. To proceed you would need to approve, separately: (1) lifting the Family B hold for B2; (2) registering and freezing the B2 pre-registration (gate result recorded); (3) strategy implementation with synthetic validation; (4) one market run (G5, explicit owner approval for the exact spec hash in `run_approvals.json`).
