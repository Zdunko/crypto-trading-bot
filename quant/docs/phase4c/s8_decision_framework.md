# S8 — Decision framework and recommendation

## Pre-registered rule (s8_criteria.json, fixed before the study)
A path is a research path only if ALL hold: (1) a dependence-aware paired test with size ≤ 0.07 under every DGP; (2) power ≥ 0.80 at the declared plausible effect **IR 0.5** over the available legally usable history; (3) the data is legally usable for the intended purpose (unverified counts as unverified); (4) no frozen threshold is weakened. GO = a path meets (1)-(4) with data in hand or verified free and legal. CONDITIONAL GO = meets (1), (2), (4) but (3) is unresolved or history must first be extended. NO-GO = no path meets (1) and (2) even with the maximum conceivable free history.

## Paths (power = Newey-West test, synthetic, 4.5 years unless stated; "assumed" = an assumption, not evidence)
| Path | Power at IR 0.3 / 0.5 / 0.8 / 1.0 | Criterion (1) | Criterion (2) at IR 0.5 | Legal (3) | Effort | Expected research value |
|---|---|---|---|---|---|---|
| P0 time-series paired claim, current PIT data (2021-2025 usable, research-only) | 0.14-0.19 / 0.22-0.33 / 0.40-0.54 / 0.57-0.69 | met (NW, L10) | **not met** | research-only (verified restriction) | none | can only *fail to reject*; cannot establish an edge |
| P1 same claim, legally extended history (≈ 13 y of BTC/ETH, e.g. venue downloads) | at 13 y: 0.25-0.29 / 0.49-0.56 / 0.83-0.89 / 0.95-0.98 | met | **not met** (needs ≥ 25 y) | **unverified** (hosts unreadable) | medium: licence reading, data build, PIT identity for 1-2 assets | meets the rule only for IR ≥ 0.8; breadth ≈ 1-2 assets, one market regime history |
| P2 cross-sectional relative claim, active return vs equal weight, N = 40-100 (2021+) | IR assumed 0.76 / 1.22 for IC 0.01 → power 0.49 / 0.82; at IR 0.5 → ≈ 0.30 | met (size 0.03-0.07) | **not met** at IR 0.5; met only if the strategy truly delivers IR ≳ 1.2 | research-only | medium-high (a new family spec, not approved) | high only if the IC assumption holds; IC 0.01 is unverified and costs/turnover are ignored |
| P3 signal-existence test (cross-sectional IC, HAC t) before any tradability claim | IC 0.01: 0.19 (N5) / 0.48 (N20) / 0.75 (N40) / 0.98 (N100) | met (size 0.04-0.06 at IC 0) | not applicable (different claim: *a signal exists*, not that a long-only portfolio earns IR 0.5) | research-only | medium | most informative per unit of data; proves nothing about tradable or cost-adjusted returns; spot-only cannot capture the short side |
| P4 purged/embargoed walk-forward for model-based families | no power gain | n/a | n/a | n/a | low (spec + test) | prevents spurious +0.085 IC from shuffled CV; mandatory for ML, not a power source |
| P5 independent market/regime validation | unknown; gain only if returns are independent (simulated correlation 0.55-0.68) | n/a | n/a | unverified | high | cannot be quantified; unlikely to add independent information |
| P6 forward paper trading as out-of-sample evidence | accrues ≈ 1 year per year; same arithmetic (≈ 25 y for IR 0.5) | n/a | not met in any realistic horizon | needs licence-cleared live feed | high | useful for operations and cost realism, not for proving an edge; **not approved** |

## Recommendation: **NO-GO under the pre-registered rule**
No path meets criterion (2) at the declared plausible effect IR 0.5, even with the maximum conceivable free history (≈ 13 years: power 0.49-0.56; about 25 years would be needed), and the only legally verified data (Binance Vision) is research-only. Nothing was weakened to reach a different answer.

What this does and does not mean:
- It is **not** evidence that profitable strategies do not exist. Failing to reject is uninformative here (D2). It says a backtest on this data **cannot establish** an edge of the size an unremarkable systematic strategy would have.
- It means the stated objective (a statistically defensible validation of an automated strategy from historical data alone) is not attainable by adding more infrastructure or more assets.
- Two narrow paths remain **possible but are not recommended without an owner decision**, because they change the claim being tested rather than rescuing the old one: **P3** (validate that a cross-sectional signal exists, at power 0.75-0.98 for IC 0.01 with N ≥ 40) combined with an explicit statement that tradable performance and costs are unproven; and **P2/P1** only for strategies whose economic rationale implies IR ≳ 0.8-1.2 (which must itself be justified a priori, not from backtests). Either needs a new pre-registered claim type, new criteria, licence-cleared data for any commercial use, and approval of any family; none of this is granted by S8.

## Concrete next steps (no implementation without approval)
1. Owner decides whether the objective is (a) prove a tradable edge from history (NO-GO), (b) establish a signal-existence + risk-bounded operating path (new claim type, needs a pre-registered "evidence ladder"), or (c) stop research and treat the system as infrastructure only.
2. Read the primary licence texts (allow the venue hosts or paste them) before any data decision; nothing is verified except Binance Vision's research-only restriction.
3. If (b): a pre-registered S9 design with the IC-test criteria, Holm across all tested signals, purged validation, V3 integration tests G1/G3/G5, still with zero strategy registration until approved.
4. Adopt nothing from the v2 proposal yet; if (b), adopt HAC as the default paired test and restrict V2-1 to episode counts.
