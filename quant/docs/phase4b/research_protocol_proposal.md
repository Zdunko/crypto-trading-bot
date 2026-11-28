# Phase 4B - research integrity findings and proposed protocol v4 (DESIGN ONLY, awaiting owner approval)

Status: nothing in this document has been run or implemented. No backtest, no strategy code, no CI run was used.
All data before 2025-07-01 is research data; the holdout 2025-07-01 -> 2026-11-25 is untouched. T1-T10 are not weakened.
Historical reports, the rejected R1 configuration and all ablation results stay in the repository unchanged.

## Part A - integrity findings (analysis of code and recorded results; no new runs)

### A1. Stateful lookahead-analysis failures
Facts: freqtrade `lookahead-analysis` re-runs a short backtest around selected trades (`analyze_row`, `prepare_data` with a new
`timerange`) and compares the resulting signals with the full run. R0 strategies are stateless (signal = f(candles)) and were clean.
R1 flagged exactly one trade in two periods for both strategies (SOL/USDT 2022-08-07, LINK/USDT 2023-01-04).
Cause (hypothesis, not proven): R1 decisions depend on path state that a truncated run does not have - equity/wallet, closed-trade
history (cooldown, cluster pause), breaker peak. A different start therefore legitimately changes a decision without any future leakage.
Proposed resolution (Stage 0): a **trade-level causality test** that does not rely on lookahead-analysis for stateful logic:
1. Decision-replay: for every entry decision d(t) of the full run, record the full input vector (closed candles, state snapshot).
   Re-compute the decision from inputs truncated to candles closed before t plus the SAME recorded state; they must be identical.
2. State-injection: re-run the truncated window with the recorded state at its start (equity, peak, stop history, open trades) and
   compare decisions; any difference is a leak, not state.
3. Mutation test: replace all candles at/after t by random values; decision at t must not change (already unit-tested for the pure
   functions; extend to the full Freqtrade path).
lookahead-analysis stays mandatory for the stateless signal layer; for stateful overlays the three tests above decide T10.

### A2. Drawdown breaker monitoring (correction of my Phase 4 report)
The report said the breaker only observes equity at entry decisions. That was imprecise: `custom_stoploss` also calls the snapshot every
candle while a position is open, so the breaker was monitored on every candle with open positions, using last CLOSED candle prices.
It still never halted Trend although the evaluation drawdown was 21.8 %. The more likely reason is A4 (the breaker saw a cheaper world
than the evaluation). Arithmetic estimate, to be verified: 833 trades x ~5-10 % stake x ~0.15-0.20 % extra slippage per round trip
is ~6-17 points of equity that Freqtrade's own wallet never paid. Also: a halt only blocks entries; it cannot reduce drawdown of
positions already open. Proposed: monitor in `bot_loop_start` (called per candle in backtests), use ONE equity definition shared
with the evaluation engine, and define halt behaviour for open positions explicitly (keep stops / tighten / flatten) in the protocol.

### A3. Simulated versus native execution
Verified earlier (Phase 3B): for fee-only R0 trades, trade count, PF, win rate, profit and per-pair profit are identical to Freqtrade.
Known differences: (a) slippage is post-hoc and not fed back into Freqtrade sizing (approximated by a wallet-ratio scale);
(b) our drawdown is hourly mark-to-market, Freqtrade's is on closed trades; (c) stop fills: Freqtrade fills at the stop or the candle
open when gapped, we add +stop_extra; (d) custom stops are reported as `trailing_stop_loss`; (e) R1 stress was re-priced on identical
positions; (f) BTC regime history for R1 came from the stored file because the exchange startup-candle limit forbids ~6000 candles.
Proposed: every new engine must reproduce a native Freqtrade run of a reference strategy (trades identical, profit within 0.1 %)
before it is used for research; the reconciliation test becomes a CI gate.

### A4. Consistent fee and slippage accounting
Root problem: costs enter at two places (Freqtrade `--fee` for decisions/wallet, post-hoc layer for reporting), so every
state-dependent rule (sizing, breaker, cooldown) acts on a different world than the one reported. Proposal: **one cost model, applied
where decisions are made**. For portfolio-level strategies (Part B) use an own vectorised engine with explicit turnover costs
(fee + slippage per unit traded, same constants as protocol v2: 0.10 % + 0.05 %, stress 0.20 % + 0.10 %) so equity, sizing and risk
rules all see net equity. For Freqtrade confirmation runs use a lumped `--fee` (fee + slippage) so wallet = reported equity, with the
post-hoc layer kept only as a labelled sensitivity. Slippage assumptions remain assumptions; calibrate only against free public data.

