# Phase 4C - Risk Management and Evaluation Protocol V2 (PROPOSAL, design only)

Status: nothing here is implemented or run. No market experiment was executed for this document; the only numbers used are
re-readings of results already recorded (Family A run 45679466940), labelled as descriptive. T1-T10, all manifests, all historical
results and the holdout are untouched. Family A stays rejected as specified; no result is reclassified.

## 1. Findings

### 1.1 Why the circuit breaker permanently terminates trading
1. **By construction, not by accident.** The latch releases only with an owner approval timestamp; a backtest has none, so the first halt
   is terminal (documented and approved, but its consequence for evaluation was underestimated).
2. **A high-water-mark breaker on cash can never recover.** After a flatten the account holds cash, so equity cannot rise above the old
   peak; any rule of the form "resume when drawdown < x" or "resume after the peak is regained" is unreachable unless the peak is reset.
3. **The threshold is incompatible with the asset's volatility.** The 8-pair basket had a 90 % drawdown; a long-only crypto book at
   meaningful exposure crosses a 20 % drawdown from its peak within months with high probability. The breaker therefore fires early in
   almost every run (A0 after 10 days, V0 after 142 active days, A1 after 798).
4. **The breaker threshold equals the T4 threshold (20 %).** Reported max drawdown (20.0 %, 22.0 %, 20.4 %) is therefore set by the breaker
   plus gap overshoot, not by the signal. T4 became close to a measurement of overshoot. T4 is unchanged, but its information content
   under this design is low.
5. **Flatten realises the loss and removes all exposure at once**, so even a temporary dip costs the whole subsequent recovery.

### 1.2 Reconciliation of inconsistencies (recorded Family A numbers; descriptive re-reading, not a new experiment)
| Reported quantity | Problem | Correct treatment (proposed) |
|---|---|---|
| Average exposure 3.0 % (A1), 0.5 % (A0), 2.0 % (V0) | averaged over the whole calendar period including the flat time after the halt | report exposure **while active** (A1 ~6.2 %, A0 ~72 %, V0 ~23 %) and over the whole period, side by side |
| Time in market 15.6 % / 0.6 % / 8.7 % vs "share of period traded" 48.6 % / 0.65 % / 8.7 % | different denominators (hours with a position vs time until halt) | define: *active window* = start to halt-liquidation; time in market = share of the ACTIVE window with a position (A1 ~32 %, A0 ~100 %, V0 ~100 %) |
| Sharpe, Sortino, DSR, minimum detectable Sharpe computed on 1642 days | 84 % / 99 % / 91 % of the days have zero return after the halt, so the sample size is overstated and the ratios are diluted; A0 has ~11 active days | all statistics on **active days**; effective n and detectable Sharpe reported from active days (A1 ~798 d: detectable ~1.7; A0 ~11 d: ~15; V0 ~142 d: ~4.0) |
| Active-window Sharpe (A1 0.77, A0 5.4, V0 2.3) | looks better but is based on 11-798 days and a halt chosen by the path | never used as evidence; shown only next to the same-window benchmark (B1 over the same windows: Sharpe 1.12 / 10.9 / 4.6) |
| `entries_blocked = 0` | structurally always 0: the strategy stops emitting orders when halted, so the engine never sees a blocked entry | count **suppressed signals** (what the strategy would have done) via a shadow signal log |
| Halt drawdown 20.0 % / 22.0 % / 20.4 % | breaker checks the previous close; one large candle at 82 % exposure overshoots | report overshoot explicitly (threshold - observed) |
| T7 windows 0.0 % after the halt | halted windows count as "not positive", so T7 penalises the breaker, not the signal | keep T7 unchanged for the verdict, add a descriptive "active windows only" line |
| T8 "all ok", T5 PF = infinity | regimes with < 30 episodes are skipped, PF with no losing episode is infinite: vacuous passes | state "vacuous" next to such passes; they never count as evidence |
| Benchmarks without breaker or liquidity cap | not like-for-like | keep definitions; add risk-matched comparators (section 6) |

## 2. Assumptions challenged
- "A profitable strategy exists in this data": not assumed. A valid final outcome of the programme is "no credible edge found".
- "T3 and T4 together are neutral gates": T3 asks for a Sortino at least that of the best passive benchmark (a survivor-biased basket in a
  bull cycle, 1.81) and T4 asks for a drawdown at most 20 % where the same basket had 90 %. Sharpe-like ratios are exposure-invariant, so
  low exposure alone cannot satisfy T3; it takes timing skill that beats a hindsight-flattered benchmark. Prior probability of passing
  both is low. Criteria stay unchanged (owner decision), but the research budget must be sized accordingly.
