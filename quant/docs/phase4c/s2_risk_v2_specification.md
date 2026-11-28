# S2 - Risk layer V2: architecture, state-transition table, risk-budget mathematics

Status: implemented and validated on SYNTHETIC data only (no market backtest, no holdout, no Family B, no dataset builder, no parameter
optimisation). Code: `quantlab/risk_v2.py`, `quantlab/active_stats.py`. Specification and numbers: `protocol/protocol_v6_risk_v2.json`
(frozen by manifest v6). **All numbers are provisional engineering assumptions, not validated optima.** T1-T10 and the T4 definition are untouched.
Family A remains rejected.

## 1. Architecture (four layers, L4 is this module)
`inner strategy (L1/L2) -> RiskManagedStrategy (L4) -> engine (L3)`. L4 sees only previous-close equity, positions and candle availability. It acts only through
(a) an absolute gross-exposure cap per state and (b) explicit liquidation orders (priority first, reason `halt`, never expiring, subject to the shared liquidity budget).
The inner strategy is told the cap through `risk_multiplier`; the wrapper enforces it independently (scales buys, sells the excess pro rata) and logs every suppressed
order (shadow-signal log). `RiskStateMachine` is pure and deterministic (state, equity, gross exposure, integrity flag -> decision); persistence is a separate `StateStore`.
Existing engine breaker (v1) is kept unchanged for reproducibility of archived runs; new work uses V2 (`ExecConfig(breaker=False)`). `strategies_r1/` (rejected) is untouched.

## 2. Definitions
E = previous-close liquidation equity; **H = all-time high-water mark, never reset** (not by recovery, restart or authorisation);
P = epoch-local peak (P = H in epoch 0; P = E at an authorised restart); d_G = 1 - E/H; d_L = 1 - E/P.
Tiers 1 and 2 use d_L; floors and the hard limit use E against H; so after an authorised restart tiers do not fire on the old, deeper drawdown, while cumulative protection stays tied to H.

## 3. State-transition table (one transition per candle; precedence top to bottom)
| # | Condition (evaluated in this order) | From | To | Cause |
|---|---|---|---|---|
| 0 | none: SHUTDOWN absorbs everything except a valid authorisation | SHUTDOWN | SHUTDOWN | - |
| 1 | integrity alarm (non-finite or <= 0 equity, clock regression, held pair without candles for 48 h, persistence error) | any active | SHUTDOWN | `integrity` |
| 2 | E <= floor (epoch 0: H x (1 - 18 %); epoch k: max(E_auth x (1 - loss limit), H x (1 - 25 %))) | any active | SHUTDOWN | `tier3_floor` / `epoch_floor` |
| 3 | FLAT_COOLDOWN with positions still open for >= 24 candles | FLAT_COOLDOWN | SHUTDOWN | `liquidation_unavailable` |
| 4a | d_L >= 15 % | NORMAL, REDUCED | FLAT_COOLDOWN | `tier2` (more than 3 cycles: SHUTDOWN `flat_cycles`) |
| 4b | d_L >= 10 % | NORMAL | REDUCED | `tier1` |
| 4c | d_L < 5 % | REDUCED | NORMAL | `recovered` |
| 4d | cooldown (14 d) elapsed and portfolio flat | FLAT_COOLDOWN | REENTRY (step 0) | `cooldown_elapsed` |
| 4e | equity <= entry equity x (1 - 3 %) | REENTRY | FLAT_COOLDOWN (second consecutive failure: SHUTDOWN `reentry_loop`) | `reentry_failed` |
| 4f | step held 7 d, steps 0.25 -> 0.5 -> 1.0 | REENTRY | REENTRY | `step_k` |
| 4g | final step held 7 d and d_L < 15 % | REENTRY | NORMAL (or REDUCED if d_L >= 10 %) | `reentry_complete` |
| 5 | valid owner approval (section 5) | SHUTDOWN | REENTRY (epoch + 1) | `authorised_by:<name>` |
Thresholds are inclusive and evaluated on equity (E <= P x (1 - x)) so exact boundaries are not lost to float rounding. All simultaneous conditions are recorded in the transition record.
Caps: NORMAL 1.0; REDUCED 0.5; FLAT_COOLDOWN and SHUTDOWN 0; REENTRY min(step, approved cap, budget cap); the budget cap also applies in every authorised epoch.
Guards against loops: (i) tier-2 cannot re-fire inside REENTRY (failure is measured against the re-entry start equity, not against P); (ii) REENTRY stays at the final step while d_L is still >= 15 % instead of leaving and re-triggering; (iii) at most 3 flat cycles and 2 consecutive failed re-entries per epoch; (iv) cooldown never shortens.
Recovery from a flattened cash portfolio does not need the peak to be regained (impossible in cash): it depends on time, the step schedule and the risk budget.

## 4. Risk-budget mathematics
phi = stress_gap + exit_cost (loss per unit of exposure value when a stress gap of 30 % hits and the position is then liquidated at 0.15 %); entry_cost = 0.15 %.
Floor F as in the table; remaining budget R = max(0, E - F). X_open = gross value still held, **including positions queued for liquidation and residual exposure after a partial liquidation**.
Allowed total gross exposure: if phi * X_open <= R then X_open + (R - phi * X_open) / (phi + entry_cost), else R / phi (existing exposure above the budget must be sold down).
Identity (tested): phi * allowed + entry_cost * (allowed - X_open) <= R. Cap fraction = allowed / E, clipped to [0, 1].
Example: E = 1000, F = 820 (R = 180), X_open = 0 gives allowed = 180 / 0.303 = 594 (59.4 % of equity).
**This is a control rule, not a guarantee.** The 18 % floor is not a maximum loss: a gap larger than the stress assumption, a missing candle, or no liquidity breaches it. Tests show a 30 % single-candle gap taking a book to d_G = 30 %, a 40 % gap with a fully invested book, and a gap during an authorised re-entry that breaches both the epoch floor and the 25 % hard limit; the overshoot is stored in the transition record and in `safety_events`.

