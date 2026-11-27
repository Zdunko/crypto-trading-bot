"""S7 acceptance record: every accepted S7 artifact is unchanged; the validation outcome document is frozen."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s7_acceptance_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_accepted_s7_artifact_is_unchanged():
    assert len(REC["files"]) >= 8
    for name, h in REC["files"].items():
        assert sha(Q / name) == h, f"{name} changed after S7 acceptance"


def test_outcome_states_intermittency_without_weakening_ci():
    t = (Q / "docs/phase4c/s7_validation_outcome.md").read_text(encoding="utf-8")
    assert "intermittent" in t and "No upstream test was modified, skipped or suppressed" in t
    assert "cancelled by the workflow concurrency group" in t and "Not a validation result" in t
