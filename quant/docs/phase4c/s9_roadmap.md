# S9 — Roadmap: from the recommended signal hypothesis to a paper-trading bot

"Session" = one focused working session (estimate, not a measurement). Nothing starts without the owner's written approval of the gate before it. Budget: the family uses 1 of 3 remaining family slots and at most 3 configurations (N 43 -> at most 46 of 52).

| M | Milestone | Effort | Gate to proceed | Termination condition |
|---|---|---|---|---|
| M0 | Owner approves registering the recommended hypothesis as one family and the budget accounting | 0.5 | written approval | not approved: stop; no experiment exists |
| M1 | Risk V3 integration tests G1, G3, G5 (plan in `s9_v3_minimum_integration_plan.md`) | 2 | all three pass, V2 equivalence on the clean subset | a test cannot pass without weakening a threshold: stop |
| M2 | L1 pre-registration: formula, universe rule, window, horizons (<= 3), Holm family, fixed lags, seeds, sub-periods, disguise check, lookahead/survivorship tests on synthetic fixtures | 1.5 | criteria committed before any market data of the signal is read; owner approves the single run | any market-derived look before registration: the configuration is void and counted |
| M3 | L1 run: one execution of the registered configurations, report significance only | 1 | L1 rejected after Holm in the registered direction and passes the disguise check | not rejected: **terminate the hypothesis** (no variant search); N stays charged |
| M4 | L2 economic viability: long-only portfolio through the engine with V3, 1x and 2x costs, comparators | 2 | net active return positive at 2x costs, break-even cost >= 2x assumed, T4 drawdown respected | fails any: terminate; report "L1 only" honestly |
| M5 | L3 robustness: pre-registered sub-universes, periods, regimes | 1.5 | pre-registered share of slices positive, no single-slice dependence | fails: terminate |
| M6 | Licensing resolved for the intended venue and data feed (owner, parallel from M0) | owner time | written permission or documented acceptable terms | denied or ambiguous: research stays research-only; no paper trading on that feed |
| M7 | Paper-trading bot (Freqtrade `dry_run` true, daily rebalance, PIT-safe data job, order/fill reconciliation, V3 monitoring, alerting) | 4-6 | owner approval after M4-M6; operational acceptance checklist | unreconciled orders or risk breach: halt, fix, restart L4 clock |
| M8 | L4 forward period (months of calendar time) | owner time | pre-registered tracking-error and incident criteria | breach: stop; L5 is never implied |

Global termination: budget N reaches 52; two consecutive rejected registered configurations; owner stop; any hard rule at risk (dry_run must stay true, no credentials, spot only). Total engineering before a paper-trading bot: about 12-15 sessions if every gate passes; the expected outcome of a single family is rejection, which the ladder is designed to reach cheaply (M3 is the first real test, after about 4 sessions).
