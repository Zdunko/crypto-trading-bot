"""M5 design acceptance record: the accepted design artifacts are unchanged; the Phase 1 approval is limited as the owner wrote it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/m5_design_acceptance_record.json").read_text(encoding="utf-8"))
APPR = json.loads((Q / "protocol/m5_phase1_owner_approval.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_accepted_m5_design_artifact_is_unchanged():
    assert len(REC["files"]) >= 8
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after the M5 design acceptance"


def test_phase1_approval_is_limited_to_option_r_phase1_and_excludes_phase2():
    assert APPR["approved"]["family"] == "h1_vol_control" and APPR["approved"][
        "configurations"
    ] == ["VC-h7", "VC-h28"]
    assert "47" in APPR["approved"]["budget"] and any("Phase 2" in x for x in APPR["not_approved"])
    assert any("H1b" in x for x in APPR["not_approved"]) and any(
        "STOP before market evaluation" in x for x in APPR["conditions"]
    )
