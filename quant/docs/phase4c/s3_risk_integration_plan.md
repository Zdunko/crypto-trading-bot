# S3-4: Synthetic integration validation plan, RiskManagedStrategy x Freqtrade (DESIGN ONLY - not executed)

Status: design. Nothing here was run. No market data, no market replay, no backtest of any strategy. Execution needs a separate owner approval.
Scope guard: every scenario uses **generated synthetic candles or mocked exchange responses**; the holdout and all Binance/OKX market data are out of scope. `dry_run=true`, spot only, no credentials, `position_adjustment_enable=false` throughout.

## 1. What exists and what is unproven
`quantlab.risk_v2.RiskManagedStrategy` is an order-level wrapper for the **project's own Stage-0 engine** (`quantlab.execution`): it returns `Order` lists per candle and reads a `PortfolioView`. Freqtrade has a different execution model (callbacks, order objects with partial fills/cancel/timeouts, a SQLite trades DB, wallets, exchange I/O). Everything below validates the *adapter* and the *behaviour of the state machine under Freqtrade's semantics*; the state machine itself is already frozen (S2, manifest v6) and must not change.

Known semantic gaps to be closed by the adapter and tested:
| Gap | Engine (S2) | Freqtrade | Risk |
|---|---|---|---|
| Time | candle-open fills, one decision per completed candle | `bot_loop_start` every ~5 s, `process_throttle_secs`; candle is "new" only after refresh | duplicate or missed `step()` per candle; clock regression |
| Equity | `view.equity` marked on closes | `Wallets.get_total()` / open-trade valuation by ticker/orderbook | equity input differs; must be defined once and logged |
| Orders | order fills fully or per liquidity budget | partial fills, cancels, timeouts, exchange reject | residual exposure and queued-liquidation state in the risk budget (`X_open`) |
| Liquidation | `priority=-1` sell orders, never expire | `force_exit`/`custom_exit`, exit order timeouts, `exit_timeout_count`, unfilled limit orders | stuck liquidation must keep state FLAT/SHUTDOWN and alarm |
| Persistence | atomic single hash-chained file | bot DB (`tradesv3*.sqlite`) is independent of the risk file | divergence between risk state and DB after crash/restore |
| Restart | `RiskStateMachine.resume` | `freqtrade trade` reloads open trades from DB | restart in SHUTDOWN must not allow an entry before authorisation |

## 2. Adapter contract (to be designed in code later, not now)
1. Single thin class in `quant/strategies/` (must pass `quantlab.strategy_policy`) delegating to `RiskStateMachine`; no risk logic duplicated.
2. One `step()` per completed candle, keyed by the candle's close time; idempotent for a repeated timestamp (returns the stored decision, never a second transition); a timestamp earlier than the last processed one is an integrity event (SHUTDOWN, `state_integrity`).
3. Hooks: `bot_loop_start` (step, authorisation poll), `confirm_trade_entry` (veto unless state allows and the cap/budget permits), `custom_stake_amount` (cap and risk-budget scaling), `custom_exit` / forced exit on liquidation, `order_filled` (update gross exposure and outstanding-liquidation set), `confirm_trade_exit` (never veto a risk liquidation).
4. Equity definition frozen in the adapter and logged each step: wallet free + open trades marked at the last completed close (same convention as the engine); the exchange-reported balance is compared against it (reconciliation, section 4).
5. Fail-closed: any exception inside the adapter in a state other than SHUTDOWN ends in SHUTDOWN with a safety flag; entries are vetoed while the adapter is uninitialised.

## 3. Test layers
| Layer | Mechanism | Purpose | Cost |
|---|---|---|---|
| A. Adapter unit | pure Python, fake `Trade`/`Wallets`/`Order` objects | hook logic, idempotence, vetoes, mapping | seconds, normal CI |
| B. Freqtrade backtesting on **synthetic OHLCV** | generated feather/json in a temp `user_data`, deterministic generators with seeds | multi-candle scenarios of the machine under Freqtrade's candle/order model (gap-through, drawdown ladders, re-entry loops) | minutes, marker-triggered CI only if heavy |
| C. `FreqtradeBot` dry-run with a mocked exchange | Freqtrade's patched-bot pattern (as used by upstream tests; no upstream file is modified) with scripted order books, fills, rejects, timeouts | order-level behaviour: partial fills, unfilled liquidation, rejects, restart from DB | seconds-minutes |
| D. Crash injection | subprocess + `SIGKILL` at named points, plus truncated/corrupted/replaced state files | restart and persistence | seconds |
Layer B never reads a market file; layers C/D use no network. Layer B results are checked against the pure-engine result for the same synthetic path (differential test) wherever the semantics are meant to be identical.

## 4. Scenario matrix and pass criteria (written before running)
Each scenario has a seed, an expected state trace (from the S2 engine on the same path) and a hard assertion. A scenario fails if any assertion fails; there is no tolerance tuning.