## 5. Manual authorisation, SAFETY_DISQUALIFIED, persistence (fail closed)
- Approval (file or dict): `shutdown_id`, `approver`, `exposure_cap` in (0, 1], `epoch_loss_limit` in (0, 5 %], `approval_id`, timezone-aware `issued_at`. Rejected if: id mismatch, empty approver or id, bad numbers (NaN included), naive time, issued before the shutdown or in the future, older than 168 h, approval id already consumed (replay), positions not flat, equity at or below H x (1 - 25 %), not in SHUTDOWN, `state_integrity` shutdown, malformed/unreadable file. A rejected approval changes nothing.
- On success: new epoch, REENTRY, floor replaced by the epoch floor, **H unchanged, SAFETY_DISQUALIFIED unchanged**.
- `SAFETY_DISQUALIFIED` is set on every entry into SHUTDOWN, appended to `safety_events`, never cleared by recovery, restart or authorisation, and is not an input to T4 (T4 is computed from equity exactly as before; a tier-3 event at 18 % is not reported as a 20 % breach).
- Persistence: one file written atomically (temp file, fsync, rename), hash-chained transition records plus latest state under a head hash; missing, truncated, corrupt or modified file on resume = SHUTDOWN (`state_integrity`), which cannot be authorised (a new run with an explicit HWM is required); `new()` refuses to overwrite an existing file. A stray temp file from an interrupted write is discarded and the previous complete file wins. **Limitation:** the hash chain is tamper evidence; someone who recomputes all hashes is only detected if the head hash is anchored outside the file (`expected_head`), which the tests demonstrate.

## 6. Reporting fixes (reconciliation of the Family A inconsistencies)
`active_stats()` separates the **trading window** (start to the last day with a position or trade) from **invested days**, reports exposure and time in market over both the calendar and the window, and power on the window and on invested days (effective n never above raw n). Reconciled against the stored Family A result: A1 window 798 days (invested 257), exposure 3.0 % calendar vs 6.2 % in the window, time in market 15.6 % vs 32 %; A0 11 days; V0 143 days; zero-return days 84 % / 99 % / 91 % of the calendar. Earlier text used "active" for the window; the invested-day count is the more conservative power base. `layered_report()` keeps L1-L4 tables separate; `signal_information()` gives a signal-only IC/hit-rate for L1.

## 7. Tests (synthetic only)
New in S2: 122 tests (466 in the local gate). Machine: every one of the 13 allowed transitions reached and nothing else; inclusive boundaries for tiers 1/2/3; cooldown and step timing to the hour; re-entry failures, loop budget, the rule that the floor precedes a second failure under default parameters; simultaneous triggers and fixed precedence with audit trail; invalid equity, clock regression, idempotent candle replay; liquidity alarm; gap-through (30 % single candle, gap during re-entry beyond the hard limit); budget formula by hand and by identity; authorisation (valid path, 12 rejection cases, stale, duplicate, malformed, wrong state, file round trip, repeated authorisations bounded by the hard limit); permanent SAFETY_DISQUALIFIED and T4 untouched; 40 seeded random paths with 7 invariants each (HWM equals the running maximum, at most one transition per candle, flag never clears, caps bounded, floor breach in epoch 0 always shuts down, FLAT never longer than the cooldown, deterministic replay); oscillating-market flat-cycle bound; cross-process replay hash. Store: round trip and resume equal to an uninterrupted run, 5 corruption modes, edit without and with a recomputed hash, rollback, interrupted write (rename failure), partial write, authorisation and consumed ids across restarts, flag persistence. Engine: tier-1/2 behaviour with costs and next-open liquidation, cap enforcement, HWM equals engine equity, 40 % gap, liquidity failure after flatten, authorisation through the wrapper, mutation causality for prices and volumes, restart equality (engine plus machine state), in-process and cross-process determinism. Active stats: reconciliation, hand cases, layer separation, IC.

## 8. Remaining limitations and unresolved risks
- All thresholds, the 30 % stress gap, cooldown and step lengths are provisional assumptions; nothing about their adequacy for real markets was tested (no market data used).
- Gaps, halts and missing liquidity can exceed any floor; the budget cap is a control rule conditional on the stress assumption.
- The hash chain does not prevent a determined local attacker; real protection needs file permissions and an external anchor.
- The wrapper calls the inner strategy while flat/shut down to log shadow signals; inner strategies with hidden memory would see calls they did not act on (Family A is stateless).
- The wrapper enforces absolute exposure caps but does not know about per-asset concentration or correlation (L2 job).
- Re-entry after a tier-2 flat in epoch 0 happens on a clock, not on a signal check; whether that is desirable is a design choice to be examined in a future approved study, not tested here.
- Liquidity budget uses completed-candle volume only (amendment A1); no order-book data.
- Causality helper robustness fix recorded as amendment A4 (empty fill lists).
