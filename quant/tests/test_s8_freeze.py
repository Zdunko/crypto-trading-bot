"""S8 deliverables stay frozen; the S6/S7 inputs of S8 are unchanged; nothing registered or approved."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s8_freeze_record.json").read_text(encoding="utf-8"))
PRE_REGISTRATION_COMMIT = "a54ff97"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_s8_file_and_every_unchanged_input_is_unchanged():
    for name, h in REC["files"].items():
        assert sha(Q / name) == h, f"{name} changed after the S8 freeze"


def test_criteria_equal_the_pre_registered_version():
    assert (
        REC["files"]["docs/phase4c/s8_criteria.json"]
        == REC["criteria_sha256_at_pre_registration_a54ff97"]
    )
    # when the history is available the pre-registration commit itself must hold the same bytes
    try:
        raw = subprocess.run(
            ["git", "show", f"{PRE_REGISTRATION_COMMIT}:quant/docs/phase4c/s8_criteria.json"],
            cwd=Q,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return  # shallow clone without that commit: the recorded hash above is the check
    assert (
        hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        == REC["criteria_sha256_at_pre_registration_a54ff97"]
    )


def test_budget_unchanged_nothing_approved_and_decision_recorded():
    st = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))["state"]
    assert st == REC["budget_state"] and st["total_n"] == 43 and st["further_families"] == []
    assert REC["approvals"] == [] and REC["decision"].startswith("NO-GO")
    reg = json.loads((Q / "protocol/spec_registry.json").read_text(encoding="utf-8"))
    assert reg.get("registered", []) == []