| ID | Scenario | Layer | Pass criterion |
|---|---|---|---|
| I1 | Clean path, no triggers | B | identical equity/state trace to engine within 1e-9 relative; zero vetoes |
| I2 | Tier 1 -> Tier 2 ladder, cooldown, 3-step re-entry | B | transition table identical to engine; caps respected on every entry |
| I3 | Tier 3 / floor breach -> SHUTDOWN | B/C | all positions queued for liquidation; no entry for the rest of the run; SAFETY flag set |
| I4 | Gap-through (candle opens beyond floor) | B | overshoot reported, not hidden; state SHUTDOWN in the same candle; no second transition |
| I5 | Liquidity failure: liquidation order not filled for N candles (scripted order book) | C | after `liquidity_alarm_candles` -> SHUTDOWN `liquidation_unavailable`; open exposure reported as unliquidated and counted in `X_open` |
| I6 | Partial fill of liquidation | C | residual exposure re-queued, never dropped; budget uses residual |
| I7 | Partial fill of entry | C | gross exposure uses filled amount; cap never exceeded by the sum of fills and open orders |
| I8 | Exchange reject/timeout on entry and exit | C | entry reject = no state change; exit reject keeps liquidation pending and retried; no double sell |
| I9 | Duplicate candle / replay of the same timestamp | A/C | no second transition (idempotent); logged |
| I10 | Clock regression / candle from the past | A | SHUTDOWN `state_integrity` |
| I11 | Restart in each state (NORMAL, REDUCED, FLAT, REENTRY at each step, SHUTDOWN) | D | resumed state, HWM, epoch floor, counters, `SAFETY_DISQUALIFIED` identical to pre-kill; first post-restart decision equals uninterrupted run |
| I12 | Kill at each write point: before temp write, after temp write, after fsync, after `os.replace`, mid-candle before step, after step before orders | D | file is either the old or the new complete state, never partial; resume never skips or repeats a transition; orphan temp file ignored/cleaned |
| I13 | State file missing/corrupted/truncated/hash-chain edited/replaced by older valid file | D | SHUTDOWN `state_integrity`, entries vetoed, not authorisable |
| I14 | Restored older bot DB with newer risk file and vice versa | C/D | reconciliation mismatch detected -> SHUTDOWN (no auto-heal) |
| I15 | Reconciliation: engine gross exposure vs wallet/DB-derived exposure after every candle | C | mismatch above `flat_tolerance`-based bound for 2 consecutive candles -> alarm -> SHUTDOWN; single-candle mismatch logged only |
| I16 | Manual authorisation: valid, stale, duplicate `approval_id`, future-dated, wrong approver, cap too high, positions not flat, file edited after signing | A/D | exactly the S2 outcomes; duplicate never accepted twice, also after restart |
| I17 | Simultaneous triggers (integrity + floor + tier 2 + liquidity in one candle) | A/B | precedence integrity > floor > liquidity > tiers; one transition |
| I18 | Repeated failed re-entries across restarts | D | counter persists; escalation to SHUTDOWN at 2; no reset by restart |
| I19 | SHUTDOWN persistence across 100 restarts and a config reload | D | stays SHUTDOWN; no entry; `SAFETY_DISQUALIFIED` never cleared |
| I20 | Property test: random synthetic paths x random kill points | B/D | invariants of S2 (HWM monotone, no transition after SHUTDOWN without valid authorisation, caps, one transition per candle, replay determinism) |
| I21 | Policy check | A | `strategy_policy` passes; `dry_run` true; no futures/margin/position adjustment; no credential fields |

## 5. Environment, resources, ordering
- No network is available to exchange hosts from this environment (all but the Binance S3 endpoint and GitHub are unreachable), which is compatible with the plan: A/D need none, B/C use generated data and mocks.
- Freqtrade version and Python pinned by `uv.lock`; synthetic data generators live in `quant/quantlab/synthetic.py` (new, seeded); no file in `freqtrade/`, `tests/` or other upstream paths is touched.
- Order: A -> D (cheap, highest risk coverage) -> C -> B (differential). CI: A/C/D in normal Quant CI; B only if runtime exceeds a few minutes, then on a marker.
- Estimated effort: adapter + A tests small; C requires a careful mocked-exchange harness (the main engineering risk); B needs the synthetic generator.

## 6. Exit criteria for the integration stage
All I1-I21 pass with no skipped scenario; differential traces identical; zero unexplained divergence; `check.sh` and CI green; the S2 frozen files unchanged (freeze test). Any failing scenario is a defect to fix in the adapter, never a reason to relax a criterion or change risk parameters.

## 7. Risks of the plan itself
1. Mocked-exchange semantics can differ from a real exchange (partial-fill and rejection behaviour, rate limits); only a later, separately approved dry-run observation can cover this, and it is out of scope here.
2. Freqtrade backtesting does not model restarts, order timeouts or partial fills; hence layers C and D.
3. Reconciliation thresholds (I15) are new design parameters; they are set from arithmetic (tolerance of the S2 `flat_tolerance`), not from data, and are frozen before the run.
