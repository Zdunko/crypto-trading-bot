# Phase 3B - audit of the Phase 3 evaluation (findings)

Date 2026-11-25. Evidence: run 45630084090 (commit `065a7fc`, corrected engine + audit stage), run 45563804911 (original, `918c2f5`), offline tests. **No strategy rule, parameter, threshold, period or config was changed; the frozen manifest verifies. The holdout (2025-07-01 -> 2026-11-25) was not evaluated.** Original results are preserved verbatim in `quant/reports/phase3_evaluation_report.md`; corrected numbers are in `quant/reports/phase3b_corrected_evaluation.md`.

## 1. Slippage accounting (losses below -100 %): found, fixed, preserved

- **Cause (verified):** Phase 3 applied slippage afterwards to trades that Freqtrade had sized from a wallet that never paid slippage. For a strategy that loses almost everything the extra cost was charged on stakes the account no longer owned, so equity could fall below zero. Reproduced offline (`test_posthoc_slippage_can_ruin_below_minus_100_percent_but_consistent_cannot`). The frozen protocol called this "second order"; **that was wrong for losers and for high-turnover strategies.** Erratum recorded here; `protocol.json` is not edited (frozen).
- **Fix:** `apply_costs_consistent` scales each position by `(wallet + our realised profit) / (wallet + Freqtrade fee-only realised profit)` at entry, so sizes shrink as slippage erodes the account and losses compound multiplicatively. With zero slippage it reproduces Freqtrade exactly (scale = 1). Approximation: realised profit only; exits processed before entries at equal timestamps.
- **Effect (same trades, base costs):**

| Strategy | Net original -> corrected | Stress net original -> corrected |
|---|---|---|
| TrendEmaCross | +654.0 % -> +583.3 % | +218.5 % -> +207.9 % |
| MeanReversionRsiBb | -73.6 % -> -66.5 % | **-101.4 % -> -83.4 %** |
| BreakoutDonchian | +190.8 % -> +188.5 % | -60.3 % -> **+6.8 %** |
| MomentumRoc | +1140.2 % -> +1074.0 % | +643.6 % -> +610.5 % |

  Worst parameter variant of MeanReversion: -109.3 % -> -91.1 %. No value below -100 % remains. The original engine **overstated both gains (up to 11 % of net return) and losses**; the one verdict-relevant change is **BreakoutDonchian T6 (stress) flips FAIL -> PASS** (stress +6.8 %, PF 1.004). Breakout is still rejected (T1b, T3, T4, T5, T7a, T7b). **All four strategies remain rejected under the corrected engine** with identical failed-criteria lists otherwise (Trend T1b/T3/T4/T5/T7b/T8; MeanReversion 10 criteria; Momentum T1b/T4/T5/T7a/T7b/T8).

## 2. Reconciliation with native Freqtrade (fee-only trades, run 45630084090)

| Strategy | Trades FT/ours | Profit factor FT/ours | Win rate FT/ours | Total profit FT/ours (USDT) | Per-pair profit max abs diff |
|---|---|---|---|---|---|
| TrendEmaCross | 830/830 | 1.2219/1.2219 | 0.2554/0.2554 | 7949.82/7949.82 | 0.0000 |
| MeanReversionRsiBb | 780/780 | 0.7825/0.7825 | 0.6013/0.6013 | -569.80/-569.80 | 0.0000 |
| BreakoutDonchian | 1033/1033 | 1.1021/1.1021 | 0.3466/0.3466 | 3049.01/3049.01 | 0.0000 |
| MomentumRoc | 523/523 | 1.2435/1.2435 | 0.3040/0.3040 | 12988.59/12988.59 | 0.0000 |
| BuyAndHold | 4/4 | 0.0 / inf | 1.0/1.0 | 41885.70/41885.70 | 0.0000 |

Everything matches (BuyAndHold PF differs only by convention: Freqtrade prints 0.0 when there are no losing trades; we print inf). Earlier run: final balances within 0.004 %. Known, expected difference: **maximum drawdown** (Freqtrade counts closed trades only and understates it, e.g. Trend 41 % vs 70 % mark-to-market). The equal-weight benchmark agrees with Freqtrade's own `market_change` (+1877 % vs our gross +1902 %; 1.3 % apart because we buy at the first candle's open).

