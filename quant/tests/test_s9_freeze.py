"""S9 deliverables stay frozen; inputs from S6-S8 unchanged; nothing registered, approved or run."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from amend_chain import accepted, accepted_budget_states, accepted_registry_ids


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s9_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_s9_file_and_unchanged_input_is_unchanged():
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after the S9 freeze"


def test_criteria_equal_the_pre_registered_version():
    assert (
        REC["files"]["docs/phase4c/s9_criteria.json"]
        == REC["criteria_sha256_at_pre_registration_60cce9b"]
    )
    try:
        raw = subprocess.run(
            ["git", "show", "60cce9b:quant/docs/phase4c/s9_criteria.json"],
            cwd=Q,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return  # shallow clone: the recorded hash is the check
    assert (
        hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        == REC["criteria_sha256_at_pre_registration_60cce9b"]
    )


def test_budget_unchanged_nothing_registered_or_approved():
    st = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))["state"]
    assert st in accepted_budget_states(REC["budget_state"])
    assert REC["approvals"] == [] and REC["selected_candidate"] == "H1"
    reg = json.loads((Q / "protocol/spec_registry.json").read_text(encoding="utf-8"))
    ids = [r["family_id"] for r in reg.get("registered", [])]
    assert ids in accepted_registry_ids([])
