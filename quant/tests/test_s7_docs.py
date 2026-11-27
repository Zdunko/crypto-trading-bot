"""S7 deliverables exist and say what the pre-registered criteria require (M1, C1-C4, P1, G4)."""

from __future__ import annotations

import json
from pathlib import Path

from amend_chain import accepted_approvals, accepted_budget_states, accepted_registry_ids


Q = Path(__file__).resolve().parents[1]
D = Q / "docs/phase4c"


def read(n: str) -> str:
    return (D / n).read_text(encoding="utf-8")


def test_audit_answers_all_seven_questions_with_verdicts():
    rows = [
        r
        for r in read("s7_gate_methodology_audit.md").splitlines()
        if r.startswith("| ") and r[2].isdigit()
    ]
    assert len(rows) == 7 and all("**" in r for r in rows)
    assert "unchanged" in read("s7_gate_methodology_audit.md")


def test_methodology_proposal_is_marked_not_adopted_and_has_adoption_criteria():
    p = json.loads(
        (D / "proposals/feasibility_methodology_v2_proposal.json").read_text(encoding="utf-8")
    )
    assert (
        "NOT ADOPTED" in p["status"]
        and len(p["adoption_criteria"]) >= 4
        and len(p["proposed_changes"]) >= 3
    )


def test_family_review_has_three_candidates_labels_evidence_and_recommends_no_go():
    t = read("s7_strategy_family_review.md")
    assert "C1" in t and "C2" in t and "C3" in t and "B2" in t
    assert "Measured" in t and "assumption" in t and "NO-GO" in t and "Not disguised" in t


def test_roadmap_covers_all_eight_stages_and_starts_nothing():
    t = read("s7_production_readiness_roadmap.md")
    for i in range(1, 9):
        assert f"## Stage {i}" in t
    assert "not authorised" in t and "never withdrawal" in t
    assert "s7_production_readiness_roadmap.md" in (Q.parent / "ROADMAP.md").read_text(
        encoding="utf-8"
    )


def test_no_family_registered_and_budget_unchanged():
    b = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))
    base = json.loads((Q / "protocol/s7_freeze_record.json").read_text(encoding="utf-8"))[
        "budget_state"
    ]
    assert b["state"] in accepted_budget_states(
        base
    )  # N=43, or the state declared by amendment A11
    appr = json.loads((Q / "protocol/run_approvals.json").read_text(encoding="utf-8"))["approvals"]
    assert appr in accepted_approvals([])
    reg = json.loads((Q / "protocol/spec_registry.json").read_text(encoding="utf-8"))["registered"]
    assert [r["family_id"] for r in reg] in accepted_registry_ids([])
