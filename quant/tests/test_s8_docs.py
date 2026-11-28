"""S8 deliverables exist and say what the pre-registered criteria require."""

from __future__ import annotations

from pathlib import Path


Q = Path(__file__).resolve().parents[1]
D = Q / "docs/phase4c"


def read(n: str) -> str:
    return (D / n).read_text(encoding="utf-8")


def test_decision_framework_follows_the_pre_registered_rule_and_covers_every_path():
    t = read("s8_decision_framework.md")
    assert "NO-GO under the pre-registered rule" in t and "not weakened" in t.replace(
        "Nothing was weakened", "not weakened"
    )
    for p in ("P0", "P1", "P2", "P3", "P4", "P5", "P6"):
        assert f"| {p} " in t
    assert "Effort" in t and "Expected research value" in t and "not approved" in t


def test_methodology_review_answers_every_requested_topic():
    t = read("s8_methodology_review.md")
    for key in (
        "NOT adopted",
        "Newey-West",
        "block",
        "Purged",
        "Breadth",
        "Selection bias",
        "evidence of poor performance",
    ):
        assert key in t, key


def test_data_feasibility_marks_unread_sources_unverified_and_separates_research_only():
    t = read("s8_data_commercial_feasibility.md")
    assert (
        t.count("**unverified**") >= 6
        and "Research-only (verified)" in t
        and "nothing is purchased" in t.lower()
    )


def test_v3_review_is_not_an_adoption():
    t = read("s8_risk_v3_adoption_review.md")
    assert "NOT adopted" in t and "NOT READY" in t and "G1" in t and "G5" in t


def test_report_states_limits_and_stops():
    t = read("s8_report.md")
    assert "NO-GO" in t and "Limitations" in t and "explicit approval" in t
