"""M4 results freeze: result, report and the registered code stay unchanged; the level is not overstated."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amend_chain import accepted


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/m4_results_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_frozen_m4_result_file_is_unchanged_and_the_decision_is_no_go():
    for name, h in REC["files"].items():
        assert sha(Q / name) in accepted(name, h), f"{name} changed after the M4 results freeze"
    assert REC["result_level"].startswith("L2 NO-GO")