- "Breaker-OFF is a deployable fallback": it is not. Breaker-OFF is a diagnostic instrument only.
- "More strategy families will eventually find something": with 43 trials already spent on one dataset the multiple-testing penalty
  grows faster than the plausible discovery rate (section 8).
- "Fewer trades are fine if profit factor is high": 7-14 episodes carry no statistical information.

## 3. Architecture: four separable layers
| Layer | Responsibility | Output | Evidence it is judged on |
|---|---|---|---|
| L1 Signal | desired direction/strength per asset from completed candles only | target score s in [0,1] per asset per day | gross, cost-free, **unit-exposure** return series of the signal alone, information coefficient vs next-period returns, hit rate; compared with a random-timing null |
| L2 Portfolio construction | turns scores into weights (volatility scaling, caps, no leverage) | target weights | risk-adjusted return of weights vs an exposure-matched and a volatility-matched buy-and-hold |
| L3 Execution | fills, fees, slippage, liquidity budget, minimum notional | fills, costs | cost drag, turnover, rejected/partial orders, slippage sensitivity at 2x; reconciliation with native Freqtrade |
| L4 Risk management | tiered state machine (section 4) | exposure multiplier, flatten orders, state log | drawdown control, forgone return, time spent in each state, re-entry lag, false-trigger rate |

Rules: L1 never sees equity or state; L2 sees only L1 output and volatility; L4 acts only through an exposure multiplier and explicit
liquidation orders; each layer has its own unit tests and its own metric table. T1-T10 are applied to the full stack (the deployable
object); layer metrics are diagnostics and never replace T1-T10.

## 4. Risk management V2
### 4.1 Alternatives
| Option | Idea | Pros | Cons / failure mode |
|---|---|---|---|
| A. Current terminal latch | halt, flatten, wait for owner | simplest, safest for a live account | confounds evaluation (section 1); unusable as the only mechanism in research |
| B. Cooldown + epoch reset | flatten, wait N days, reset the peak, resume at reduced size | deterministic, recovers | each epoch can lose another 20 %: whole-run drawdown can exceed 20 % and T4 (unchanged, measured on the all-time peak) would still fail; reset hides loss |
| C. Headroom sizing (CPPI-like) | exposure proportional to the remaining cushion above a floor tied to the all-time peak | never breaches the floor except by gaps; no discrete halt | cushion at the floor means zero exposure: an absorbing state again; slow recovery |
| D. Tiered state machine (recommended) | temporary reduction (tier 1), defensive flatten with cooldown and staged re-entry (tier 2), emergency shutdown needing manual authorisation (tier 3); drawdown measured against the all-time peak | separates temporary risk reduction from permanent shutdown; deterministic; reportable; stays consistent with T4 | more parameters (all fixed a priori, none tuned); tier 3 is still terminal in a backtest, but now rare and labelled as a risk-system failure |

### 4.2 Proposed tiered design (all values a priori from a risk budget; no value derived from Family A results)
- **Reference**: all-time peak of mark-to-market equity (never reset except by owner approval).
- **Tier 0 normal.**
- **Tier 1 temporary reduction**: drawdown from the all-time peak >= 10 %: exposure multiplier 0.5. Auto-reverts when drawdown < 5 % (hysteresis) - time-independent, deterministic.
- **Tier 2 defensive flatten**: drawdown >= 15 % (set below the 20 % T4 limit so that normal gap overshoot stays inside it): flatten at the next open
  through the liquidity budget, no new entries, **cooldown 14 calendar days** (about two weeks of volatility clustering), then **staged re-entry** at
  multipliers 0.25, 0.5, 1.0 with 7 days between steps, each step conditional on no new tier-1 or tier-2 trigger; any trigger returns to tier 2 with a new cooldown. The peak is NOT reset.
- **Tier 3 emergency shutdown (permanent, manual authorisation)**: drawdown >= 18 % from the all-time peak, or any integrity breach (missing data above
  a threshold, price anomaly above x sigma, order/fill reconciliation error, exchange rejection storm). Flatten, block everything, write the
  state file; only a file naming the shutdown id and an approver restarts, and a restart opens a new, separately reported epoch.
