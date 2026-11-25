# Phase 3B — risk-management research proposal (DESIGN ONLY, awaiting owner approval)

Status: **proposal. Nothing in this document has been implemented or run.** No new strategy variant exists yet.

## 0. Ground rules (what makes this research honest)

1. **All data before 2025-07-01 is research data from now on.** It has been used to evaluate, reject and discuss the Phase 2 strategies, and its characteristics (2021 and 2024-H2 bull windows, 2022 and 2025-H1 drawdowns) are known to the designer. Anything tuned or chosen on it is a *hypothesis*, never a validation.
2. **No search over observed results.** Every parameter below is set *a priori* from a risk budget or a market convention, written into a frozen protocol (v3) **before** the first run. Ablations are descriptive only; the final overlay is "all components on, a-priori values". Parameters are not swept; the Phase 2 style one-at-a-time sensitivity is reported, not used to choose.
3. **The only clean out-of-sample evidence is (a) the untouched holdout 2025-07-01 → 2026-11-25, usable exactly once, and (b) forward paper trading (Phase 5), which is true future data.** A result on research data may justify *continuing*, never *claiming validation*.
4. **T1–T10 are not weakened.** They (with T4 ≤ 20 %, T5 ≥ 1.3, T1 ≥ 200 trades) remain the promotion gate. On research data they are reported as diagnostics. A new gate may only be *added*, never relaxed.
5. **Multiple-testing ledger:** every configuration ever backtested is logged (count and outcome) in the journal; the final report states the number of trials.
6. **Costs:** the corrected sizing-consistent slippage engine (Phase 3B) is used; the original post-hoc results stay archived.
7. Candidates carried forward as **research candidates only**: `TrendEmaCross`, `MomentumRoc`. Rejected and not carried forward: `MeanReversionRsiBb`, `BreakoutDonchian`.

## 1. Components (each with an a-priori value and a rationale that does not come from the results)

| # | Component | Mechanism | A-priori setting | Why this value (not tuned) | Freqtrade hook |
|---|---|---|---|---|---|
| 1 | Volatility-adjusted position sizing | stake so that a stop-out loses a fixed share of equity: `f = risk / (k · ATR%)`, capped (existing `quant_common.atr_stake_fraction`, already unit-tested) | risk per trade 0.5 % of equity, stop distance 3 × ATR(14), cap 20 % of equity per position | 0.5–1 % per trade is the textbook budget; 3 × ATR is the common chandelier width; a 20 % cap keeps 5 slots below 100 % | `custom_stake_amount` |
| 2 | Portfolio exposure limits | cap gross exposure and open positions | max 3 positions, gross exposure ≤ 60 % of equity | forces ≥ 40 % cash at all times; bounds worst-case gap loss | `custom_stake_amount` / `confirm_trade_entry` |
| 3 | Correlation-aware diversification | do not open a position if the candidate's 30-day hourly-return correlation with any open position exceeds the threshold; at most one position per correlation cluster | correlation limit 0.8, window 30 days | crypto majors are strongly correlated; 0.8 flags "same bet" | `confirm_trade_entry` with informative pairs |
| 4 | Market-regime filter | no new entries when BTC/USDT daily regime (existing `market_regime`: ADX ≥ 25 and close < EMA200) is `bear`; reduce risk per trade to 50 % in `sideways` | the Phase 2 regime definition, unchanged | reuse of an already-specified, causal component; no new tuning knob | informative pair + `confirm_trade_entry` |
| 5a | Stop-loss | trailing ATR (chandelier) stop replacing the fixed −10 % | 3 × ATR(14) below the highest close since entry | consistent with the sizing stop in #1 (one stop distance for sizing and exit) | `custom_stoploss` |
| 5b | Cooldown | after a stop-out, no new entry in that pair for 24 h; after 3 stop-outs in 48 h portfolio-wide pause for 24 h | 24 h / 3-in-48 h | Freqtrade-native `CooldownPeriod` / `StoplossGuard` semantics | `protections` |
| 6 | Capital preservation in bear markets | (i) regime filter above, (ii) portfolio circuit breaker: if equity is more than 15 % below its peak, halve risk per trade; if more than 20 % below, stop entries until equity recovers to within 10 % of peak, minimum 30 days | 15 % / 20 % / 10 % / 30 d | 20 % equals the T4 limit the strategy must meet; breakers act before the limit | `MaxDrawdown` protection + custom logic |

