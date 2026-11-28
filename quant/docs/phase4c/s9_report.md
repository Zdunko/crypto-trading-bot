# S9 report — Evidence Ladder, signal discovery design and practical transition

Branch `claude/freqtrade-trading-system-b82aek`, draft PR #1. Pre-registration: `60cce9b` (criteria, rubric weights, power scenarios, budget accounting; before any S9 design). The Croatian owner report is delivered in the session; this file is the English record.

## Outcome
- **S8 finalised**: job-level CI of `fb4e8f9` recorded (24 success, 5 skipped release-only jobs, 0 failed, 0 cancelled); `s8_acceptance_record.json` freezes it. Historical conclusions preserved (NO-GO under the original protocol stands).
- **Evidence Ladder** (`protocol/evidence_ladder_v1.json`, `s9_evidence_ladder.md`): L1 signal, L2 economic viability, L3 robustness, L4 forward paper trading, L5 controlled live (unreachable without separate approval); non-implication rules; T1-T10 and all manifests untouched; no rejected strategy reclassified.
- **Three hypotheses** (`s9_signal_hypotheses.md`): H1 lottery-demand avoidance (MAX3, window 28), H2 post-listing age decay, H3 Amihud illiquidity. Scores were fixed before the simulation (`s9_selection.json`).
- **Recommended candidate: H1** (weighted score 3.55; H3 3.35; H2 3.15), exactly one, selected without any market performance.
- **Power** (synthetic, HAC, three dependence scenarios): size 0.03-0.055; at N = 40 power is 0.27-0.34 / 0.67-0.69 / 0.96-1.00 for daily IC 0.005 / 0.01 / 0.02; at N = 100 it is 0.53-0.56 / 0.93-0.98 / 0.995-1.00; detectable IC at 80 % power about 0.014 (N = 40), 0.008 (N = 100), not reached at N = 10. Break-even IC is 0.0035 (H1), 0.0009 (H3), 0.0004 (H2): below the detectable IC, so **no hypothesis is "powered" at its break-even effect** (pre-registered definition). L1 therefore screens for effects 2-4x larger than break-even; a non-rejection terminates the hypothesis.
- **Budget**: S9 adds nothing to N (43/52). The selected family would use 1 of 3 family slots and 2 configurations (N -> 45); non-selected hypotheses are not tested; no exploratory experiments.
- **V3**: minimum integration plan for G1, G3, G5; zero recovery as the primary assumption with sensitivity; an assumed recovery is never executable liquidity.
- **Licensing**: exact documents and owner actions listed; nothing re-fetched; no commercial right assumed.
- **Roadmap**: milestones M0-M8 with effort, gates and termination conditions to a paper-trading bot (about 12-15 sessions if every gate passes; first real test M3 after about 4).

## Limitations
Power numbers are synthetic (idealised dependence: HAC lag 10, regime persistence 0.99, independent idiosyncratic shocks); the IC-to-return mapping assumes a daily-IC unit and a top-quintile mean z of 1.4; turnover and costs are assumptions, not measurements; the mechanisms' literature is unverified here; H1 is related to short-term reversal (a disguise check is registered); licensing is unverified outside Binance Vision.

## Unchanged by S9
T1-T10, all manifests and acceptance records, S6 gate and thresholds, risk_v2/risk_v3, budget N 43/52 with 0 further families, run approvals and spec registry empty, holdout (not accessed, not even metadata). Family A rejected; B, B2, C1-C3 unapproved. No strategy code, no market experiment, no paper/live trading, no paid service, no merge/deploy.

## Stop
Implementation of the recommended plan (M0 onward) needs the owner's explicit written approval.