- **Position behaviour**: tiers 2 and 3 flatten; tier 1 scales target exposure down by selling the excess at the next open (never adds).
- **Honest consequence**: because the peak is not reset and T4 stays at 20 %, a run that needs the owner's restart has failed T4 on the
  whole-run equity. That is intended: recovery mechanisms may protect against a permanent lock-in but must not hide a breach.
- Parameter budget: five numbers (10/5/15/18 % and 14 d, steps 7 d). They are justified as risk-budget conventions (T4 limit minus overshoot margin)
  and are frozen before any run; they are never tuned on market results.

### 4.3 Reporting rules (applied to every future run)
Active window, time in each tier, number and timing of tier changes, suppressed signals, overshoot, liquidation fills, forgone return
during tier 2/cooldown, re-entry lag, and whole-run T1-T10 on actual equity. A terminal tier 3 is reported as "risk system shutdown at
date X" and the evaluation of the remaining period is declared **not evaluated**, never as zero return.

## 5. Diagnostic protocol isolating the breaker (not a deployable strategy)
- **Shadow replay**: the identical signal/portfolio/execution run twice in one job, risk layer ON (the deployable object, verdict basis) and
  OFF (a *diagnostic instrument*, always labelled "not a strategy, not for deployment, excluded from T1-T10, DSR and promotion").
- **Attribution identity**: equity(ON) - equity(OFF) = avoided losses - forgone gains, reported per tier event; plus max-drawdown reduction,
  return given up, false-trigger rate (trigger followed by recovery above the trigger level within 60 days), re-entry lag, number of
  halts per year.
- **Synthetic validation first** (no market data): scripted crash/V-shape/slow-bleed/gap scenarios prove each tier's behaviour,
  idempotence and absence of lock-in before any market use.
- **Counting**: an OFF diagnostic is a *diagnostic trial* recorded in the ledger (class "diagnostic"); it does not enter N for DSR unless it is
  ever considered as a candidate (it never is).
- **Approval**: each diagnostic run is requested separately; none is authorised by this proposal.

## 6. Comparable risk-adjusted benchmarks (added as comparison lines; T3 definition unchanged)
1. B1-B5 exactly as frozen (no breaker, no cap) - kept, with the disclosure.
2. **Exposure-matched buy-and-hold**: B1 at the strategy's time-varying exposure path, rest in cash (shows what plain beta scaling gives).
3. **Volatility-matched buy-and-hold**: B1 scaled to the strategy's realised volatility.
4. **Cash-mix at the T4 limit**: static mix of B1 and cash whose historical drawdown is 20 % (an honest "no-skill" reference for T4).
5. **Random-timing null**: permutation of the strategy's own exposure schedule over time (thousands of draws, fixed seed) to test whether timing adds value beyond exposure level.
6. **Signal-only L1 benchmark**: the L1 gross series versus random signals of equal turnover.
All are computed on the same universe and costs, so survivorship affects strategy and comparator alike (it does not vanish in absolute terms).

## 7. Trade counts, survivorship, power and repeated testing
- **Pre-run feasibility gate (new, mandatory)**: before any market run, show arithmetically (assets x expected entries per asset-year x years) and on synthetic
  data that T1 (>= 200 closed episodes) is reachable; compute the minimum detectable Sharpe from the expected *active* days; if T1 is unreachable or
  detectable Sharpe > 1.5, the specification is **not run** (saves a trial). Family A would have failed this gate (about 14 episodes).
- **Statistics on active days**; effective n reported; DSR/PBO use N from the ledger (43) plus new configurations.
- **Survivorship**: (i) data-source audit (availability only, no strategy) for point-in-time listings of delisted pairs from free public sources; (ii) if none, every result is
  labelled survivor-biased and conclusions are restricted to relative statements against same-universe comparators; (iii) no claim of absolute profitability on survivors.
- **Repeated testing**: ledger is binding; a Holm family over all hypotheses ever registered on this dataset is computed at report time; the dataset is declared
  **exhausted for confirmatory purposes** (research data), so any new positive result only earns a forward test, never a claim.
- **Out-of-sample**: only (a) the single-use holdout (unchanged) and (b) forward paper trading with a frozen specification, no parameter edits, minimum 6 months or 200 episodes,
  whichever is later, are accepted as OOS evidence.

