"""The committed S4 dataset tables must stay self-consistent, development-window only and passing."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from quantlab import pit_universe as pu


D = Path(__file__).resolve().parents[1] / "dataset"


def text(name: str) -> str:
    with gzip.open(D / name, "rt", encoding="utf-8", newline="") as f:
        return f.read()


def test_manifest_hash_is_recomputable_from_the_committed_files():
    man = json.loads((D / "manifest.json").read_text(encoding="utf-8"))
    parts = {
        "files": pu.sha(text("files.csv.gz")),
        "epochs": pu.sha(text("epochs.csv.gz")),
        "membership": pu.sha(text("membership.csv.gz")),
        "classification": pu.sha(
            (D / "asset_classification.json").read_bytes().replace(b"\r\n", b"\n")
        ),
    }
    assert parts == man["parts"]
    assert pu.dataset_hash(parts, man["params"]) == man["dataset_hash"]


def test_no_holdout_month_anywhere_in_the_dataset():
    rows = list(csv.DictReader(text("files.csv.gz").splitlines()))
    assert rows and max(r["month"] for r in rows) < "2025-07"
    mem = list(csv.DictReader(text("membership.csv.gz").splitlines()))
    assert max(r["date"] for r in mem) <= "2025-06"
    listing = json.loads((D / "dev_window_listing.json").read_text(encoding="utf-8"))
    assert max(m for v in listing.values() for m in v) < "2025-07"


def test_recorded_gates_all_passed_and_every_non_ok_file_has_a_reason():
    g = json.loads((D / "gates.json").read_text(encoding="utf-8"))
    assert g["verdict"] == "GO" and g["failed"] == []
    for r in csv.DictReader(text("files.csv.gz").splitlines()):
        if r["status"] != "ok":
            assert set(r["reasons"].split("|")) <= set(pu.REASONS) and r["reasons"]
