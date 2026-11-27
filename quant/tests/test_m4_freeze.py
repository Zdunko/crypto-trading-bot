"""M4 freeze: the registered L2 evaluation, its code and the unchanged inputs stay frozen; the spec hash equals the approval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted

from quantlab import l2_run as run


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/m4_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_m4_file_is_unchanged():
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after the M4 freeze"


def test_spec_hash_equals_the_owner_approval_and_no_l2_result_is_frozen():
    spec = json.loads((Q / "protocol/m4_l2_preregistration.json").read_text(encoding="utf-8"))
    h = run.spec_hash(spec)
    assert h == REC["spec_sha256"]
    appr = json.loads((Q / "protocol/run_approvals.json").read_text(encoding="utf-8"))["approvals"]
    assert any(
        a["spec_hash"] == h and a["approved_by"] == "owner" and a["scope"].startswith("L2")
        for a in appr
    )
    assert REC["l2_market_results_existed_at_freeze"] is False and not any(
        "m4_l2_results" in k for k in REC["files"]
    )
