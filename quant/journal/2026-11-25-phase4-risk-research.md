# 2026-11-25 - Phase 4 risk-management research (research data only)

**Question.** Does the pre-registered R1 overlay (ATR sizing and chandelier stop, exposure/correlation limits, BTC regime filter,
cooldowns, latched 20 % drawdown breaker) make TrendEmaCross / MomentumRoc acceptable under T1-T10?
**Protocol.** `quant/protocol/protocol_v3.json` (frozen, `frozen_manifest_v3.json`), R0 reference `r0_reference.json`. Holdout untouched.
**Trials.** 14 backtests per run, 2 research runs of the same frozen design (3 CI runs allowed, 2 used).

## Runs
| run | commit | outcome |
|---|---|---|
| 1 | 1e99407 (45644306073) | INVALID. Overlay equity used `wallets.get_starting_balance()` (= current balance in backtests): realised profit counted twice, phantom +16 % / +29 % peaks, breaker halted at ~10 % real drawdown. Detected because breaker peak > independently reconstructed MTM equity; reproduced offline; fixed; verified to 8 digits; regression test. No parameter/threshold changed. |
| 2 | 20b972b (45653877385) | VALID. Report: `quant/reports/phase4_risk_research_report.md` |

## Results (base costs, 2021-01-01..2025-07-01)
| | R0 net / DD | R1 net / DD / PF | R1 stress net | halts |
|---|---|---|---|---|
| TrendEmaCross | +583 % / 72.2 % | -19.0 % / 21.8 % / 0.83 | -45.8 % | 0 |
| MomentumRoc | +1074 % / 75.5 % | -14.8 % / 23.1 % / 0.85 | -30.4 % | 1 (2023-03-20) |

T3 benchmark rule: Sortino >= 1.81 (B1), drawdown <= min(20 %, 77.2 %). R1 fails T2-T8, T10; T9 not evaluated.
Ablations are descriptive only (see report); none selected.

## Conclusion
R1 as pre-registered does not produce an acceptable strategy: lower drawdown than R0 but negative after costs, T4 still failed, bias
check not clean. Not carried to the holdout. Open: trade-level causality check of the stateful overlay; whether the chandelier
stop (not the cooldown) explains the `no_stop_cooldown` ablation. Both need a NEW protocol version, not edits to v3.
