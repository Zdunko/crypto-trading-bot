# M2 report — H1 L1 pre-registration, registration, and power applicability (written BEFORE any market data is read)

## What is frozen (`protocol/h1_l1_preregistration.json`, sha256 `469607453ca5261c83d7903ed95ea69fdee87f05b47878d0472feb551cc48741`)
Signal MAX3 over a fixed 28-day window, S = -MAX3, one-sided test of mean daily cross-sectional Spearman IC > 0; entry at the open of day t+1, return open to open over h = 7 and 28 days; point-in-time 5 M universe (S4 rules) fixed per month, identity epochs respected, missing-exit rule = last observed close (zero-recovery delisting is a reported sensitivity only); Newey-West lag 2h, Holm over the two configurations; sub-periods 2021-01..2022-12 and 2023-01..2025-06-29; regimes by BTC trailing 90-day return; minimum sample gates (>= 1000 valid IC days, >= 30 assets on average, coverage >= 0.80); practical threshold = S9 break-even IC 0.0035 x sqrt(h); disguise bound 0.7 on five rejected-family styles; prefix-invariance and reproducibility checks; PASS rule and the termination rule (no variants). Data end: last completed daily candle 2025-06-29 (the loader refuses the holdout).

Multiple testing: Holm over the 2 H1 configurations. The owner's phrase "any relevant historical hypothesis tests" is read as tests of the same hypothesis or signal (none exist among the 43 earlier configurations); the programme-wide Bonferroni over N = 45 (alpha 0.00111) is reported next to the primary result as a **non-gating sensitivity**.

## Registration (M0 completed here, before any result)
Family `h1_lottery_max3`: 1 family slot, 2 configurations, N 43 -> 45 (cap 52), status `preregistered`, 0 market runs; ledger entry and spec-registry entry; run approval for the exact spec hash, scope L1 only (amendments A11 for the ledger, A12 for the pinned artifacts; no historical freeze/acceptance record was edited: tests follow the amendment chain). H2, H3 and all other families stay unauthorised. The S6 feasibility gate (strategy-family schema) is not applicable to an L1 signal test and was not used as a precondition; the runner's guard checks the budget slot, the exact spec hash and the owner approval instead.

## M1 (Risk V3 integration) status
G1 (40 assets, engine, V2 equivalence on the clean feed through one year, defects, determinism), G3 (causal epoch-based status source, prefix invariance, leaky source fails), G5 (47 h / 49 h resume, +-30 %/+-60 % first print), G2 policy (zero recovery primary, no sale of impaired assets): 13 tests, all passing. `risk_v2.py`, `risk_v3.py` and every limit are unchanged; V3 is not used by L1 (no engine, no costs at L1).

## Do the S9 power estimates apply to the registered horizons? (synthetic, `m2_horizon_power_results.json`)
S9 estimated power for 1-day IC at a 1-day horizon. Here: overlapping h-day forward returns, signal persistence phi in {0.9, 0.97}, Newey-West lag 2h, 400 replications, power reported against the REALISED mean daily IC of the same data (comparable to S9).

| Per-day-equivalent IC about 0.01 | S9 (1-day) | h = 7 | h = 28 |
|---|---|---|---|
| N = 40, phi 0.9 / 0.97 | 0.67-0.69 | 0.55-0.71 | **0.30-0.33** / 0.57-0.61 |
| N = 100, phi 0.9 / 0.97 | 0.93-0.98 | 0.84-0.99 | **0.53-0.55** / 0.81-0.92 |

Size at zero skill (nominal 0.05): h = 7: 0.045-0.078; h = 28: 0.045-0.093.

**Discrepancies (reported before market access; no criterion was changed):**
1. For h = 7 the S9 estimates transfer approximately (about 0.1 lower in the worst cell).
2. For h = 28 the S9 estimates are **optimistic** when the signal is not very persistent (phi 0.9: power 0.30-0.55 at IC 0.01 instead of 0.67-0.98); with a very persistent signal (phi 0.97) h = 28 is as powerful as or more powerful than the 1-day case. The true persistence of MAX3 ranks is unknown (an assumption).
3. HAC with lag 2h is mildly over-sized in some cells (up to 0.093 at h = 28 versus the pre-registered 0.07 size limit of S9): a marginal Holm p between roughly 0.01 and 0.05 should be read with caution. The block-bootstrap p is reported alongside.
4. The practical threshold (0.0035 x sqrt(h)) is a conservative mapping: realised mean IC_h per unit daily IC is 1.4-1.7 (phi 0.9) or 2.2-3.3 (phi 0.97), below sqrt(h) = 2.6 / 5.3; the threshold for h = 28 (0.0186) therefore corresponds to a per-day-equivalent IC of about 0.012 (phi 0.9) to 0.006 (phi 0.97). It was fixed before the study and is not relaxed.
Consequence: the L1 evidence for h = 28 is weaker than S9 suggested; h = 7 is close to the S9 numbers. A NO-GO from h = 28 alone is therefore not informative about small effects. Under the registration the outcome rule is unchanged.

## Gates for M3 (all must hold before data is read)
M1 tests pass; registration present and guard accepts the exact spec hash; pre-registration, code and this report are committed and pushed; the loader refuses the holdout; nothing candidate-specific was computed on market data. They hold at this commit.