Known design weaknesses to state up front: the ATR and correlation windows lag (a crash can precede the filter); stops can gap through; the circuit breaker locks in losses after sharp V-shaped recoveries; the regime filter is the least robust component (ADX is a laggard and flips near its threshold); long-only spot cannot profit from bear markets, only avoid them.

## 2. Experimental design

- **Strategies under overlay:** TrendEmaCross and MomentumRoc (parameters and entry/exit rules unchanged from Phase 2; only the risk layer is added). Overlay is a separate, reviewable module so that results are attributable.
- **Configurations (pre-registered, at most 4 evaluated):** `R0` = Phase 2 strategy without overlay (baseline, already measured); `R1` = full overlay, a-priori values (**the candidate**); `A-*` = ablations "R1 minus one component" (6 runs per strategy, **descriptive only**, never used to select or re-tune). Total ≤ 2 strategies × (1 + 6) = 14 backtests on research data, then at most 2 holdout runs.
- **Data splits (all research data, so labelled as such):** R1 is run once on 2021-01 → 2025-07 with the same nine 6-month windows and the same regime segmentation; results are shown next to R0. No second iteration of R1 is allowed after seeing these results; if R1 is changed for any reason it counts as a new trial and the count is reported.
- **Metrics:** the Phase 3 set (net return, max drawdown, Sharpe, Sortino, PF, win rate, expectancy, trades, monthly), plus: time in market, average and peak gross exposure, worst 30-day loss, drawdown duration, exposure by regime, cost share. Intervals as in Phase 3 (annualised block bootstrap), labelled optimistic.
- **Benchmarks:** the frozen equal-weight buy-and-hold, plus the Phase 3B alternative benchmarks (ex-SOL, BTC+ETH, monthly rebalanced) so that no result depends on one coin.
- **Promotion path (nothing is "validated" by this research alone):**
  1. Engineering acceptance: unit tests per component, `lookahead-analysis`/`recursive-analysis` clean (≥ 6 periods, 8 pairs), strategy-policy checks extended (no shorting, no averaging, stop present).
  2. Research-data report (diagnostic, no pass/fail claim).
  3. **Holdout, once**, only if the owner approves a *new protocol version* that fixes R1 and the holdout criteria in advance (T4 ≤ 20 %, T5 ≥ 1.3 and the rest unchanged). The holdout is not touched before that approval.
  4. Forward paper trading (Phase 5) on a free host with the same code; real validation.
- **Budget:** ≤ 3 CI research runs (one bias run, one research-data evaluation run, one holdout run), no paid services, no credentials, simulated capital only.

## 3. What would count as failure (decided now)

- R1 does not reduce max drawdown on research data below that of R0 → the overlay is not worth carrying forward.
- R1 reduces drawdown only by being in cash almost always (time in market below ~25 %) → report as "capital preservation without edge", not as a strategy.
- R1 passes on research data but fails the single holdout run → rejected; **no re-tuning and no second holdout** (the holdout would be burned).

## 4. Out of scope for this proposal

New entry rules, machine learning, shorting/leverage/futures, live trading, deployment, paid data or servers.

## 5. Decisions needed from the owner

1. Approve the components and a-priori values above (or change them **now**, before any run).
2. Approve R1 as the single candidate configuration and the ablation list as descriptive only.
3. Approve the promotion path, in particular that the holdout is used once and only after a frozen protocol v3.
4. Confirm that MomentumRoc and TrendEmaCross remain research candidates only (not validated, not for paper trading yet).
