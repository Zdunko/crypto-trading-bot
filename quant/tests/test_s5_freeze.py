"""The accepted S5-infra artifacts (loader, guard, budget, reports, investigations) stay frozen."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s5_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_s5_file_is_unchanged():
    for name, h in REC["files"].items():
        assert sha(Q / name) == h, f"{name} changed after the S5-infra freeze"


def test_research_budget_state_is_the_frozen_baseline():
    st = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))["state"]
    assert st == REC["budget_state"]  # no family registered, N=43, nothing consumed