### A5. Chandelier stop versus cooldown
Defect in my protocol v3: the flag `stop_cooldown` switched off BOTH the cooldown/cluster pause AND the chandelier stop (reverting to
the fixed -10 % stop). The `no_stop_cooldown` ablation (+67 % / +99.6 %) therefore cannot be attributed to either. It is NOT adopted
and NOT validated. Proposed mechanism study (descriptive, pre-registered, costs counted in the trial ledger): 2x2 factorial on the
unchanged R0 entry rules - {fixed -10 %, chandelier 3 ATR} x {no cooldown, cooldown} - plus the observation that R1 sizing
(0.5 % risk / 3 ATR stop) produced 2.5-4.9 % average exposure, so the strategy was mostly in cash; return is bounded by exposure.
Hypothesis to test, not a result: trend/momentum winners are rare and large (R0 win rate 25-30 %, PF 1.2), and a tight trailing
stop truncates them.

### A6. Multiple-testing ledger (honest accounting)
Evaluation-period backtests run so far on the same research data: Phase 3 (4 strategies x base/stress + parameter variants + 1
benchmark), Phase 3B reruns of the same, Phase 4 2 x 14 (run 1 invalid). The exact count will be rebuilt from run logs before any
Stage 2 result is read, and used in Deflated-Sharpe / PBO calculations. Results from research data can justify continuing; never validation.

## Part B - approaches to evaluate (theory only; none is assumed profitable)

Common facts: spot-only, long-only, cash earns 0 % (no yield products: no credentials, no paid services). Costs: 0.15 % per side base,
0.30 % stress. Statistical power warning: ~4.5 years of data is about one bull-bear cycle; for an annualised Sharpe of 1 the standard
error of the estimate is ~0.5 (SE ~ sqrt((1+0.5 SR^2)/years)), so a credible edge on research data needs a large effect and still
only justifies a holdout and paper trading.

| # | Approach | Economic rationale | Expected costs | Fails when | Complexity | Data needed | Overfitting / survivorship |
|---|---|---|---|---|---|---|---|
| 1 | Cross-sectional momentum (rank assets by past return over L weeks, hold top quantile, weekly/biweekly rebalance) | Under-reaction / herding / limited arbitrage; documented for equities and in crypto as a significant factor | Highest: turnover maybe 50-100 % per rebalance one-way -> roughly 8-15 % per year at 0.15 %/side (estimate to be measured) | Momentum crashes after sharp rebounds; long-only cannot short losers so it is mostly beta + selection; thin altcoins | High: portfolio engine, universe rules, liquidity filter | Daily OHLCV for 30-100 coins INCLUDING delisted ones, volume for liquidity filter | Survivorship is severe: our 8 pairs are survivors of 2020-09. Needs point-in-time universe (to be checked: free sources); lookback/quantile/rebalance grid invites overfitting -> pre-register 1 primary spec |
| 2 | Higher-timeframe trend (4h and 1D; ensemble of fixed lookbacks e.g. 50/100/200 EMA or SMA filters per asset) | Time-series momentum / trend following has long cross-asset evidence; crypto has strong trending episodes and heavy tails | Low: few round trips (about 2 x 0.15 % per trade) | Sideways chop (whipsaws), V-shaped recoveries, fees dominate on 4h | Low-medium: resample from stored 1h; Freqtrade-compatible or vectorised | Already have 1h OKX; 4h/1D by resampling (completed bars only) | Fewer degrees of freedom if the ensemble is fixed a priori; survivorship moderate (8 survivors); T1 (>=200 trades) may be unreachable at 1D -> reported honestly, T1 not lowered |
| 3 | Relative strength / asset rotation (hold top-k of N by relative strength; absolute-momentum filter to cash) | Combines selection (relative) with a trend filter (absolute), so it can sit in cash in bear phases ("dual momentum" idea) | Medium: monthly or weekly rotation | Rotation whipsaw, leadership reversals, correlated crash (all assets fall together) | Medium | Same as 1 (smaller universe acceptable: 8-20 liquid pairs) | Same survivorship; k, lookback, rebalance period are tunable -> fix a priori |
| 4 | Volatility-targeted allocation (weight = target vol / forecast vol, capped at 1 because no leverage) | Volatility is persistent and risk-return is weakly related to it, so scaling by inverse vol can raise Sharpe and cut tail risk (equity evidence, contested out of sample) | Low-medium with a rebalance band (trade only when weight moves > x %) | Sudden vol spikes (gap), vol-of-vol, and in strong low-vol bull runs the cap forces under-investment; cannot lever up | Low-medium | Daily/hourly closes, realised-vol estimator window | Few parameters (target, window, band) but target choice changes everything; fix from a risk budget not from results. Lesson from R1: low exposure destroys return |
| 5 | Dynamic crypto/cash allocation (trend or regime switch between a crypto basket and cash) | Drawdown control via an on/off trend filter on a diversified basket (tactical allocation evidence in traditional assets) | Low: a few switches per year | Late exits and late re-entries in V shapes, whipsaw near the filter, basket dominated by BTC beta | Low | Basket closes (daily) | Essentially one filter parameter; cash yield assumed 0 %; benchmark comparison must include the same basket buy-and-hold |

