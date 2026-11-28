# S5 scope confirmation (written before any S5 work)

## 1. What "S5" meant in the approved plan
`risk_and_evaluation_protocol_v2_proposal.md` section 10 defines **S5 = "first new family evaluation (only if its pre-registration passes the gate); one run, full report, T1-T10 unchanged; G5: separate approval per run"**.
The stage names were reused during execution: the plan's S3 (feasibility-gate tool + pre-registration template) and S4 (benchmark add-ons) were **not** the stages executed under those numbers (the executed S3 was the data feasibility audit, the executed S4 the point-in-time dataset builder). Status of the original plan items:
| Original item | Status |
|---|---|
| S1 data-source audit | done (executed S1) |
| S2 risk layer V2 + reporting fixes | done (executed S2) |
| S3 feasibility-gate tool and pre-registration template | **not done** |
| S4 benchmark add-ons (exposure/volatility-matched, cash-mix, random-timing null) | **not done** |
| budget/ledger/stop-rule enforcement in `check.sh` (protocol V2 acceptance criterion 4) | **not done** |
| S5 first new family evaluation | requires a market run on a new family |

## 2. Does the original S5 require a prohibited activity?
**Yes.** A "first new family evaluation" is a market backtest / strategy evaluation of a new family (the only candidate on the table is Family B, which is not approved). The owner's current restrictions forbid market backtests, Family B implementation and strategy evaluations. **The original S5 is therefore NOT executed, and will not be, without a separate explicit approval.** It also needs, before it can start: the feasibility-gate tool, the benchmark add-ons and the budget enforcement above, plus a pre-registered family specification passing the gate.

## 3. What is authorised and done under the name "S5" now
Authorised by the owner: S5 infrastructure, integration and synthetic validation inside the approved protocol, plus seven preparatory items. Scope of this stage ("S5-infra"):
1. Freeze the S4 dataset (record + test), without changing any S4 criterion.
2. Limitations register (including macOS cancellations as an unresolved infrastructure limitation, not passed tests).
3. Investigation of the 4.8 % daily/hourly volume discrepancy and its impact on eligibility and execution (development data, descriptive, no returns).
4. Review of identity-epoch handling (crash versus migration/redenomination), descriptive; S4 stays frozen; any alternative is only a proposal for a separately pre-registered revision.
5. Holdout-isolation statement limited to what the evidence supports.
6. Production-data licensing roadmap (documentation; no purchase, no assumed permission).
7. Infrastructure with synthetic validation only: a causal, fail-closed dataset loader; a universe guard that integrates the dataset with the Stage 0 engine and the risk wrapper; budget/stop-rule enforcement in `check.sh`.
**Not done in S5-infra (needs approval or belongs to later stages):** feasibility-gate tool and pre-registration template (original S3), benchmark add-ons (original S4), any family implementation, any market run.

## 4. Boundaries (unchanged)
No market backtests, no strategy optimisation, no Family B, no holdout access, no paper/live trading, no paid services, no merge/deployment; T1-T10, S2 risk parameters, frozen manifests, S3/S4 criteria and all historical results unchanged.
