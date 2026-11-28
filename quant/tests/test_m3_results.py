"""M3: the stored single-run result is consistent with the registration, the decision is recomputed from the stored
numbers, the budget consumption is recorded, and the caveats quoted in the report are pinned. No market data is read."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quantlab import l1_max3 as m


Q = Path(__file__).resolve().parents[1]
R = json.loads((Q / "docs/phase4c/m3_l1_results.json").read_text(encoding="utf-8"))
SPEC = json.loads((Q / "protocol/h1_l1_preregistration.json").read_text(encoding="utf-8"))
M2 = json.loads((Q / "protocol/m2_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_result_belongs_to_the_frozen_registration_dataset_and_code():
    assert R["spec_sha256"] == m.spec_sha256(SPEC) == M2["spec_sha256"]
    assert R["code_sha256"] == M2["files"]["quantlab/l1_max3.py"]
    s4 = json.loads((Q / "protocol/s4_freeze_record.json").read_text(encoding="utf-8"))
    assert R["dataset_hash"] == s4["dataset_hash"]
    assert (
        R["panel"]["last_date"] == "2025-06-29" and R["panel"]["last_date"] < "2025-06-30"
    )  # holdout never read


def test_decision_is_recomputed_from_the_stored_numbers_and_both_configurations_are_reported():
    assert set(R["configurations"]) == {"H1-h7", "H1-h28"}
    again = m.decide(SPEC, R["configurations"], R["disguise"], True)
    for cid in R["configurations"]:
        a, b = again["configurations"][cid], R["decision"]["configurations"][cid]
        assert (
            a["criteria"] == b["criteria"]
            and a["gates"] == b["gates"]
            and abs(a["p_holm"] - b["p_holm"]) < 1e-15
        )
    assert R["decision"]["L1_PASS"] is True and R["decision"]["decision"] == "L1 PASS"
    assert (
        R["reproducibility"]["second_run_in_process_identical"]
        and R["reproducibility"]["separate_process_identical"]
    )
    assert all(R["prefix_invariance"].values()) and R["decision"]["disguise_passes"] is True


def test_quoted_statistics():
    h7, h28 = R["configurations"]["H1-h7"], R["configurations"]["H1-h28"]
    assert 0.09 < h7["mean_ic"] < 0.094 and 0.115 < h28["mean_ic"] < 0.118
    assert 8.5 < h7["t_hac"] < 8.7 and 5.6 < h28["t_hac"] < 5.7
    assert (
        h7["n_days"] == 1633
        and h28["n_days"] == 1612
        and h7["hac_lag"] == 14
        and h28["hac_lag"] == 56
    )
    for c in (h7, h28):
        assert all(v["mean_ic"] > 0 for v in c["subperiods"].values())
        assert (
            c["coverage"]["coverage_ratio"] > 0.997
            and c["cross_section"]["min_assets_per_valid_day"] >= 40
        )
    assert 320 < h7["effective_n_days"] < 330 and 80 < h28["effective_n_days"] < 86
    assert all(
        v["would_pass_program_wide"] for v in R["program_wide_sensitivity_not_gating"].values()
    )


def test_caveats_pinned_volatility_confound_and_disguise_values():
    vol = R["disguise"]["realised_vol_28d_informational"]
    assert (
        vol["mean_rank_corr"] < -0.9
        and vol["share_days_abs_above_bound"] > 0.99
        and vol["gating"] is False
    )
    assert abs(R["disguise"]["max_abs_mean_rank_corr_gating"] - 0.3787) < 1e-3
    rep = (Q / "docs/phase4c/m3_l1_report.md").read_text(encoding="utf-8")
    assert (
        "low-volatility signal" in rep
        and "L1 PASS" in rep
        and "does NOT license" in rep
        and "10x larger" in rep
    )


def test_budget_consumption_is_recorded_and_the_level_is_not_overstated():
    b = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))["state"]
    fam = b["further_families"][0]
    assert b["total_n"] == 45 and fam["market_runs"] == 1 and fam["status"] == "evaluated_accepted"
    assert fam["result_level"].startswith("L1 only") and fam["result_sha256"] == sha(
        Q / "docs/phase4c/m3_l1_results.json"
    )
    led = json.loads((Q / "protocol/experiment_ledger.json").read_text(encoding="utf-8"))[
        "registered_families"
    ][0]["market_run"]
    assert (
        led["result_sha256"] == fam["result_sha256"]
        and led["holdout_accessed"] is False
        and led["market_runs_consumed"] == 1
    )
