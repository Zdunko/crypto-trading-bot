"""M2 freeze: the registered evaluation, its code and the supporting studies are unchanged since registration; the
specification hash equals the approval; no market result exists in the frozen set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted

from quantlab import l1_max3 as m


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/m2_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_m2_file_is_unchanged():
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after the M2 freeze"


def test_spec_hash_equals_the_owner_approval_and_the_registry_and_no_market_result_is_frozen():
    spec = json.loads((Q / "protocol/h1_l1_preregistration.json").read_text(encoding="utf-8"))
    h = m.spec_sha256(spec)
    assert h == REC["spec_sha256"]
    appr = json.loads((Q / "protocol/run_approvals.json").read_text(encoding="utf-8"))["approvals"]
    assert any(
        a["spec_hash"] == h and a["approved_by"] == "owner" and a["family_id"] == "h1_lottery_max3"
        for a in appr
    )
    reg = json.loads((Q / "protocol/spec_registry.json").read_text(encoding="utf-8"))["registered"]
    assert any(r["spec_hash"] == h for r in reg)
    assert REC["market_results_existed_at_freeze"] is False and not any(
        "m3_" in k for k in REC["files"]
    )
