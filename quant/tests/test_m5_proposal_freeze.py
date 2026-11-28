"""M5 proposal freeze: the design-only deliverables stay unchanged until the owner decides."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/m5_proposal_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_m5_proposal_file_is_unchanged_and_the_status_is_design_only():
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after the M5 proposal freeze"
    assert REC["status"].startswith("DESIGN ONLY")
