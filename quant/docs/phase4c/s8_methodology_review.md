# S8 — Independent methodology review and alternative research designs

All numbers: `docs/phase4c/s8_design_study_results.json` (seeded, byte-reproducible, pinned by `tests/test_design_study.py`). **Synthetic only**: they describe statistical methods, not any market or strategy. Parameters were pre-registered in `s8_criteria.json` before any code existed. Monte-Carlo standard error of a rejection rate at 400 replications is about 0.011.

## 1. Review of `feasibility_methodology_v2_proposal.json` (still NOT adopted)
| Item | Finding | Verdict |
|---|---|---|
| MDE / power arithmetic | Simulated iid power at IR 1.0 is 0.68 vs analytic Φ(IR·√4.5 − 1.645) = 0.683; at IR 0.5 0.28 vs 0.28. The gate's MDE logic is arithmetically right; the problem is the sample, not the formula. | confirmed |
| V2-1 (overlap/regime-aware effective sample) | On **return series** the measured design effect is only 0.97–1.23 under the pre-registered DGPs (AR(1) 0.15: 1.23; persistent regimes of ±0.001/day: 1.08). The large understatement found in S7 concerns **episode counting** with overlapping holds, not tests on return series. | keep, but restrict V2-1 to episode counts; do not use it to inflate return-series tests |
| V2-2 (claim-type-specific power) | Direction is right. A paired series is just another series: its power is set by *its own* IR (α/tracking error). Pairing helps only because a highly correlated benchmark lowers variance, which also shrinks α; it is not free power. | keep; require the declared effect as IR of the paired series |
| V2-3 (declared invested share from simulated risk layer) | Unaffected by S8; remains correct. | keep |
| V2-4 (report non-normality / HAC) | HAC (Newey-West lag 10) kept size ≤ 0.07 on all five DGPs (0.04–0.07) and matches the bootstrap in power. | keep, make HAC the default paired test |
| V2-5 (ex-post comparators are non-tradable) | Unaffected. | keep |
**Not adopted.** Adoption stays a separate, owner-approved, versioned step; no S6 threshold is changed.

## 2. Dependence-aware inference (D1)
Size at nominal 0.05, one-sided, 1,642 daily observations (4.5 years):
| DGP | naive t | Newey-West L10 | block L10 | block L20 | block L40 |
|---|---|---|---|---|---|
| iid normal | 0.065 | 0.070 | 0.068 | 0.078 | 0.073 |
| Student-t(3) | 0.043 | 0.050 | 0.048 | 0.050 | 0.053 |
| AR(1) 0.15 | **0.075** | 0.043 | 0.045 | 0.043 | 0.048 |
| vol clustering | 0.055 | 0.058 | 0.063 | 0.068 | 0.065 |
| persistent regimes | 0.058 | 0.058 | 0.055 | 0.058 | 0.050 |
Pre-registered limit 0.07: **Newey-West and block L10 pass everywhere**; naive t fails under autocorrelation; block L20/L40 exceed 0.07 on iid (0.078, 0.073), within about 2 Monte-Carlo standard errors of 0.07. The block bootstrap gives **no power advantage** over Newey-West. The regime effect was fixed a priori at ±0.001/day, which is mild; stronger real regimes are a limitation of the study, not a conclusion.

Power (Newey-West) on 4.5 years: IR 0.3 → 0.14–0.19; IR 0.5 → 0.22–0.33; IR 0.8 → 0.40–0.54; IR 1.0 → 0.57–0.69. **No dependence-aware method reaches 0.8 at IR 0.5; none can**, because the dependence inflation is small and the sample is short.

## 3. Insufficient power vs negative expected performance (D2)
With the same 4.5 years (HAC 95 % interval half-width ≈ ±0.77 annualised IR):
- True IR +0.5: the test fails to reject 72–73 % of the time, yet the upper bound is below 0 in 0–1 % of runs → a non-significant result is **not** evidence of poor performance.
- True IR 0: false "conclusive negative" 5–8 %.
- True IR −0.5: failing to reject 99 %, but a conclusive-negative statement (upper 95 % bound < 0) only in 27 %.
Conclusion: on this history a single non-significant result separates neither "skill 0.5" from "skill 0" nor "skill 0" from "skill −0.5". A rejected strategy is "not proven", never "proven bad", unless a separate pre-registered negativity bound is met. Family A's rejection stands because it failed pre-registered *safety/robustness* criteria, not because of a power-limited non-rejection.

## 4. Alternative research designs
| Design | S8 finding (synthetic) |
|---|---|
| Purged + embargoed validation (D3) | On pure noise with 20-day overlapping labels, shuffled K-fold shows a spurious IC of **+0.085** (≈13 standard errors); contiguous folds without purging −0.023 and with purge+embargo −0.025 (the same within error, small negative CV bias). Purging removes 2.4 % of training data. Needed to forbid shuffled CV and to stop boundary leakage in any model-based family; it creates **no extra power**. |
| Breadth / cross-section (D4) | Average pairwise correlation 0.55–0.68; an equal-weight portfolio of 5–100 assets has only **1.4–1.7 effective independent assets**. More assets do **not** create independent observations for absolute claims. For relative cross-sectional claims, power rises with N only because the achievable IR rises (≈ IC·√N): at IC 0.01, IC-test power 0.19/0.48/0.75/0.98 and top-quintile active IR 0.21/0.52/0.76/1.22 for N = 5/20/40/100. Power of the long-only active-return test then follows its own IR (0.82 at IR 1.22; 0.30 at IR 0.52), exactly like any other test. The IC value is an **assumption**, not evidence. |
| Breadth really available | PIT eligibility (S1, ≥ 5 M USDT median 90-day volume): 7 (2018-07), 10 (2019-01), 9 (2020-01), 40 (2021-01), 186 (2022-01), 54 (2023-01), 112 (2024-01), 169 (2025-01). N ≥ 40 exists only from 2021; before that breadth ≤ 27 even at 1 M. |
| Longer history (D5) | Years needed for 80 % power: IR 0.5 → 24.7 (iid) to 30.5 (AR(1)); IR 0.8 → 9.7–11.9; IR 1.0 → 6.2–7.6. Power at 13 years: IR 0.5 → 0.49–0.56 (below target), IR 0.8 → 0.83–0.89. Longer legal history would mostly add BTC/ETH calendar time, not independent assets. |
| Selection bias / multiple testing (D6) | Best of 43 null strategies has in-sample Sharpe **1.04** and is "significant" unadjusted in **90 %** of runs; its out-of-sample Sharpe is −0.001. Holm/Bonferroni keeps the family-wise rate at 5.6 % (n = 43). Independent trials are assumed; correlated families would bias less. Holm remains mandatory. |
| Exposure-/risk-matched benchmarks | Remain necessary to avoid crediting exposure as skill (S7 q1/q7), but they are comparators, not a source of power. |
| Independent market/regime validation | No verified data source; cannot be assessed beyond the arithmetic above (an independent market adds `n` only if its returns are independent of the first, which crypto markets are not: pairwise correlation 0.55–0.68 in the simulation, an assumption). |
