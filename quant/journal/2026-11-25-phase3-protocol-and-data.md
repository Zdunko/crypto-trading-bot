# 2026-11-25 — Phase 3 start: data validation, protocol v2 freeze, bias-check expansion

- **Owner instructions (2026-11-25):** Phase 2 conditionally approved; OKX approved; T1 ≥ 200 trades, T4 ≤ 20 %
  (and ≤ benchmark), T5 ≥ 1.3, rest unchanged; explicit fee + slippage without double counting; untouched
  holdout; wider bias checks; report uncertainty/sample limits/survivorship; never optimise on the holdout;
  fix the Codecov failure without disabling upstream tests, no paid services, no secrets.

## Upstream Codecov failure (investigated)
- Run 45554153646: 15 jobs succeeded (Ubuntu 22.04/24.04/26.04, ARM, macOS-26, Windows 2022/2025, docs, mypy,
  pre-commit, the online exchange tests); 5024 tests passed on 3.14. The only failing step was the Codecov upload
  (`Token required - not valid tokenless upload`: the fork has no `CODECOV_TOKEN` and the step has
  `fail_ci_if_error: true`); matrix `fail-fast` then cancelled 7 jobs.
- Fix: one condition on the upload step (`github.repository == 'freqtrade/freqtrade'`, marked `FORK PATCH`).
  Tests still run with coverage; no secret and no paid service added. Result of the first full run is recorded in
  PROJECT_STATUS.md.

## Data (verified from the workflow log, run 45558871512, commit 331ab62)
- OKX spot 1h, 8 pairs, 2020-01-01 → 2026-11-25 (exclusive). 60 480 candles per pair (SOL 53 918, listed
  2020-09-30), **0 missing, 0 gaps, 0 duplicates, 0 impossible OHLC**; zero-volume candles ≤ 0.57 % (DOGE); one DOGE
  hourly move above 50 % flagged (warning). Dataset sha256 `fd94dcb6…8085`.

## Protocol v2 (frozen in this commit)
- Evaluation 2021-01-01 → 2025-07-01 (nine 6-month windows), holdout 2025-07-01 → 2026-11-25. Both fixed from data
  availability and calendar boundaries **before any return was computed**.
- Costs: Freqtrade `--fee` 0.10 % (base) / 0.20 % (stress); slippage 0.05 % / 0.10 % (+ equal extra on stop exits)
  applied afterwards; double-counting guard in code and test. See `docs/strategies/phase3_validation_thresholds.md`.
- Freeze mechanics: `protocol/frozen_manifest.json` + `python -m quantlab.protocol verify` in `check.sh` and in
  every research stage.

## Research run log (every run, including reruns)
| Stage | Run | Commit | Purpose / outcome |
|---|---|---|---|
| data | 45558871512 | 331ab62 | download + validation: passed (see above) |
| bias | 45560148402 | 6a80519 | 8 pairs x 6 half-year periods inside the evaluation period: lookahead clean 6/6 periods for all 4 strategies (0 biased signals); recursive 18/18 checks per strategy within 0.1 % (worst 0.034 % MomentumRoc, 0.026 % TrendEmaCross, 0.000 % others). Recorded in `protocol/bias_result.json` |
| upstream CI | 45560359246 | a573c62 | Windows 2025/3.14: 6 of 5104 tests failed - manifest keys used backslashes (**our bug**, Windows only); fixed in 5126a25 (`as_posix`); the Codecov patch itself worked (job ran to the end) |
| eval | 45561413667 | 18cdd1c | **failed before any result**: Freqtrade could not store the backtest export because the output directory did not exist (my runner bug; no result was produced or looked at). Fixed in the next commit |
| eval | 45561982317 | fedad61 | **completed; all four strategies REJECTED on T1-T10** (max drawdown 75-87 % vs limit 20 %, PF 1.06-1.21 vs 1.3). Two presentation defects noticed in the output: net returns below -100 % (post-hoc slippage not fed back into sizing, visible only for near-ruined accounts) and total-return bootstrap intervals that are unreadably wide. Reaction: add a reconciliation stage against Freqtrade's own totals, annualised intervals and a ruin flag. **No rule, parameter, threshold, period, config or strategy changed** (manifest verifies); verdicts cannot change because they do not depend on these outputs |
