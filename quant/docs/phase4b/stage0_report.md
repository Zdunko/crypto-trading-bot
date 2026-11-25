# Stage 0 report - research infrastructure (no strategy, no profitability result)

Scope kept: no new strategy, no parameter search, no profitability backtest, holdout untouched, historical reports and rejected
configurations (R1, `no_stop_cooldown`, ...) preserved unchanged. Everything below is infrastructure.

## 1. Single execution and cost model (`quantlab/execution.py`, `quantlab/costs.py`)
- One cost definition: `CostScenario` (fee, slippage, stop_extra). `entry_price`/`exit_price` are now the ONLY place the price
  formulas live; the legacy post-hoc `apply_costs` calls them (same numbers, tests unchanged), the engine calls them for every fill.
- Engine contract: strategy sees only candles `< i` (`History`) and an explicit `PortfolioView`; orders fill at the open of `i`;
  equity = cash + positions at liquidation value; the circuit breaker, sizing and the report all use this one equity.
- Deterministic order of processing: stop moves, sells, then buys, each by (priority, pair).
- Funds: buys are clipped to free cash, rejected below `min_notional` (never rounded up); no pyramiding; missing candle: order waits
  at most `max_defer` candles then expires (logged); positions valued at last known close; stops cannot trigger without a candle.
- Stops: fill at the stop, or at the open when the candle opens beyond it (`conservative`); `freqtrade` mode reproduces Freqtrade's
  rule (stop price unless the whole candle is beyond the stop) for reconciliation only.
- Native confirmation runs use a lumped `--fee = fee + slippage` (`ExecConfig.lumped_fee`) so the wallet equals reported equity;
  `stop_extra` cannot be represented natively and stays an engine-only stress assumption.

## 2. Circuit breaker (continuous, deterministic)
Checked at the close of EVERY candle on the shared equity (not only at entries). Drawdown from the peak:
>= 15 %: risk multiplier 0.5 (visible to the strategy); >= 20 %: HALT - new buys rejected; `flatten` (default): every open position
is sold at the next open (reason `halt`); `hold`: positions stay with their stops. A halt is latched: it survives price recovery
and only an owner approval timestamp resumes trading (peak reset to current equity). In a backtest no approval exists, so a halt
is terminal (reported, never hidden). Flatten is the default because holding leaves the drawdown unbounded; this is a protocol
choice, listed under owner decisions.

## 3. Trade-level causality (`quantlab/causality.py`)
Lookahead-analysis re-runs a truncated window with a fresh state, so a stateful strategy can be flagged without any leakage. New
checks, exact and on the engine: (a) mutation - random future candles never change orders up to and including candle k nor trades
closed before k; (b) restart - saving the full state at k and restarting reproduces orders and equity bit-for-bit; (c) negative
control - a deliberately leaky strategy IS detected, and a fresh start without state differs (the lookahead-analysis false-positive
mechanism, reproduced). lookahead-analysis stays mandatory for any stateless Freqtrade signal layer; T10 is not weakened.
Status of the two historical R1 flags (SOL 2022-08-07, LINK 2023-01-04): R1 is rejected and was NOT re-run (that would be a new
backtest). The mechanism is reproduced on synthetic data; the flags stay on record as "unresolved on real data, mechanism
identified"; they are not suppressed and R1's T10 stays failed.

## 4. Native Freqtrade reconciliation (synthetic fixtures, `tests/test_reconcile_freqtrade.py`)
Equivalent assumptions: signal on candle j fills at open j+1, fixed stake 100 (Freqtrade's stake excludes the fee, so the engine's
notional is `100*(1+slip)*(1+fee)`), stop -10 % from the fill, Freqtrade fee = fee+slippage, stop_extra = 0, `stop_fill=freqtrade`.
Fixture: 4 pairs, simultaneous entries (2 on one candle), an intrabar stop, a whole-candle gap below the stop, a gap that recovers
above the stop, an exit signal. Result: trade count, pairs, open/close timestamps and rates identical (rates within 1e-6 because
Freqtrade rounds to exchange precision); profit_abs max difference 3.1e-4 USDT (fee only) and 3.3e-4 USDT (fee + slippage) on a
100 USDT stake. Known, documented difference: Freqtrade fills a gap-down that recovers above the stop AT the stop price; the
conservative engine fills at the open (the test pins which trade differs: only the recovering gap).
Also: engine buy-and-hold equals the legacy benchmark within 2e-6 relative (legacy values positions with the additive factor
1-fee-slippage, the engine with the multiplicative (1-slippage)(1-fee) it actually pays).

## 5. Statistical rules fixed before any new result (`protocol/protocol_v4_stats.json`, `quantlab/stats.py`)
Levels: alpha 0.05 (one-sided), power 0.8, 95 % block-bootstrap interval, DSR >= 0.95, PBO <= 0.25, Holm across registered
hypotheses, BH only as a secondary view. Trial count N = 40 historical configurations + the new family. Underpowered rule: if the
smallest annualised Sharpe detectable at power 0.8 exceeds 1.5, no significance claim is made. Volatility targeting is never evidence
of alpha: scaled series are compared with the unscaled basket. Unit-tested closed forms (PSR, expected max Sharpe, minimum track
record, minimum detectable Sharpe, PBO on noise vs skill, Holm/BH examples, guard rails).
Power fact for planning: with the 1642 daily returns of the evaluation period the smallest detectable annualised Sharpe is about 1.17.

