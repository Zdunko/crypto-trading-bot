"""The S2 freeze record must keep matching the frozen files (no silent change of risk layer V2)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

from quantlab.risk_v2 import RiskV2Config


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s2_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    # CRLF normalised (as quantlab.protocol does) so Windows checkouts hash identically
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_frozen_files_and_manifest_unchanged():
    assert (
        sha(Q / REC["manifest_v6"]["path"].removeprefix("quant/")) == REC["manifest_v6"]["sha256"]
    )
    for p, h in REC["frozen_files"].items():
        assert sha(Q / p) == h, p


def test_risk_defaults_unchanged():
    cfg = json.dumps(dataclasses.asdict(RiskV2Config()), sort_keys=True, default=str)
    assert hashlib.sha256(cfg.encode()).hexdigest() == REC["risk_config_defaults_sha256"]


def test_preserved_manifests_and_amendments_unchanged():
    for n, h in REC["preserved_manifests"].items():
        assert sha(Q / "protocol" / n) == h, n
    for n, h in REC["amendments"].items():
        assert sha(Q / "protocol/amendments" / n) == h, n
    # the ledger is verified through the amendment chain by protocol.verify_all (check.sh / test_ledger)
