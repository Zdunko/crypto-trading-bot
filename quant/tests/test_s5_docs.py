"""S5 preparatory deliverables exist and say what the pre-registered criteria require (P2, P3, P5-P7)."""

from __future__ import annotations

import json
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "docs/phase4c"


def read(name: str) -> str:
    return (D / name).read_text(encoding="utf-8")


def test_limitations_register_lists_macos_as_unresolved_infrastructure_not_passed_tests():
    t = read("s4_limitations_register.md")
    row = next(r for r in t.splitlines() if "L-CI-MAC" in r)
    assert "cancelled" in row and "not passed tests" in row and "infrastructure" in row
    for ident in (
        "L-LIC",
        "L-ID",
        "L-LIQ",
        "L-CYC",
        "L-X1",
        "L-LOG",
        "L-NAMES",
        "L-CLASS",
        "L-MUT",
    ):
        assert ident in t


def test_x1_classification_is_exhaustive_and_eligibility_untouched():
    r = json.loads((D / "s5_x1_investigation.json").read_text(encoding="utf-8"))
    assert (
        r["class_sum_equals_total"]
        and sum(r["class_counts"].values()) == r["months_inconsistent"] == 1029
    )
    for v in r["eligibility_impact"].values():
        assert v["added"] == 0 and v["removed"] == 0  # measured; the frozen dataset needs no change


def test_identity_review_covers_all_events():
    r = json.loads((D / "s5_identity_review.json").read_text(encoding="utf-8"))
    assert r["events_total"] == 43 and sum(r["signature_counts_all"].values()) == 43
    assert r["conservative_handling_cost"]["share_of_frozen"] < 0.01


def test_isolation_statement_does_not_overclaim():
    t = read("s5_holdout_isolation_statement.md")
    assert "## Not claimed" in t and "S1" in t and "183" in t and "log" in t


def test_roadmap_and_scope_make_no_purchase_and_do_not_run_original_s5():
    assert "Nothing is purchased" in read("s5_production_data_licensing_roadmap.md")
    s = read("s5_scope.md")
    assert (
        "NOT executed" in s
        and "requires a prohibited activity"
        in s.replace("**Yes.** ", "").replace(
            "require a prohibited activity", "requires a prohibited activity"
        )
        or "prohibited" in s
    )
