# S7 design review: B2 reassessed and up to three economically distinct candidate families

Design only. Nothing is implemented, registered, evaluated or approved; the research budget is untouched (N 43/52, 0 further families). **Measured** = data or stored simulations in this repository (S3-S6 results, `s7_gate_audit_results.json`); **assumption** = my declared input, with no measurement behind it.

## 1. What the audit changes
1. The frozen risk layer makes a fully invested crypto-like book hit SHUTDOWN in 58-68 % of synthetic paths with mean invested share 0.32-0.65 (measured, synthetic); constant sleeves of 15-25 % still shut down in 27-57 % (measured, synthetic, harsh drift).
2. Detectability depends on the claim. For a relative claim vs a benchmark over 4.5 years the standard error of the annual information ratio is 1/sqrt(4.5) = 0.47, so the minimum detectable IR at 80 % power (5 % one-sided) is **1.17**; power at IR 0.3 / 0.5 / 0.8 / 1.0 is **0.16 / 0.28 / 0.52 / 0.68** (arithmetic). Detecting IR 0.5 would need about **25 years** of history, IR 0.3 about 69 years. Exposure scaling does not change this.
3. Consequence: on a single 4.5-year cycle only very large effects (IR >= 1.2) are statistically demonstrable. Modest, plausible effects cannot be validated by this dataset whatever the signal.

## 2. B2 reassessed (cross-sectional momentum on the point-in-time universe)
- Relation to rejected work: the signal family (momentum) was rejected before as `momentum_roc` (time-series, per asset, absolute threshold). B2 ranks assets relative to each other on the point-in-time universe with a different construction and cost profile; it is **not the same specification**, but it is momentum again and I flag it as related.
- Gate arithmetic: passes at the declared invested share 0.9-1.0 (MDE p95 1.34), **fails once the shares measured behind the frozen layer are used** (MDE 1.74 / 2.42 / 2.69). Effective episodes are overstated (v1 formula); with 20-day holds the true design effect is about 7.8 (synthetic), so the declared 174 effective episodes would be roughly 120 or fewer.
- Risk compatibility: poor. Top-quintile long-only crypto volatility is roughly 70-90 % (assumption); the frozen layer would cut or shut it down.
- Power for a relative claim vs the point-in-time equal-weight benchmark: at an assumed IR of 0.5 the power is 0.28 (arithmetic on an assumption).
- Verdict: **NO-GO as specified.**

## 3. Candidates
| | C1 Rebalancing (volatility-harvesting) sleeve | C2 Cross-sectional low-volatility tilt | C3 Listing-maturity screen |
|---|---|---|---|
| Economic hypothesis | Rebalancing a fixed-weight basket of imperfectly correlated, high-variance assets harvests variance (a structural effect, no forecast) | Investors overpay for volatile, lottery-like assets; lower-volatility assets earn better risk-adjusted returns | Newly listed or identity-broken assets are over-hyped and underperform mature ones |
| Counterparty | Noise traders and trend chasers on the other side of rebalancing trades | Retail demand for lottery-like payoffs; leverage-constrained buyers | Attention-driven retail buying of fresh listings and rebrandings |
| Expected return source | About 0.5 (average asset variance - portfolio variance): ~14 %/yr on the sleeve for 10 assets at 90 % volatility and correlation 0.6 under iid log-normal prices (assumption; real crypto trends and crashes) | Lower drawdown and better Sharpe than the equal-weight universe | Return gap between mature and young assets |
| Failure modes | Trending markets and delistings reverse the premium; costs; identity breaks; extreme concentration risk in a sleeve | Low-vol assets are mostly large caps (still 45-60 % volatility, assumption); factor crowding; one cycle | Effect only in assets the 1 M USDT filter already removes; age data from file listings, not announcements; survivorship by listing |
| Parameters / configurations | weights (fixed equal), rebalance period (monthly), sleeve fraction: 3 conventions, 0 free / 2 | volatility window (60 d), selection fraction (tercile), rebalance (monthly): 3 conventions / 3 | minimum age (180 d), identity-break exclusion window (60 d): 2 conventions / 2 |
| Exposure / turnover | sleeve 15-25 % of wallet, invested share 1.0; turnover low (monthly) | 60-100 % of wallet when allowed; monthly turnover ~20-40 % (assumption) | near the benchmark; turnover = benchmark's plus screening changes |
| Feasibility (assumed vs measured) | Detectability: premium/vol gives an incremental Sharpe of about 0.2 vs a MDE of 1.2 (arithmetic): **unvalidatable** | Assumed relative IR 0.3-0.6: power 0.16-0.35 (arithmetic) | Assumed IR 0.3-0.8: power 0.16-0.52 |
| Risk compatibility (measured, synthetic) | Small sleeves still shut down 27-57 % of paths via the 3-flat-cycle cap | Same layer problem at crypto-like volatility | Same |
| Benchmarks | cash, BTC buy-and-hold, point-in-time equal weight, B1-B5, exposure-matched | point-in-time equal weight (primary), volatility-targeted, simple trend | point-in-time equal weight (primary), B1-B5 |
| Budget | 2 configurations (N -> 45) | 3 (N -> 46) | 2 (N -> 45) |
Not disguised: none of the three reuses a rejected family key; features checked against Family A (time-series trend filter + volatility scaling on 8 pairs), Phase 3 (EMA cross, RSI/BB mean reversion, Donchian breakout, per-asset ROC momentum) and R1 (risk overlay). C2 uses volatility as a cross-sectional ranking, not as time-series position scaling (Family A V0). B2 is flagged above.
Also considered and dropped: short-term reversal / liquidity provision (turnover cost: a round trip costs about 0.30 % in the BASE scenario, no measured gross edge), event or calendar effects (no rationale), anything with futures, shorting, options or lending (forbidden or no data).

## 4. Recommendation
**NO-GO for implementing, registering or evaluating any of B2, C1, C2, C3.** The evidence supports no candidate: each needs either an effect size the dataset cannot detect, or exposure the frozen layer will not permit, and a run would consume budget (N) to return "underpowered". Preserving N = 43 is the better use.
Decisions for the owner (not taken here):
1. **Objective:** accept that modest alpha cannot be statistically proven on crypto history of this length (about 25 years would be needed for IR 0.5). A defensible production system can still be justified by structure (risk control, costs, legality, operational validation) rather than by a claimed significant edge; the volatility-targeted point-in-time portfolio benchmark is the natural starting point, valued as risk-managed beta, not alpha.
2. **Methodology:** consider adopting the v2 gate proposal so future pre-registrations are judged on realistic exposure, overlap-aware sample size and claim-specific power.
3. **Evidence horizon:** the only real source of additional power is time: licensed forward data and paper trading under a frozen specification (see the production roadmap), not more tuning on the 2017-2025 window.
