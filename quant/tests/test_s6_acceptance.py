"""S6 is accepted and frozen; every historical freeze record still verifies; the research budget stays N=43/52."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted, accepted_budget_states

from quantlab import budget


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s6_acceptance_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_accepted_s6_artifacts_are_unchanged():
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after S6 acceptance"


def test_all_historical_freeze_records_exist_and_budget_is_unchanged():
    for name in REC["historical_freeze_records"]:
        assert (Q / name).exists()
    b = json.loads(budget.BUDGET.read_text(encoding="utf-8"))
    assert REC["research_budget"]["total_n"] == 43
    baseline = json.loads((Q / "protocol/s7_freeze_record.json").read_text(encoding="utf-8"))[
        "budget_state"
    ]
    assert b["state"] in accepted_budget_states(
        baseline
    )  # baseline N=43, or the state declared by amendment A11
    assert b["caps"]["max_total_n"] == REC["research_budget"]["cap"] == 52 and budget.check() == 0
