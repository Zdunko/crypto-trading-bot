# S7 report: risk integrity and research methodology review

Criteria pre-registered in `s7_criteria.json` (commit `5ffce7c`) before any S7 code or analysis; unchanged. No strategy implemented or registered, no market backtest or optimisation, no Family B/B2 approval, no holdout access (not even metadata), no research-budget change (N 43/52, 0 further families), T1-T10 and all S2 parameters untouched, the S6 gate and its thresholds untouched, no paper/live trading, no paid service.

## 1. Freeze (F1, F2)
`protocol/s6_acceptance_record.json` freezes the accepted S6 artifacts (criteria, gate, benchmarks, registries, reports, tests, freeze records) and `tests/test_s6_acceptance.py` recomputes them; every historical freeze test (S2, S4, S5, S6) passes; `verify5`, T1-T10 and the budget (N 43/52, no family, no run approval) are unchanged.

## 2. Risk layer V3 (R1-R12): `quantlab/risk_v3.py`, `protocol/risk_v3_spec.json`, 51 tests
| Property | Implementation | Evidence |
|---|---|---|
| Elapsed-time stale detection (R1) | `StaleTracker`: time since the end of the last completed candle; STALE at >= 48 h (the S2 intent) | hourly: shutdown at the same timestamp as V2 (47-50 h after the last candle); with a 4-hour monitor interval the alarm is still at 48 elapsed hours (12 candles, not 48) |
| Strategy clock separate from risk clock (R2) | hourly monitoring ticks; optional `decision_every` (for example daily) | daily decisions: 10 inner calls in 10 days, 240 risk ticks; a stale asset under daily decisions is caught within 48 hours (S2: 48 days); any monitoring cadence other than the configured one is refused with `ConfigError` |
| Explicit statuses (R3) | DELISTED, SUSPENDED, UNTRADEABLE from a feed, MISSING from the history: alarm in the same tick; GAP below the horizon valued at last known | recovery before 48 h: no alarm; recovery after an alarm: SHUTDOWN stays permanent |
| No assumed liquidation (R4) | impaired exposure stays in the gross passed to the S2 machine; halt sells are attempted but never counted as done | a stuck asset stays in the book, the machine ends in SHUTDOWN and never in NORMAL/REENTRY; tier-2 flatten with a stuck asset ends in SHUTDOWN |
| Three valuations (R5) | last-known (engine), conservative (impaired positions at `gate_recovery` x last-known, default 0, drives the machine), realized (closed trades plus explicit DELISTED write-offs) | closed-form on fixtures for r = 0, 0.5, 1 |
| Sensitivity (R6) | `recovery_sensitivity` for r in {0, 0.25, 0.5, 0.75, 1}: drawdown, final equity, tier trips | monotone; r = 1 equals last-known; r = 0 equals conservative |
| Concealment (R7) | `capital_protection_report`: last-known vs conservative drawdown against the unchanged 20 % limit | case with last-known drawdown < 5 % and conservative > 20 %: V3 trips in the very tick (floor and integrity), the report FAILS and flags `concealed_by_stale_valuation`; frozen V2 sees nothing |
| S2 preserved (R8, R9) | `risk_v2.py` untouched; V3 subclasses the wrapper and requires the unchanged `RiskV2Config` | with no impairment V3 equals V2 on 6 volatile seeded scenarios (identical engine hash, identical transition records, tiers/flat cycles exercised); tiers 10/15/18 %, hard limit 25 %, limit 20 % asserted |
| Determinism and restart (R10) | cross-process engine hash; tracker rebuilt from history | equal |
| Properties (R11) | 30 seeded random scenarios | conservative <= last-known always, HWM monotone, no buy after SHUTDOWN, conservative = last-known - impaired x (1 - r) |
Not changed and not claimed: the 48-hour horizon, the 18 % tier, the 20 % limit. V3 needs hourly candles; assets that are merely quiet for 48 h are treated as impaired (conservative by design). V3 is not adopted by any evaluation yet.

## 3. Feasibility-gate methodology audit (M1-M4)
`s7_gate_methodology_audit.md`: the gate is coherent but exposure-favouring, overstates effective sample size under overlap/regimes (design effect up to ~7.8x vs ~1.2), cannot verify declared exposure (frozen layer: mean invested share 0.32-0.65, 58-68 % of synthetic paths shut down; B2 fails the unchanged MDE criterion at those shares) and its absolute-Sharpe statistic is not the right test for timing/defensive claims; the normal MDE is adequate at daily frequency. Existing gate unmodified; improvements only as `proposals/feasibility_methodology_v2_proposal.json` (not adopted, with calibration targets and adoption criteria).

## 4. Strategy family review (C1-C4)
`s7_strategy_family_review.md`: B2 reassessed plus three distinct candidates (rebalancing sleeve, cross-sectional low-volatility tilt, listing-maturity screen); assumptions and measured evidence labelled; none disguised (B2 flagged as related to the rejected per-asset momentum). Key arithmetic: minimum detectable relative IR is 1.17 on 4.5 years (power 0.16 / 0.28 / 0.52 / 0.68 at IR 0.3 / 0.5 / 0.8 / 1.0; IR 0.5 would need ~25 years). **Recommendation: NO-GO for all four; budget preserved.**

## 5. Production-readiness roadmap (P1)
`s7_production_readiness_roadmap.md` and a pointer in `ROADMAP.md`: eight stages (data legality, exchange integration, reconciliation, independent out-of-sample validation, paper trading, monitoring, security/emergency shutdown, limited-capital live criteria), documentation only.

## 6. Regression and bookkeeping (G1-G4)
Full suite and `check.sh` (counts in the final message); ledger amendment A10 (S7 audit entry, no count change); `protocol/s7_freeze_record.json` and test; limitations register extended (L-STALEPOS-V3, L-GATE-N, L-POWER); `research_budget.json`, `spec_registry.json` registered list and `run_approvals.json` unchanged.

## 7. Remaining risks
V3 is validated on synthetic fixtures only and not integrated into any evaluation or exchange adapter; hourly-only monitoring; recovery assumption is a parameter not a measurement; the simulations behind the audit use harsh synthetic drifts (relative evidence only); modest effects cannot be demonstrated on this dataset; legal clearance of any production data path is open; the earlier S4-S6 limitations stand.

## 8. Recommendation
GO for S7 deliverables (risk layer V3 as validated infrastructure, methodology audit, roadmap). NO-GO, pending your explicit approval: adopting V3 for evaluations, adopting the v2 gate methodology, implementing/registering B2 or any candidate, any market evaluation, holdout access, paper/live trading, paid services.