## 6. Experiment ledger (`protocol/experiment_ledger.json`)
Reconstructed from the GitHub run list and runner code: 17 workflow runs, 11 with research content; 136 Freqtrade backtests in
successful runs (47 first evaluations, 89 repeats of identical configurations); 40 distinct strategy configurations evaluated on
research data (26 in Phase 3, 14 in Phase 4); 0 holdout evaluations. Counts are derived from code, not from per-run counters.

## 7. Architecture review
Removed duplication: price formulas now single-sourced (`costs.entry_price/exit_price`). Deliberately NOT removed (reproducibility
of archived reports): `apply_costs`, `apply_costs_consistent`, `apply_costs_recosted`, `build_equity`, `phase3.py`, `phase4.py`,
`strategies_r1/` (its own `DrawdownBreaker`; rejected and frozen in manifest v3). Rule for new work: new strategies use
`quantlab.execution`; legacy modules are read-only references. Frozen by manifest v4: `protocol_v4_stats.json`, ledger, `costs.py`,
`execution.py`, `causality.py`, `stats.py`.

## 8. Reference verification (web check of bibliographic data this session; full texts not read)
Verified: Jegadeesh-Titman 1993 JF 48(1) 65-91; Moskowitz-Ooi-Pedersen 2012 JFE 104(2) 228-250; Moreira-Muir 2017 JF 72(4)
1611-1644; Liu-Tsyvinski 2021 RFS 34(6) 2689-2727; Liu-Tsyvinski-Wu 2022 JF 77(2) 1133-1177; Cederburg et al. 2020 JFE 138(1)
95-117; Bailey-Lopez de Prado 2014 JPM 40(5) 94-107; Daniel-Moskowitz 2016 JFE 122(2) 221-247; Bailey et al. 2017 J. Comput.
Finance 20(4) (DOI 10.21314/JCF.2016.322). NOT verified and therefore not relied on: Hurst-Ooi-Pedersen 2017, Faber 2007,
Harvey-Liu-Zhu 2016, Harvey et al. 2018 (volatility targeting), White 2000 (partially confirmed).

## 9. Remaining limitations
- Real-data causality of the historical R1 flags is not re-adjudicated (needs a new run of a rejected configuration).
- Slippage and the 0.10 % fee are assumptions, not measured; Freqtrade cannot reproduce `stop_extra`.
- The engine is hourly-candle based; intrabar order of high/low is unknown (stops assume the stop is reached if low <= stop).
- Only synthetic fixtures reconcile with native Freqtrade; real-data agreement is limited to the buy-and-hold benchmark (CI check).
- Research data is not out-of-sample; the survivor universe (8 pairs) is biased.

## 10. Concrete proposal for Family A (design only, needs separate approval)
**Primary specification A1 - trend-filtered, volatility-scaled crypto basket vs cash** (all parameters fixed a priori from convention
or a risk budget; none tuned on this data):
- Universe: the 8 frozen pairs, labelled survivor-biased. Daily bars from completed days only (1h resampled), decisions at the next
  open, cash earns 0 %.
- Trend score per asset: share of three fixed filters satisfied, close > SMA(50), SMA(100), SMA(200): s in {0, 1/3, 2/3, 1}.
- Weight per asset: w_i = (1/8) * s_i * min(1, sigma_target / sigma_i), sigma_i = 30-day realised volatility (annualised), sigma_target
  = 40 % (about half the basket's historical volatility; a risk budget, no leverage so w sums to <= 1, rest in cash).
- Rebalance daily only if the target weight moves by more than 5 percentage points (cost control).
- Components registered as descriptive trials (counted in N = 43): A0 = trend filter without vol scaling; V0 = vol scaling without
  trend filter (fully invested basket); plus A1. Benchmarks: B1-B5 and A0/V0.
- Hypotheses (Holm over 2): H1 net annualised Sharpe of A1 > 0; H2 A1's Sharpe exceeds the unscaled basket B1's (paired block
  bootstrap). Vol targeting alone (V0 vs B1) is reported but never counted as alpha.
- Costs: 0.15 % per side (stress 0.30 %) on traded notional; turnover and average exposure reported (R1 taught that low exposure
  alone destroys return).
- Circuit breaker: evaluated OFF for the edge test (signal quality), and replayed deterministically afterwards only to report how
  often it would have halted; ON in any paper-trading deployment. Owner decision requested.
- Honest expectations (not results): T4 (max drawdown <= 20 %) and T5 (PF >= 1.3) are demanding for a long-only crypto basket and
  may fail; T1 (>= 200 closed trades) may be hard to reach with daily trend episodes on 8 assets; with 4.5 years the sample is
  underpowered for Sharpe below about 1.2. None of this will be softened: failure of T1-T10 means no promotion.
- Stage 1 deliverable (before any run): the specification and pre-registration committed and hashed in manifest v5; then Stage 2
  evaluation on research data only after your approval; the holdout only after a further written approval.