Overlap: approaches 2, 4 and 5 are building blocks of one family ("trend-filtered, volatility-scaled crypto basket"); 1 and 3 are the
cross-sectional family. The protocol therefore tests TWO pre-registered primary specifications, not 5 x grids.

### Recommended research direction (a recommendation, not a result)
1. **Stage 0 - infrastructure only, no market hypotheses**: causality tests (A1), single cost model and native reconciliation gate
   (A3, A4), breaker redesign, trial ledger. Exit: all tests green in CI; no strategy result produced.
2. **Stage 1 - desk work**: pre-register hypotheses, one primary specification per family with a priori parameters from the
   literature or risk budget, expected sign of the effect, failure conditions; data feasibility check for a point-in-time universe
   (free sources only; if impossible, cross-sectional momentum is restricted to the 8-pair survivor universe and labelled biased).
3. **Stage 2 - research-data evaluation** of family A (trend-filtered vol-scaled basket, approaches 2/4/5) first - lowest cost and
   complexity, largest sample per trade - then family B (cross-sectional, approaches 1/3) only if a credible universe exists.
   Reporting: T1-T10 unchanged, benchmark rule B1-B5 (T3 = max Sortino, T4 = 20 % and min benchmark DD), plus Deflated Sharpe Ratio,
   probability of backtest overfitting (CSCV), block-bootstrap CIs, reality-check/SPA over the trial ledger, cost stress 2x, regime table.
4. **Stage 3 - holdout**: once per finalist, only after separate written approval and a frozen manifest. **Stage 4**: paper trading.
Decision rule decided now: an approach is "credible" only if net Sharpe after costs has a bootstrap interval above 0, survives the
multiple-testing correction, passes T1-T10 and 2x costs, and does not depend on a single asset or a single regime.

## Part C - references (status of verification)
Verified in this session through web search (bibliographic data only; abstracts, not full texts, were read):
- Liu, Y., Tsyvinski, A., Wu, X. (2022). Common Risk Factors in Cryptocurrency. Journal of Finance 77(2), 1133-1177. DOI 10.1111/jofi.13119 (NBER WP 25882).
- Cederburg, S., O'Doherty, M., Wang, F., Yan, X. (2020). On the performance of volatility-managed portfolios. Journal of Financial Economics 138(1), 95-117. DOI 10.1016/j.jfineco.2020.04.015.
- Bailey, D., Lopez de Prado, M. (2014). The Deflated Sharpe Ratio. Journal of Portfolio Management 40(5), 94-107. DOI 10.3905/jpm.2014.40.5.094.
- Daniel, K., Moskowitz, T. (2016). Momentum crashes. Journal of Financial Economics 122(2), 221-247. DOI 10.1016/j.jfineco.2015.12.002.
Cited from memory, NOT verified in this session (check before relying on them):
- Jegadeesh, N., Titman, S. (1993). Returns to buying winners and selling losers. Journal of Finance 48(1), 65-91.
- Moskowitz, T., Ooi, Y.H., Pedersen, L.H. (2012). Time series momentum. Journal of Financial Economics 104(2), 228-250.
- Hurst, B., Ooi, Y.H., Pedersen, L.H. (2017). A century of evidence on trend-following investing. Journal of Portfolio Management 44(1), 15-29.
- Faber, M. (2007). A quantitative approach to tactical asset allocation. Journal of Wealth Management 9(4), 69-79.
- Moreira, A., Muir, T. (2017). Volatility-managed portfolios. Journal of Finance 72(4), 1611-1644.
- Harvey, C. et al. (2018). The impact of volatility targeting. Journal of Portfolio Management 45(1), 14-33.
- Liu, Y., Tsyvinski, A. (2021). Risks and returns of cryptocurrency. Review of Financial Studies 34(6), 2689-2727.
- Harvey, C., Liu, Y., Zhu, H. (2016). ...and the cross-section of expected returns. Review of Financial Studies 29(1), 5-68.
- Bailey, D., Borwein, J., Lopez de Prado, M., Zhu, Q.J. (2017). The probability of backtest overfitting. Journal of Computational Finance 20(4), 39-69.
- White, H. (2000). A reality check for data snooping. Econometrica 68(5), 1097-1126.
Reading note: Cederburg et al. report that volatility-managed portfolios do not systematically beat unmanaged ones out of sample,
which is why approach 4 is carried as a risk-control building block, not as a source of alpha.

## Part D - decisions requested from the owner
1. Approve Stage 0 (infrastructure and tests only, no market results) and the single-cost-model principle.
2. Approve the two-family plan and the credibility rule above, or change them now.
3. Confirm that no result of Phase 4 (incl. `no_stop_cooldown`) is carried forward as a candidate.
