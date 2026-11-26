"""S7 deliverables stay frozen; the v3 spec matches the code; nothing registered or approved."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s7_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_s7_file_is_unchanged():
    for name, h in REC["files"].items():
        assert sha(Q / name) == h, f"{name} changed after the S7 freeze"


def test_criteria_equal_the_pre_registered_version_and_nothing_is_registered():
    assert (
        REC["files"]["docs/phase4c/s7_criteria.json"]
        == REC["criteria_sha256_at_pre_registration_5ffce7c"]
    )
    st = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))["state"]
    assert st == REC["budget_state"] and st["total_n"] == 43 and st["further_families"] == []
    assert REC["approvals"] == []
