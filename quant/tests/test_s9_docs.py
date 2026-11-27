"""S9 deliverables exist and say what the pre-registered criteria require."""

from __future__ import annotations

import json
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
D = Q / "docs/phase4c"
C = json.loads((D / "s9_criteria.json").read_text(encoding="utf-8"))


def read(n: str) -> str:
    return (D / n).read_text(encoding="utf-8")


def test_three_hypotheses_have_every_required_field_and_none_reuses_rejected_keys():
    t = read("s9_signal_hypotheses.md")
    for h in ("## H1", "## H2", "## H3"):
        assert h in t
    for label in (
        "Rationale",
        "Signal",
        "PIT data",
        "Horizon",
        "Turnover",
        "Cost sensitivity",
        "Regime dependence",
        "Lookahead/survivorship",
        "Rejection criteria",
        "Estimated power",
    ):
        assert (
            t.count(f"**{label}") >= 3
            or t.count(f"**{label}.") >= 3
            or t.count(f"**{label}**") >= 3
        ), label
    assert (
        "Multiple testing" in t and "Holm" in t and "null: mean cross-sectional rank IC <= 0" in t
    )
    for key in C["hypotheses"]["forbidden_reuse"]:
        if "_" in key:
            assert key not in t, key  # rejected-family identifiers are not reused as hypotheses
    assert "None is momentum" in t
    assert "Recommended candidate: H1, exactly one" in t.replace("**", "")


def test_v3_plan_uses_zero_recovery_and_never_treats_it_as_liquidity():
    t = read("s9_v3_minimum_integration_plan.md")
    assert "Zero recovery is the primary assumption" in t.replace("**", "")
    assert "never executable liquidity" in t and "G1" in t and "G3" in t and "G5" in t
    assert "no code in s9" in t.lower()


def test_licensing_list_assumes_nothing_and_lists_owner_actions():
    t = read("s9_licensing_request_list.md")
    assert "No commercial usage right is assumed" in t and "not retried" in t
    assert "Paste the text" in t.replace("**", "") and "Authorise the exact hosts" in t.replace(
        "**", ""
    )
    assert "quant/docs/legal/" in t


def test_roadmap_has_milestones_gates_effort_and_termination():
    t = read("s9_roadmap.md")
    for m in ("M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"):
        assert f"| {m} " in t
    assert (
        "Termination condition" in t
        and "Global termination" in t
        and "dry_run" in t
        and "1 of 3" in t
    )


def test_ladder_doc_keeps_t1_t10_and_budget_untouched():
    t = read("s9_evidence_ladder.md")
    assert "does not modify T1-T10" in t and "N = 43/52" in t and "No exploratory experiments" in t
