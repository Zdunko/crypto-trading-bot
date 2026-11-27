# M3 report — H1 (MAX3) L1 market result (single registered run, 2026-11-27)

Result file: `docs/phase4c/m3_l1_results.json` (sha256 `53a3862df0d199efadcd7d391bbf297ea68ee67ec8b12fe0fd2534b651aba8aa`). Registration: `protocol/h1_l1_preregistration.json` (spec sha256 `469607453ca5261c83d7903ed95ea69fdee87f05b47878d0472feb551cc48741`), frozen and pushed before any market data was read (commit `3e9753c`). Data: Binance Vision spot 1d klines, 15,699 files for 411 symbols, every file verified against the S4 manifest; last candle used opens 2025-06-29 (holdout never read, not even metadata). Code unchanged since the freeze (`code_sha256` equals the M2 record).

## Decision: **L1 PASS** — and only L1
Both registered configurations pass every registered criterion; the disguise check (registered form) passes; causality and reproducibility checks pass. **This is a level-1 result: evidence of a predictive cross-sectional signal on research-only data. It says nothing about costs, capacity, robustness, forward behaviour, T1-T10, or a profitable strategy.**

| | H1-h7 | H1-h28 |
|---|---|---|
| valid IC days | 1,633 | 1,612 |
| mean IC / median IC | **0.0919 / 0.0947** | **0.1166 / 0.1316** |
| HAC lag; HAC t | 14; 8.60 | 56; 5.64 |
| two-sided 95 % CI of mean IC | [0.0710, 0.1129] | [0.0761, 0.1570] |
| one-sided 95 % lower bound | 0.0743 | 0.0826 |
| raw one-sided p / Holm p (2 configs) | < 1e-16 / < 1e-16 | 8.3e-9 / 8.3e-9 |
| block-bootstrap p (check, 999 draws) | 0.001 (floor) | 0.001 (floor) |
| effective sample size (n x (naive se / HAC se)^2) | 326 days | 83 days |
| practical threshold (0.0035 x sqrt(h)) | 0.0093 (met) | 0.0186 (met) |
| sub-period P1 2021-01..2022-12 (730 days) | 0.1035 (t 8.2) | 0.1348 (t 5.3) |
| sub-period P2 2023-01..2025-06 | 0.0825 (t 5.1) | 0.1015 (t 3.4) |
| regime up / down (BTC 90-day return sign) | 0.103 / 0.078 | 0.141 / 0.088 |
| assets per valid day (mean / min) | 115.3 / 40 | 115.4 / 40 |
| coverage (valid signal and return / member-days) | 99.78 % (188,345 / 188,758) | 99.78 % (186,077 / 186,490) |
| missing signal / missing return member-days | 412 / 350 | 412 / 350 |
| distinct assets with an observation | 411 | 404 |
| delisting zero-recovery sensitivity (not gating) | mean IC 0.0926, t 8.65 | 0.1185, t 5.71 |
| programme-wide Bonferroni (alpha 0.00111, non-gating) | passes | passes |

Disguise check (registered, gating, bound 0.7, mean daily cross-sectional rank correlation of S with the style): trailing 7-day return -0.094; trailing 28-day return -0.379; RSI14 -0.257; Donchian20 position +0.199; EMA12/26 gap -0.324; maximum |.| = 0.379 -> **passes**. Prefix invariance at 2022-06-30, 2023-12-31, 2025-03-31: exact. Reproducibility: second run in the same process and a run in a separate process give the identical result hash `4dce744e...`.

Budget consumption: N = 45 of 52 (43 + 2 configurations), 1 of 3 family slots, 1 of 1 market run for this family; remaining room: N 7, 2 family slots. No unregistered market experiment was run; no parameter, window, horizon or filter was changed; the two registered configurations are both reported.

## Caveats the owner must weigh before reading this as "good news"
1. **The signal is, to a large extent, a low-volatility signal.** The registered informational diagnostic shows a mean daily rank correlation of **-0.913** between S and trailing 28-day realised volatility (|rho| > 0.7 on 99.8 % of days). The disguise check did not gate on volatility (registered as informational), so the registered PASS does not separate "lottery demand" from "low volatility / size / quality of the asset". The economic mechanism that motivated H1 is therefore **not isolated**; at most the result supports a broader statement: assets with calmer recent price paths outperformed on this sample.
2. **The effect is about 10x larger than the scale used in the S9 power study** (daily-equivalent IC 0.005-0.02; here IC_h 0.09-0.12 for 7-28 days). Such magnitudes should raise suspicion of a structural cause (for example the secular decline of small and illiquid coins over 2021-2025, universe-construction effects, or other confounds shared by every volatility-ranked signal). No bug was found: the alignment of window and returns is verified by closed-form tests, the signal is prefix-invariant on the real data, the sensitivity with zero-recovery delistings is the same, and coverage is 99.8 %. Plausible is not proven.
3. **Research-only data.** Binance Vision data is licensed for research / personal non-production backtesting; nothing here is a commercially usable result.
4. L1 uses a zero-latency entry at the next open and no costs; a long-only portfolio captures only one side of the cross-sectional spread; turnover (weekly) would be cost-sensitive. All of that belongs to L2, which is **not** approved.
5. The IC is a rank statistic over the whole cross-section; the profits of a long-only top-quintile portfolio depend on the tails, the crash behaviour of volatile coins, delistings and capacity, none of which L1 measures.
6. Power note (M2): for h = 28 the S9 power was optimistic and HAC at lag 2h is mildly over-sized; with t = 5.6 this does not change the conclusion.

## What this result does NOT license
No L2/L3 evaluation, no strategy implementation, no paper or live trading, no paid service, no use of the holdout, no new hypothesis, no variant of H1 (including a "volatility" variant) without a new owner approval and a new registration charged against the remaining budget.