## 3. Were thresholds applied to the correct period, separate from development data?

- **Period: yes (verified).** Backtest logs show data "up to 2025-07-01"; windows end 2025-07; the evaluation index ends 2025-06-30 23:00. **Leakage proof:** removing every candle at/after 2025-07-01 leaves closes, BTC regime labels and the benchmark **identical** (run 45630084090). The code does load all candles into memory (including the holdout) but only through causal indicators and an index that stops at the evaluation end.
- **Separation from development data: there was none, and that must be said plainly.** Protocol v2 uses one pooled pre-holdout period for fixing nothing (parameters are conventions, not fitted) and for judging everything (T1-T10, robustness variants, bias checks all use the same 2021-2025-H1 data). It is therefore an **evaluation/research period, not an independent out-of-sample test**; v1 wording ("OOS") is superseded. Thresholds were fixed before results; they were not derived from them. From now on **all data before 2025-07-01 is research data**.

## 4. The high Freqtrade `BuyAndHold` return (+4185 %): explained

- Freqtrade's reference strategy had 3 slots: BTC, ETH, SOL bought 2021-01-01 (330 USDT each). **SOL reached the strategy's `minimal_roi` trigger of +10 000 % on 2021-09-06**, the 330 USDT became ~33 000 USDT, and that money was redeployed into XRP (stake 11 231 USDT, +64 % to the end). So the number is one coin x100 captured by an ROI exit plus a reinvestment, driven by start date and coin selection - **not a meaningful benchmark**.
- The frozen **equal-weight benchmark (+1896 %) is also dominated by two coins**: SOL +10 154 % (66.7 % of the benchmark's gross return) and DOGE +3 436 % (22.6 %). Without SOL: +721 %; without SOL and DOGE: +271 %; BTC alone +269 %; BTC+ETH +253 %; monthly rebalanced equal-weight +1660 % (Sortino 1.78, drawdown 81.6 %).
- **Start-date sensitivity (all 8 pairs, to 2025-07):** from 2021-01-01 +1896 %, from 2021-07-01 +75 %, 2022-01-01 +16 %, 2022-07-01 +230 %, 2023-01-01 +386 %, 2023-07-01 +213 %, 2024-01-01 +70 %. The frozen benchmark's headline is a 2021-01-01 start artefact (SOL at its listing-era price). This also is **survivorship/hindsight selection**: the universe was chosen in 2026.
- **Consequence for fair comparison:** T3 (Sortino >= benchmark 1.81) is hard to pass because of that single start date. Benchmark Sortino: EW 1.81, ex-SOL 1.57, ex-SOL-and-DOGE 1.12, BTC 1.16, BTC+ETH 1.09. Trend (1.67) and Momentum (1.97) would beat the weaker benchmarks; **no verdict changes** because every strategy also fails T4 and T5 independently. v2's thresholds are not edited.
- **Proposal for a future protocol (owner decision, must not weaken T3):** judge T3 against the *maximum* Sortino of {equal-weight, equal-weight ex-top-2, BTC}, report all of them, and report start-date sensitivity; never use Freqtrade's 3-slot `BuyAndHold` as a benchmark.

## 5. Preservation and status of candidates

- Preserved unchanged: `phase3_evaluation_report.md`, `protocol.json` v2 + manifest, `e_verdict.json`, journal rows, all run IDs. New: this file, `phase3b_corrected_evaluation.md`, engine `apply_costs_consistent` (the original `apply_costs` is kept and still tested).
- **Research candidates only (not validated, not for paper or live use): TrendEmaCross, MomentumRoc.** Not carried forward: MeanReversionRsiBb, BreakoutDonchian.
- Honest limits that remain: flat slippage assumption; candle-based fills; one market cycle; survivorship; optimistic bootstrap intervals; the correction itself is an approximation.
- CI note: the upstream matrix for `065a7fc` reported a failed aggregate "Build (3.13)"; I did not investigate it (earlier occurrences were macOS runners that never started).
