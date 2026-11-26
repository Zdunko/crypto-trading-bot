"""S6 gate, benchmark registry, thresholds and proposal stay frozen; no family registered, no run approved."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s6_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_s6_file_is_unchanged():
    for name, h in REC["files"].items():
        assert sha(Q / name) == h, f"{name} changed after the S6 freeze"


def test_criteria_equal_the_pre_registered_version():
    c = REC["files"]["docs/phase4c/s6_criteria.json"]
    assert c == REC["criteria_sha256_at_pre_registration_f053d61"]


def test_no_family_registered_and_no_market_run_approved():
    st = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))["state"]
    assert st == REC["budget_state"] and st["further_families"] == [] and st["total_n"] == 43
    assert (
        json.loads((Q / "protocol/run_approvals.json").read_text(encoding="utf-8"))["approvals"]
        == []
    )
    assert REC["approvals"] == []