## 8. Research budget (hard caps to prevent endless searching)
- At most **3 further strategy families** and **3 configurations per family** (primary + 2 descriptive components) = 9 new trials; total N never above 52 on this dataset.
- At most **one market run per family** plus one approved diagnostic replay per family; no reruns, no "fix and rerun" after seeing results (infrastructure bugs found before the run are fixed before it, as with amendment A1).
- **Stop rules**: two consecutive families rejected under protocol V2 -> stop strategy search and report "no credible edge under these constraints"; owner then decides between
  more data (forward paper trading of the best-justified spec), widening scope, or ending the research line.
- Every family requires a one-page pre-registration (rationale, parameters, feasibility gate result, hypotheses) frozen in a manifest before implementation.
- Budget in money and effort stays EUR 0, no paid data, no credentials.

## 9. Is Family B scientifically justified under this protocol?
Cross-sectional momentum needs a broad cross-section (>= 30 liquid assets) and a point-in-time universe including delisted assets. The frozen data hold 8 survivors;
ranking 8 survivors is not a cross-sectional test and carries maximal survivorship bias. Costs are the highest of all families (turnover). **Conclusion: not
justified on current data.** It becomes justified only if the data-source audit (stage S1 below) finds a free point-in-time universe of >= 30 pairs with a history long enough
for >= 200 expected episodes, and the feasibility gate passes. Otherwise Family B is dropped. Higher-timeframe trend/vol targeting variants are not automatically
justified either: Family A showed the feasibility gate and the evaluation design matter more than the signal.

## 10. Implementation stages and approval gates
| Stage | Content | Acceptance criteria | Gate |
|---|---|---|---|
| S0 (this document) | proposal | owner reads and decides | **G0: approve/modify/reject the proposal** |
| S1 | data-source audit: free point-in-time listings, volume history, gaps (availability only) | written audit; decision on Family B and on survivorship labelling | G1 |
| S2 | risk layer V2 on the engine with synthetic scenario tests; layered metric reporting; active-day statistics; reconciliation fixes (section 1.2); shadow-signal log | all scenario tests pass (no lock-in, deterministic, causality mutation/restart, liquidity), reconciliation with native Freqtrade unchanged, full regression green, manifest v6 with amendment history | **G2: approve implementation result** |
| S3 | feasibility gate tool (arithmetic + synthetic) and pre-registration template | gate rejects Family A as specified, accepts a synthetic example | G3 |
| S4 | benchmark add-ons (exposure/volatility-matched, cash-mix, random-timing null) validated on synthetic data | closed-form checks, determinism | G4 |
| S5 | first new family evaluation (only if its pre-registration passes the gate) | one run, full report, T1-T10 unchanged | **G5: separate approval per run** |
| S6 | diagnostic breaker replay | only on request, labelled diagnostic | G6 per run |
| S7 | holdout / paper trading | unchanged rules, owner written approval each | G7 |
No stage starts without its gate; no market experiment occurs before G5.

## 11. Acceptance criteria for protocol V2 itself
1. A scripted scenario suite shows: no permanent lock-in after tier 1/2, tier 3 only on the listed conditions, staged re-entry timing exact, deterministic hash across processes.
2. The layered report reproduces every Family A number in section 1.2 from the stored result (consistency test) and states active vs calendar quantities.
3. Whole-run T1-T10 on actual equity is computed exactly as before (unit-tested against the frozen implementation).
4. Ledger, budget counters and stop rules are enforced by a check in `check.sh` (a run cannot start if the budget is exhausted).
5. Documentation of what V2 cannot do: it does not create alpha, does not remove survivorship, and does not make T3/T4 easier.

## 12. CI status (HEAD 3ade8da, verified 2026-11-25)
Quant CI (push and PR): success. zizmor: success. Upstream Freqtrade CI: 17 jobs succeeded (all Linux, ARM and Windows test jobs, pre-commit, mypy, docs), 6 macOS test
jobs cancelled because GitHub never assigned them a runner, aggregate "Build (3.13)" therefore fails. **Unresolved infrastructure issue**: macOS runner availability (external, no code defect);
one earlier Windows timing flake (`test_cleanup_timeout`) did not recur on HEAD. No unresolved failure belongs to our code.

## 13. Decisions requested
1. Approve (or change) the four-layer separation and the tiered breaker design, in particular the a-priori numbers 10/5/15/18 % and 14 d / 7 d.
2. Confirm that tier 3 and any owner restart count as a T4 failure on whole-run equity.
3. Approve the pre-run feasibility gate, the research budget (<= 3 families, <= 9 trials) and the stop rule.
4. Approve stage S1 (data-source audit) as the only next step, to decide Family B and survivorship handling.
