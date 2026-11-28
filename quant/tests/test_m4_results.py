"""M4: the stored single L2 replay is consistent with the registration; the decision is recomputed from the stored numbers; the
budget consumption is recorded; the caveats quoted in the report are pinned. No market data is read."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quantlab import l2_portfolio as l2
from quantlab import l2_run as run


Q = Path(__file__).resolve().parents[1]
R = json.loads((Q / "docs/phase4c/m4_l2_results.json").read_text(encoding="utf-8"))
SPEC = json.loads((Q / "protocol/m4_l2_preregistration.json").read_text(encoding="utf-8"))
M4 = json.loads((Q / "protocol/m4_freeze_record.json").read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_result_belongs_to_the_frozen_registration_dataset_and_code():
    assert R["spec_sha256"] == run.spec_hash(SPEC) == M4["spec_sha256"]
    for f, h in R["code_sha256"].items():
        if f in M4["files"]:
            assert h == M4["files"][f], f
    s4 = json.loads((Q / "protocol/s4_freeze_record.json").read_text(encoding="utf-8"))
    assert R["dataset_hash"] == s4["dataset_hash"]
    assert (
        R["reproducibility"]["engine_hashes_second_run_identical"]
        and R["reproducibility"]["separate_process_identical"]
    )
    assert len(R["engine_hashes"]) == 12


def test_decision_is_recomputed_from_the_stored_numbers_and_both_configurations_are_decided():
    again = l2.decide_config(SPEC, R["configurations"])
    assert set(again) == {"H1-h7", "H1-h28"}
    for cid, d in again.items():
        assert (
            d["criteria"] == R["decision"][cid]["criteria"]
            and d["decision"] == R["decision"][cid]["decision"] == "NO-GO"
        )
    assert R["decision"]["H1-h7"]["failed"] == [
        "A4_no_v3_shutdown",
        "A5_incremental_value_vs_low_volatility",
    ]
    assert R["decision"]["H1-h28"]["failed"] == [
        "A3_max_drawdown_within_limit",
        "A4_no_v3_shutdown",
        "A5_incremental_value_vs_low_volatility",
    ]


def test_quoted_economic_numbers():
    h7, h28 = R["configurations"]["H1-h7"], R["configurations"]["H1-h28"]
    assert (
        0.72 < h7["normal"]["metrics"]["net_return"] < 0.73
        and 0.92 < h28["normal"]["metrics"]["net_return"] < 0.93
    )
    assert (
        h7["double"]["metrics"]["net_return"] < h7["normal"]["metrics"]["net_return"]
        and h28["double"]["metrics"]["net_return"] < h28["normal"]["metrics"]["net_return"]
    )
    assert h7["normal"]["capital_protection"]["first_shutdown_time"].startswith("2021-02-23")
    assert h28["normal"]["capital_protection"]["first_shutdown_time"].startswith("2021-05-19")
    assert (
        h7["normal"]["execution"]["mean_exposure"] < 0.02
        and h28["normal"]["execution"]["mean_exposure"] < 0.035
    )  # in cash after the shutdown
    nr7, nr28 = (
        h7["normal"]["no_risk_diagnostic"]["metrics"],
        h28["normal"]["no_risk_diagnostic"]["metrics"],
    )
    assert (
        -0.12 < nr7["net_return"] < -0.11
        and 1.29 < nr28["net_return"] < 1.31
        and nr7["max_drawdown"] > 0.85
        and nr28["max_drawdown"] > 0.8
    )
    assert h7["double"]["no_risk_diagnostic"]["metrics"]["net_return"] < -0.27
    b = h7["benchmarks"]
    assert (
        2.6 < b["btc_buy_hold"]["net_return"] < 2.7
        and -0.26 < b["equal_weight"]["net_return"] < -0.24
        and b["cash"]["net_return"] == 0.0
    )
    assert (
        h7["normal"]["execution"]["fill_ratio"] >= 0.95
        and h28["normal"]["execution"]["fill_ratio"] >= 0.95
    )


def test_incremental_value_test_is_uninformative_because_both_portfolios_were_shut_down_by_v3():
    h7, h28 = R["configurations"]["H1-h7"], R["configurations"]["H1-h28"]
    assert (
        h7["normal"]["low_volatility"]["capital_protection"]["first_shutdown_time"]
        == h7["normal"]["capital_protection"]["first_shutdown_time"]
    )
    assert (
        h7["incremental_vs_low_volatility"]["p_one_sided"] > 0.5
        and h28["incremental_vs_low_volatility"]["p_one_sided"] > 0.5
    )
    assert (
        h28["normal"]["low_volatility"]["capital_protection"]["shutdown"]
        and h28["normal"]["capital_protection"]["shutdown"]
    )


def test_verification_diagnostics_support_the_l1_result_as_not_an_artefact():
    for cid, v in R["verification"].items():
        assert (
            v["V1_independent_reimplementation"]["max_abs_daily_ic_difference"]
            <= SPEC["diagnostics"]["V1_tolerance"]
        ), cid
        assert all(v["flags"].values()), (cid, v["flags"])
        assert (
            v["V3_survivors_only"]["assets_failed"] == 83
            and v["V2_permutation_placebo"]["max_abs_mean"] < 0.01
        )
        assert v["V2_entry_delayed_one_day"]["mean_ic"] > 0.8 * v["registered"]["mean_ic"]


def test_budget_consumption_is_recorded_and_the_level_is_not_overstated():
    b = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))
    fam = b["state"]["further_families"][0]
    assert (
        b["state"]["total_n"] == 45
        and fam["diagnostic_replays_used"] == 1
        and fam["l2_result_sha256"] == sha(Q / "docs/phase4c/m4_l2_results.json")
    )
    assert fam["result_level"].startswith(
        "L1 only"
    )  # the family is still only an L1 result; L2 was a NO-GO
    led = json.loads((Q / "protocol/experiment_ledger.json").read_text(encoding="utf-8"))[
        "registered_families"
    ][0]["diagnostic_replay"]
    assert (
        led["result_sha256"] == fam["l2_result_sha256"]
        and led["holdout_accessed"] is False
        and "NO-GO" in led["outcome"]
    )
    rep = (Q / "docs/phase4c/m4_l2_report.md").read_text(encoding="utf-8")
    assert "L2 NO-GO" in rep and "shut down" in rep and "does NOT license" in rep
