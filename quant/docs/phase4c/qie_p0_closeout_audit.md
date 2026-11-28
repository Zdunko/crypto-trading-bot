# QIE-P0 — closeout audit of the research cycle (documentation only)

Task QIE-P0 of Issue #2 (owner approval relayed in comment 7237703953). **Read-only audit:** no backtest, no market download or statistic, no holdout access (not even metadata), no code change, no registration, no budget consumption. Evidence classes used below: **V** = verified in this session from a file, log or API response I read; **R** = reported by an earlier record that I did not re-verify now; **U** = unknown / not read. Infrastructure is never assumed to be a cause.

## 1. Repository and PR state (V)
Branch `claude/freqtrade-trading-system-b82aek`, HEAD `8766bf4` (before this task's commit), 85 commits, 359 files changed vs base `develop`, working tree clean. Draft PR #1 is **open, draft, not merged**, mergeable state "clean". `AGENTS.md` rules are unchanged and still binding (dry-run only, spot only, no credentials, no fabricated results, draft PR only, no auto-merge, tests before "done"). Research budget file: `total_n` 45, `max_total_n` 52, one further family (`h1_lottery_max3`), caps 3 families / 3 configurations per family / 1 market run and 1 diagnostic replay per family.

## 2. CI evidence by commit (V unless stated; job level, skipped and cancelled shown separately)
| Commit | Quant CI | Upstream Freqtrade CI (29 jobs) | Notes |
|---|---|---|---|
| `dcb7f98` | success | 24 success, 5 skipped (release/deploy), 0 failure, 0 cancelled | baseline after M5 stop |
| `9af2d4a` | success | 19 success, 2 skipped, **7 cancelled, 1 failure** (`Build (3.13)` = aggregator) | four test jobs cancelled seconds after my next push (timing only; cause not confirmed); **no completed upstream test results for this commit** |
| `89cbbd1` | success | `Tests and Linting (macos-26, 3.14)` **failure** (+ `Build (3.13)` aggregator) | cause read from the log: my test compared platform-specific floating-point hashes; behavioural fields identical |
| `7886c35` | (not re-read) | `Tests and Linting (windows-2025, 3.14)` **failure** (+ `Build (3.13)`) | cause read from the log: my test hashed CRLF bytes on Windows |
| **`8766bf4`** | success (runs 156 push, 157 pull_request) | **24 success, 5 skipped** (Docker Package Cleanup, Docker Build and Deploy, PyPI, TestPyPI, Notify), **0 failure, 0 cancelled** (run 46129475243) | final M6-S0 state; macOS-15, macOS-26, Windows and Ubuntu jobs all completed successfully |
Unknown (U): zizmor on `8766bf4` was not read; upstream CI on the commit that carries this task is read after the push and reported separately. Skipped release jobs are not passes of anything.
**Reclassification note:** `L-CI-MAC`, `L-MACOS-15`, `L-MACOS-26` in the limitations register describe earlier cancelled macOS jobs as "infrastructure". On `8766bf4` those jobs completed successfully, and on `89cbbd1` macOS-26 failed because of my own test. The "infrastructure" label was an inference, never a verified cause; this audit records it as **unexplained cancellations, cause unknown, last observed result success** (register row `L-CI-RECLASS`).

## 3. Closed research cycle (frozen outcomes; R = from the cited records, hashes in the freeze record)
| Stage | Outcome | Source |
|---|---|---|
| Phase 3 (OKX, 2021-01..2025-07, 4 strategies, T1–T10) | **all four rejected**; holdout never opened (no survivors; the holdout stage refuses without a verdict) | `quant/reports/phase3_evaluation_report.md`, `protocol/e_verdict.json` |
| Phase 4 R1 risk overlay | rejected on research data | `quant/reports/phase4_risk_research_report.md` |
| Family A (A1, A0, V0) | **not credible** (fails T1/T3/T4/T7; terminal breaker halted V0 after 8.7 % of the period; A1 +24.4 %, V0 +30.0 % vs B1 +1896 %) | `quant/reports/family_a/evaluation_report.md` |
| S8 feasibility | NO-GO under the pre-registered rule; minimum detectable IR 1.17 on 4.5 years | `s8_report.md` |
| H1 (MAX3) L1 | **PASS** (mean IC 0.117 / 0.092), rank correlation −0.913 with 28-day volatility (confound); one run consumed | `m3_l1_report.md`, `m3_l1_results.json` |
| H1 M4 L2 | **NO-GO** (V3 shutdown 2021-02-23 / 2021-05-19; unprotected drawdown 83–88 %); one replay consumed | `m4_l2_report.md` |
| M5 Phase 1 | calibration **STOP** before market access; round-2 validation max size 0.0727 > 0.07; family `h1_vol_control` never registered | `m5_phase1_calibration_stop.md` |
| H1 | **terminated** (Option C, owner via Issue #2); incremental MAX3 effect **unresolved, not disproven** | `protocol/m6_design01_approval_record.json` |
| M6-DESIGN-01 / M6-S0 | design only, then synthetic validation: claims C1–C4 **falsified**, overlap = risk overlay on Family A V0 / S7 C2 / M4 comparator, recommendation **NO-GO for registration**; amendment A20 | `m6_s0_report.md` |
Budget: **N = 45 / 52, families 1 / 3** (no reset, no new registration). Historical manifests (v3–v6), amendments A1–A20, rejected configurations and negative results are preserved unchanged.

## 4. Stale or conflicting status entries found, and how they were reconciled (additive)
1. `PROJECT_STATUS.md` header and first table were dated 2026-11-25 ("Phase 4 … awaiting owner review", "Strategies … none evaluated on market data", "124 passed"); the repository has since run Phase 3, Family A, H1 L1/L2 and later stages and has 800+ tests. → an **authoritative current-state block** was added at the top; the old table is marked historical (text kept).
2. `ROADMAP.md` still says M5 "awaits the owner's decision (N 47/52)" and lists Phase 4/5/6 without the research-cycle outcome. → a **current-direction section** was added at the top (QIE, design only); old text kept.
3. PR #1 description (V, read via API) still says "38 passed" and "No market data downloaded and no performance results exist yet". It is stale and **was not edited** (outside this task's scope); the owner may update it.
4. `PROJECT_STATUS.md` sections "GitHub CI results", "Not yet verified" and "Open decisions for the owner" reflect 2026-11-25 and are marked historical by the new block.
5. Register entries `L-CI-MAC`, `L-MACOS-15`, `L-MACOS-26`: see section 2 (row `L-CI-RECLASS`).
6. `AGENTS.md` (V) names `.github/workflows/quant-bias-check.yml`, **which does not exist** (only `quant-ci.yml` and `quant-research.yml`; bias checks are a stage of the latter), and its layout table does not list `quant/protocol/`, `quant/reports/` or the Issue #2 coordination protocol; not edited here (owner file); noted for P1.

## 5. Runtime-safety and consistency findings (V from files read; none changed)
1. **Dry-run/spot policy is enforced by static checks in CI/`check.sh`, not at runtime.** Someone running Freqtrade with another config bypasses it (AGENTS.md calls this "CI-enforced"; it is accurate but not a runtime guard).
2. **`strategy_policy` (AST) covers only `quant/strategies` and `quant/strategies_r1`.** Engine-level strategies (`family_a.py`, `l2_portfolio.py`, `lv_sleeve_harness.py`) can use engine capabilities such as add-to-position buys (`Order.add`) without that policy applying; the bounded-averaging rule is therefore enforced by design review, not by tooling there.
3. **`quant-research.yml` is a market-access workflow reachable by a commit-message marker on any `claude/**` push**, including `[phase3-data]`, `[phase3-holdout]`, `[family-a-eval]`; `workflow_dispatch` triggers the data download unconditionally. The holdout stage reportedly refuses without `e_verdict.json` / if already done (R, from the workflow header; guard strength not re-audited). Commit messages must therefore never contain these markers. Recommendation: review/disable before any new work.
4. **Two capital-protection mechanisms coexist**: the engine breaker (`ExecConfig.breaker`, 15 % reduce / 20 % halt) and Risk Management V3; their interaction is exercised only in M4/M6-S0 fixtures.
5. **V3 shuts down terminally on any stale (> 48 h) or delisted held asset regardless of loss size** (M6-S0 F08b/F09/F10) and after a tier-2 event the re-entry budget can be smaller than the minimum notional (F02). These are design properties of the frozen layer, not defects of tests; V3 was not changed.
6. **Platform-sensitive tests**: hashes of floating-point results differ across platforms and pinned-file hashes must be LF-normalised (two CI failures were caused by this in M6-S0; fixed in tests, not in code).
7. **Dataset tables are committed** (`quant/dataset/`, derived from Binance Vision, CC BY-NC-SA 4.0): research-only, non-commercial; no raw data committed.

## 6. Documentation versus code and evidence
The numbers quoted in the research reports match the stored result files where I cross-checked them in this cycle (M4/M5/M6-S0 files); older reports (Phase 3/4, Family A) were **not re-verified** now (R). Known inaccuracies are the stale status entries of section 4. Documentation volume is large (76 markdown, 101 JSON files under protocol/docs/reports/journal) and several documents restate numbers; the freeze record pins the source files so later edits are detectable.

## 7. Unresolved limitations and licensing
36 rows in `s4_limitations_register.md`; open ones include data licensing (`L-LIC`, `L-LIC-VERIFY`: Binance Vision is research-only, **commercial rights unresolved**, the licensing inquiry draft was **never sent**), identity/liquidity/volume discrepancy (`L-ID`, `L-LIQ`, `L-X1`), V3 stale-position design (`L-STALEPOS*`, `L-L2-V3-SHUTDOWN`), power limits (`L-POWER`, `L-FEASIBILITY`), `L-H1-VOL`, `L-M5-CALIBRATION` (owner decision; superseded by termination), and the CI notes above. Licensing restrictions: no commercial or operational use of the data; no assumption of rights.

## 8. What this task did not do
No new backtests, downloads, statistics or holdout access; no registration, optimisation, strategy or engine change; no change to T1–T10, V3, caps or budget; PR #1 stays draft.
