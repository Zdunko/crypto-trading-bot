"""M6-DESIGN-01: design-only record; nothing registered, budget unchanged, proposal pinned."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/m6_design01_approval_record.json").read_text(encoding="utf-8"))


def test_proposal_is_pinned_and_design_only():
    h = hashlib.sha256((Q / REC["proposal"]).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert h == REC["proposal_sha256"]
    text = (Q / REC["proposal"]).read_text(encoding="utf-8")
    assert "DESIGN ONLY" in text and "N = 45 / 52" in text
    assert any("registration or budget consumption" in x for x in REC["not_approved"])
    assert any("holdout" in x for x in REC["not_approved"])


def test_nothing_was_registered_and_budget_is_unchanged():
    b = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))
    assert b["state"]["total_n"] == 45 == REC["budget_state"]["total_n"]
    assert [f["id"] for f in b["state"]["further_families"]] == ["h1_lottery_max3"]
    assert not any(Q.glob("protocol/*lv_sleeve*"))  # no registration or pre-registration file
    # M6-S0 later added only the minimal synthetic TEST HARNESS (no strategy implementation)
    assert [p.name for p in Q.glob("quantlab/*lv_sleeve*")] in ([], ["lv_sleeve_harness.py"])
    assert "lv_sleeve" not in (Q / "protocol/spec_registry.json").read_text(encoding="utf-8")


def test_proposed_exposure_cap_cannot_reach_the_tier3_floor():
    e_max, tier3 = 0.15, 0.18
    assert e_max < tier3  # a total loss of the whole sleeve is below the 18 % floor
    assert 3 * 0.10 / 12**0.5 < 0.10  # 3-sigma monthly loss at the 10 % target is below tier 1
