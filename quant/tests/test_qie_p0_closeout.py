"""QIE-P0: the research-cycle closeout freeze record is additive, pins the historical records, and is consistent
with the budget. Documentation consistency only; no market data, no holdout."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted


Q = Path(__file__).resolve().parents[1]
REC = json.loads(
    (Q / "protocol/research_cycle_closeout_freeze_record.json").read_text(encoding="utf-8")
)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_pinned_historical_record_is_unchanged_or_amended():
    assert len(REC["pinned_records"]) > 150
    for name, h in REC["pinned_records"].items():
        rel = name.removeprefix("quant/")
        assert sha(Q / rel) in accepted(rel, h), f"{name} changed after the closeout freeze"


def test_closeout_documents_are_pinned_and_present():
    assert len(REC["documents"]) >= 2
    for name, h in REC["documents"].items():
        if name.endswith("s4_limitations_register.md"):
            continue  # living register
        assert sha(Q.parent / name) == h, name


def test_budget_and_scope_are_unchanged():
    b = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))["state"]
    assert b["total_n"] == REC["budget"]["total_n"] == 45
    assert [f["id"] for f in b["further_families"]] == REC["budget"]["family_ids"]
    assert REC["budget"]["reset"] is False and REC["budget"]["new_registration"] is False
    assert "never accessed" in REC["holdout"] and "unresolved" in REC["licensing"]
    assert "holdout access" in REC["not_done"] and "backtests" in REC["not_done"]


def test_status_and_roadmap_point_to_the_closeout():
    root = Q.parent
    status = (root / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    road = (root / "ROADMAP.md").read_text(encoding="utf-8")
    assert "Authoritative current state (2026-11-28" in status and "N = 45 / 52" in status
    assert (
        "Current direction (2026-11-28, QIE-P0)" in road
        and "No P1 or later work is authorised" in road
    )
    plan = (Q / "docs/phase4c/qie_roadmap_design.md").read_text(encoding="utf-8")
    for p in ("P1", "P2", "P3", "P4", "P5", "Archive option"):
        assert p in plan
    assert "No P1 or later work starts without an explicit, separate owner approval" in plan
