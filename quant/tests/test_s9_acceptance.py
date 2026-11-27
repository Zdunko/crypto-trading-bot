"""S9 acceptance record: every accepted S9 artifact is unchanged; skipped jobs are not counted as passed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s9_acceptance_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_accepted_s9_artifact_is_unchanged():
    assert len(REC["files"]) >= 15
    for name, h in REC["files"].items():
        assert sha(Q / name) == h, f"{name} changed after S9 acceptance"


def test_outcome_does_not_count_skipped_jobs_as_passed():
    t = (Q / "docs/phase4c/s9_validation_outcome.md").read_text(encoding="utf-8")
    assert "24 success, 5 skipped, 0 failed, 0 cancelled" in t and "Skipped is **not** passed" in t
