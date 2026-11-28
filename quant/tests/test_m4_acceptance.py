"""M4 acceptance record: accepted artifacts unchanged; the macOS jobs are an infrastructure limitation, not passed tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/m4_acceptance_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_accepted_m4_artifact_is_unchanged():
    assert len(REC["files"]) >= 20 and REC["result_level"].startswith("L2 NO-GO")
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after the M4 acceptance"


def test_outcome_does_not_count_cancelled_or_skipped_jobs_as_passed():
    t = (Q / "docs/phase4c/m4_validation_outcome.md").read_text(encoding="utf-8")
    assert (
        "Unresolved infrastructure limitation" in t
        and "NOT passed" in t.replace("**not** passed", "NOT passed")
    ) or "not passed tests" in t
    assert "macos-26, 3.12" in t and "Skipped is **not** passed" in t
