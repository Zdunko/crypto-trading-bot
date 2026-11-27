"""M0-M3 acceptance record: accepted artifacts unchanged; the macOS jobs are documented as an infrastructure limitation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/m3_acceptance_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_accepted_m3_artifact_is_unchanged():
    assert len(REC["files"]) >= 20 and REC["result_level"] == "L1 only"
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after the M3 acceptance"


def test_macos_jobs_are_an_infrastructure_limitation_not_passed_tests():
    t = (Q / "docs/phase4c/m3_validation_outcome.md").read_text(encoding="utf-8")
    assert (
        "Unresolved infrastructure limitation" in t
        and "not passed tests" in t
        and "Skipped is **not** passed" in t
    )
    assert "macos-15, 3.12" in t and "macos-15, 3.13" in t and "macos-15, 3.14" in t
