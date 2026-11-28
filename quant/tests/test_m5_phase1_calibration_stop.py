"""M5 Phase 1: the calibration STOP is recorded, results are pinned, nothing was registered or run on market data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from quantlab import vc_inference as vc


Q = Path(__file__).resolve().parents[1]
REC = json.loads(
    (Q / "protocol/m5_phase1_calibration_stop_record.json").read_text(encoding="utf-8")
)
R2 = json.loads((Q / "docs/phase4c/m5_calibration_round2_results.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_calibration_artifacts_are_pinned():
    for name, h in REC["files"].items():
        assert sha(Q / name) == h, f"{name} changed after the calibration stop"


def test_validation_failed_the_preregistered_rule_and_nothing_was_registered():
    val = R2["validation"]
    assert val["method"] == "M5" and val["pass"] is False
    worst = max(
        c["rejection_rate"]["M5"] for r in val["runs"].values() for c in r["cells"].values()
    )
    assert 0.07 < worst < 0.073
    budget = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))
    assert budget["state"]["total_n"] == 45
    assert [f["id"] for f in budget["state"]["further_families"]] == ["h1_lottery_max3"]
    assert REC["family_registered"] is False and REC["market_evaluation_executed"] is False
    assert not (Q / "protocol/m5_phase1_preregistration.json").exists()


def test_clopper_pearson_known_values():
    lo, hi = vc.clopper_pearson(5, 100)
    assert 0.016 < lo < 0.018 and 0.110 < hi < 0.115
    assert vc.clopper_pearson(0, 50)[0] == 0.0


def test_inference_is_deterministic_and_detects_a_shift():
    x = np.random.default_rng(1).normal(0.0, 0.05, (4, 600))
    a = vc.infer("M5", x, 7, np.random.default_rng(2))
    b = vc.infer("M5", x, 7, np.random.default_rng(2))
    assert np.array_equal(a["t"], b["t"])
    assert not a["reject"].any()
    assert vc.infer("M5", x + 0.05, 7, np.random.default_rng(2))["reject"].all()
    assert vc.lag_for("M0", 7) == 14 and vc.lag_for("M5", 7) == 60


def test_reduced_calibration_cell_is_reproducible():
    one = vc.run_cell(7, "S1_baseline", 7, 0.0, 20, ("M5",))
    two = vc.run_cell(7, "S1_baseline", 7, 0.0, 20, ("M5",))
    assert one == two and 0.0 <= one["rejection_rate"]["M5"] <= 1.0
