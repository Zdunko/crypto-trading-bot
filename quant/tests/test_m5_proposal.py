"""M5 proposal is DESIGN ONLY: the draft is not registered or approved, the budget is unchanged and reconciled, the budget
options are consistent with the caps, no M5 market result exists, and the key rules are present."""

from __future__ import annotations

import json
from pathlib import Path

from quantlab import l2_run as run


Q = Path(__file__).resolve().parents[1]
DRAFT = json.loads(
    (Q / "protocol/proposals/m5_incremental_value_preregistration_DRAFT.json").read_text(
        encoding="utf-8"
    )
)
B = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))
LED = json.loads((Q / "protocol/experiment_ledger.json").read_text(encoding="utf-8"))
DOC = (Q / "docs/phase4c/m5_incremental_value_proposal.md").read_text(encoding="utf-8")


def test_the_draft_is_not_registered_not_approved_and_the_budget_is_unchanged():
    assert DRAFT["status"].startswith("DRAFT PROPOSAL, NOT REGISTERED, NOT APPROVED")
    h = run.spec_hash(DRAFT)
    appr = json.loads((Q / "protocol/run_approvals.json").read_text(encoding="utf-8"))["approvals"]
    assert not any(a["spec_hash"] == h for a in appr) and all(
        a["family_id"] == "h1_lottery_max3" for a in appr
    )
    ids = [f["id"] for f in B["state"]["further_families"]]
    assert ids == ["h1_lottery_max3"] and B["state"]["total_n"] == 45
    reg = json.loads((Q / "protocol/spec_registry.json").read_text(encoding="utf-8"))["registered"]
    assert all(r["family_id"] == "h1_lottery_max3" for r in reg)
    assert not list((Q / "docs/phase4c").glob("m5_*results*.json")) or all(
        "power" in p.name for p in (Q / "docs/phase4c").glob("m5_*results*.json")
    )


def test_budget_reconciliation_matches_the_ledger_including_the_m4_replay():
    comp = LED["configurations_evaluated_on_research_data"]
    assert (
        comp["phase3"]["subtotal"] + comp["phase4"]["subtotal"] + comp["family_a"]["subtotal"]
        == comp["total_distinct"]
        == 43
    )
    fam = B["state"]["further_families"][0]
    assert B["state"]["total_n"] == 43 + fam["configurations"] == 45
    assert (
        fam["market_runs"] == 1
        and fam["diagnostic_replays_used"] == 1
        and LED["registered_families"][0]["diagnostic_replay"]["adds_configurations"] == 0
    )
    led = DRAFT["budget"]["ledger_today"]
    assert (
        led["baseline_N"] == 43
        and led["total_N"] == 45
        and led["baseline_composition"] == {"phase3": 26, "phase4": 14, "family_a": 3}
    )


def test_the_budget_options_are_consistent_with_the_caps_and_the_remaining_room():
    caps = B["caps"]
    r, c = DRAFT["budget"]["recommended_option_R"], DRAFT["budget"]["conservative_option_C"]
    cfg_r = len(DRAFT["family"]["configurations"])
    assert (
        cfg_r == 2 <= caps["max_configurations_per_family"]
        and r["N_after_registration"] == 45 + cfg_r == 47 <= caps["max_total_n"]
    )
    assert (
        r["N_cost"] == 2
        and c["N_after"] == 45 + 4 == 49
        and 2 + 2 > caps["max_configurations_per_family"]
    )  # option C needs an exception
    assert (
        caps["max_market_runs_per_family"] == 1 and caps["max_diagnostic_replays_per_family"] == 1
    )  # stage 1 = run, stage 2 = replay
    assert 1 + 1 + 1 <= caps["max_further_families"]  # H1 + this family + one later family
    rem = caps["max_total_n"] - r["N_after_registration"]
    assert (
        rem == DRAFT["budget"]["remaining_after_R"]["N"] == 5 and 47 + 3 <= caps["max_total_n"]
    )  # one more family of 3 fits (N 50)


def test_key_design_rules_are_present():
    s2 = DRAFT["stage2_economic_research_only"]
    assert (
        "NEVER qualifies as an operational L2 pass" in s2["label"].upper().replace("NEVER", "NEVER")
        or "never qualifies as an operational L2 pass" in s2["label"]
    )
    assert "circuit breaker OFF" in s2["protection"] and "SHADOW" in s2["protection"]
    assert {
        "exposure_matched",
        "causally_risk_matched",
        "volatility_matched_low_volatility",
    } <= set(s2["comparators"])
    assert all(
        "CAUSAL" in s2["comparators"][k]
        for k in ("exposure_matched", "causally_risk_matched", "volatility_matched_low_volatility")
    )
    st1 = DRAFT["stage1_signal_level"]
    assert (
        abs(float(st1["min_effect"]["rule"].split(">= ")[1].split(" ")[0]) - 0.003522504892367907)
        < 1e-15
    )
    assert (
        "Holm" in st1["multiple_testing"]
        and "surrogate" in json.dumps(st1["negative_control_surrogates"]).lower()
    )
    assert (
        set(DRAFT["decision_tree"]) >= {"D1", "D2", "D3", "D4", "D5", "D6", "D7"}
        and len(DRAFT["stopping_rules"]) >= 4
    )
    for needle in (
        "Recommendation",
        "sufficiency",
        "Limitations",
        "abandon H1",
        "research-only unprotected",
    ):
        assert needle.lower() in DOC.lower(), needle
