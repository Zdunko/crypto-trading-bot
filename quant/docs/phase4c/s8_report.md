# S8 report — research feasibility resolution and methodology redesign

Branch `claude/freqtrade-trading-system-b82aek`, draft PR #1. Pre-registration commit: `a54ff97` (criteria, decision rule, seeds, committed before any S8 code). The Croatian owner report is delivered in the session; this file is the English record.

## Outcome
**NO-GO under the pre-registered decision rule** (`s8_decision_framework.md`): no research path reaches 80 % power at the declared plausible effect (information ratio 0.5) with any conceivable free history (about 13 years gives 0.49-0.56; about 25 years would be needed), and the only legally verified data is research-only. No threshold, criterion or manifest was weakened or edited. The result concerns what a historical backtest can *prove*; it is not evidence that no profitable strategy exists.

## What was done
1. **S7 validation** — failed upstream job analysed (`test_dca_order_adjust[2]`, timestamp straddling a minute boundary; 5,556 other tests passed on that job, including all quant tests). The rerun on `c3ce81b` was cancelled by the repository's concurrency group when the S8 pre-registration was pushed; the final outcome is recorded in `s7_validation_outcome.md` and was taken on the final S8 HEAD (the upstream code is byte-identical). No upstream test was modified, skipped or suppressed; CI was not weakened.
2. **Pre-registration** — `s8_criteria.json` (questions D1-D6, seeds, grids, decision rule) before any code.
3. **Design study** — `quantlab/design_study.py`, stored results `s8_design_study_results.json` (byte-identical on re-run; 11 tests pin the verdict-bearing numbers). One correction during the study: cross-sectional replications were raised from 100 to the pre-registered 400 and the active IR was added to the output (disclosed; no threshold or grid changed).
4. **Methodology review** — `s8_methodology_review.md` (v2 proposal item by item, dependence-aware inference, power vs negativity, purging, breadth, years needed, selection bias).
5. **Data and commercial feasibility** — `s8_data_commercial_feasibility.md`: 12 primary URLs could not be fetched (host not resolvable); every venue other than Binance Vision stays **unverified**.
6. **Risk V3 review** — `s8_risk_v3_adoption_review.md`: not ready; conditional on integration tests G1, G3, G5 and an owner decision on recovery assumption G2. Not adopted anywhere.
7. **Decision framework** — `s8_decision_framework.md` with power, limitations, effort and value for seven paths.

## Key findings (synthetic, 4.5 years, daily, one-sided 5 %)
- Newey-West and block-bootstrap L10 keep size ≤ 0.07 on all five DGPs; the naive t is over-sized under autocorrelation (0.075); block L20/L40 are marginally over 0.07 on iid (0.078/0.073).
- Power at IR 0.3 / 0.5 / 0.8 / 1.0: about 0.14-0.19 / 0.22-0.33 / 0.40-0.54 / 0.57-0.69. Dependence inflation on return series is small (design effect 0.97-1.23); the problem is sample length: 25-31 years for IR 0.5.
- Failing to reject is not evidence of negative performance: at true IR +0.5, 72 % of runs fail to reject and 0-1 % show an upper bound below zero.
- Shuffled K-fold leaks (spurious IC +0.085 on noise); contiguous purged and unpurged folds are equal within error; purging costs 2.4 % of training data and adds no power.
- More assets are not independent observations for absolute claims (1.4-1.7 effective assets for any N, pairwise correlation 0.55-0.68). Cross-sectional breadth raises the achievable IR (assumed IC), and power then follows that IR; breadth N ≥ 40 exists only from 2021.
- Selecting the best of 43 null strategies gives in-sample Sharpe 1.04 and "significance" in 90 % of runs unadjusted; Holm keeps 5.6 %.

## Limitations
Synthetic DGPs (regimes only mildly persistent, independent idiosyncratic shocks, constant volatility) are idealised; the IC grid is an assumption, not evidence; transaction costs, turnover and the long-only constraint are not in the cross-sectional power numbers; licensing is unverified outside Binance Vision; nothing was run on market data.

## Unchanged by S8
T1-T10, all manifests and acceptance records, the S6 gate and thresholds, `risk_v2.py`, `risk_v3.py`, research budget N = 43/52 with 0 further families, empty run approvals and spec registry, holdout (not accessed, not even metadata). Family A rejected; B, B2, C1, C2, C3 unapproved; no paper/live trading, no paid service, no merge/deploy.

## Stop
No strategy implementation, registration or market evaluation will start without the owner's explicit approval.
