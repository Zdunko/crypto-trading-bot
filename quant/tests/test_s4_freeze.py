"""The S4 dataset, manifest, criteria and provenance stay frozen (CRLF-normalised hashes)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


Q = Path(__file__).resolve().parents[1]
REC = json.loads((Q / "protocol/s4_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_dataset_file_is_unchanged():
    on_disk = {p.name for p in (Q / "dataset").iterdir() if p.is_file()}
    assert on_disk == set(REC["files"]), "a dataset file was added or removed"
    for name, h in REC["files"].items():
        assert sha(Q / "dataset" / name) == h, name


def test_dataset_hash_and_manifest_parts_match_the_record():
    man = json.loads((Q / "dataset/manifest.json").read_text(encoding="utf-8"))
    assert man["dataset_hash"] == REC["dataset_hash"] and man["parts"] == REC["manifest_parts"]


def test_criteria_and_reports_unchanged_since_pre_registration():
    c = REC["criteria"]
    assert (
        sha(Q.parent / c["path"]) == c["sha256"] == c["sha256_at_pre_registration_commit_58ba372"]
    )
    for name, h in REC["reports"].items():
        assert sha(Q / "docs/phase4c" / name) == h, name


def test_frozen_code_hashes_in_manifest_still_describe_the_code():
    # the manifest records the code that produced the dataset; a later edit must be a conscious new version
    man = json.loads((Q / "dataset/manifest.json").read_text(encoding="utf-8"))
    for f, h in man["code_sha256"].items():
        assert sha(Q / "quantlab" / f) == h, f"{f} changed after the dataset was built"
