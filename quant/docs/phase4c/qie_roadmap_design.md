# Quant Intelligence Engine (QIE) — design-only roadmap P1–P5

**Design only. Nothing here is authorised, scheduled or promised.** No P1 or later work starts without an explicit, separate owner approval; each phase ends in a report and a stop. No claim of alpha is made: the repository's own evidence (S8: minimum detectable IR 1.17 on 4.5 years; every tested idea rejected, terminated or falsified) says that profitability cannot currently be demonstrated, and QIE is framed as an **evidence-first research and risk-analytics system**. Trading permissions and research criteria are unchanged (dry-run only, spot only, no credentials, no real orders, holdout untouched, T1–T10 and V3 unchanged, N 45/52, families 1/3; any budget change is an owner decision, not part of this roadmap).

## Permission tiers (separate approvals; never inferred)
| Tier | Meaning | Status |
|---|---|---|
| Research-only | analysis on data whose licence permits non-commercial research | **current** (Binance Vision CC BY-NC-SA 4.0; OKX public data for Phase 3) |
| Operational | running the system (dry-run/paper, internal use) | **not permitted** — data rights unresolved, no deployment approved |
| Commercial | selling signals, advice or managing third-party funds | **not permitted**; legal advice is outside what an AI agent can provide |

## Reuse map (from `qie_p0_reusable_inventory.md`)
Engine/costs (`execution`, `costs`, `causality`), PIT tooling (`pit_*`, `data_audit`), governance (`feasibility`, `protocol`, `budget`, `amend_chain`), risk V3, benchmarks, statistics, safety policy and `quant-ci` are reused as they are. No new framework, database or dashboard is proposed.

## P1 — Lawful fresh data and feasibility (before any hypothesis registration)
- **Deliverables:** (a) data-rights memo per candidate source: what the published terms say for each tier (owner/lawyer to confirm; no assumption of rights); (b) provenance specification: retrieval log, hash, licence text version and permitted-use label stored with every file; (c) feasibility note: what *independent* evidence each source can add (new untouched time span, new asset classes, forward collection) and the resulting power under the existing gate (`feasibility.py`); (d) a plan for **forward data accumulation** under permitted terms (evidence then grows at calendar speed).
- **Dependencies:** owner decisions on licensing inquiry (draft exists, never sent) and on any paid service (none authorised).
- **Acceptance:** at least one source whose written terms permit the intended tier **and** whose independent evidence span makes a pre-declared effect size reachable at 80 % power; otherwise P1 reports "infeasible".
- **Stop rules:** no lawful source → stop (archive option); no downloads of market data before the memo is approved; no holdout access.

## P2 — Descriptive market-regime and risk analytics (not presumed predictive)
- **Deliverables:** causal, point-in-time descriptors (volatility, correlation, breadth, liquidity, delisting/stale incidence, drawdown statistics) with reproducibility hashes and prefix-invariance tests; risk-event rates that inform V3 handling (e.g. the 83 failed assets of 411).
- **Dependencies:** P1 lawful data (or the existing research-only dataset for research-only analysis).
- **Acceptance:** descriptors reproduce bit-for-bit within a platform; causality tests pass; every output labelled descriptive.
- **Stop rules:** a descriptor may not be used as a signal without a P3 registration; no performance claims.

## P3 — Hypothesis research and independent validation
- **Process:** overlap audit against all prior families first (matrix as in M6-S0); power gate first; pre-registration before data; inference calibration rule pre-registered **with an exact binomial criterion** (lesson of M5); independent evidence = an untouched span (forward data, or the sealed holdout **only** by separate explicit approval, single use).
- **Budget:** remaining N 7 configurations / 2 families under the existing caps; a new family would count; stop after two consecutive rejections under protocol V2 (already encoded).
- **Acceptance:** pre-registered criteria met on independent evidence, with costs ×1 and ×2.
- **Stop rules:** non-rejection ≠ proof; no variant search; any falsified guarantee is withdrawn, not tuned.

## P4 — Portfolio intelligence
- **Deliverables (specification and synthetic evidence only):** risk-state handling that avoids the M6-S0 failure modes (integrity shutdown on a single delisting, drift between resizes, minimum-notional hysteresis, cumulative loss with replenishment); allocation rules stated as risk engineering, not alpha.
- **Dependencies:** P2 findings; a P3 result if a return claim is made; V3 changes need owner approval and a new frozen version.
- **Acceptance:** synthetic fixtures with frozen predictions and falsification rules (as M6-S0); overlap audit shows a distinct contribution.
- **Stop rules:** no registration if the contribution is only a risk overlay on evaluated components.

## P5 — Execution (locked)
- **Locked behind explicit approval.** Scope when unlocked: dry-run/paper only, monitoring and reconciliation, kill switch, ≥ 4 weeks uninterrupted dry-run with live-vs-model deviation report (as ROADMAP Phase 5). Live trading with real funds stays out of scope unless the owner changes the rules in writing.
- **Dependencies:** P1 operational-tier licence, a P3 validated signal or an explicit "no-alpha operational" decision, P4 specification, free host approved by the owner.
- **Stop rules:** any safety-policy failure, unexplained reconciliation gap or data-rights doubt stops the phase.

## Archive option (explicit)
If P1 reports "infeasible" (no lawful source with sufficient independent evidence), or the owner declines to fund the licensing step, the project is **archived**: freeze the repository state with a tag, keep all records and negative results, disable market-access workflows (`quant-research.yml`) and unused upstream workflows, keep `quant-ci` and the safety policy, and leave a README pointer to the closeout freeze record. Nothing is deleted.

## Proposed next decision (not an authorisation)
Choose one: (1) approve P1 only (documentation-only data-rights and feasibility work, no downloads); (2) archive now; (3) pause. No schedule or effort estimate is asserted.
