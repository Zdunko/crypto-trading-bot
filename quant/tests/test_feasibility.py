"""S6 feasibility gate: calibration (Family A fails, synthetic example passes), one mutation per check,
fail-closed behaviour, determinism, anti-retrospective-change, no automatic authorisation."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from prereg_fixtures import TH, family_a_as_specified, synthetic_example

from quantlab import budget as budget_mod
from quantlab import feasibility as f


BUDGET = json.loads(budget_mod.BUDGET.read_text(encoding="utf-8"))
Q = Path(__file__).resolve().parents[1]


def failed(doc, **kw):
    return set(f.gate(doc, **kw)["failed"])


def test_synthetic_example_passes_every_check_and_authorises_nothing():
    r = f.gate(synthetic_example())
    assert r["verdict"] == "GATE_PASS" and r["failed"] == [] and len(r["checks"]) == 11
    assert r["authorizes_market_evaluation"] is False
    assert r["power"]["raw_episodes_p05"] >= 200 and r["power"]["mde_sharpe_p95"] <= 1.5


def test_family_a_as_specified_is_rejected_for_power_and_for_being_a_rejected_family():
    r = f.gate(family_a_as_specified())
    assert r["verdict"] == "GATE_FAIL"
    assert {"A7", "A9"} <= set(r["failed"])  # about 14 episodes; rejected family key
    assert "T1 not reachable" in r["checks"]["A7"]["reason"]
    # Family A's own numbers: raw episodes around 14, far below 200
    from quantlab.feasibility import power

    p = power(family_a_as_specified(), TH)
    assert 8 < p["raw_episodes_median"] < 20 and p["raw_episodes_p05"] < 200


def mutate(path, value):
    d = synthetic_example()
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value
    return d


MUTATIONS = {
    "A1": lambda: {k: v for k, v in synthetic_example().items() if k != "economic"},
    "A2": lambda: mutate(
        ("economic", "expected_failure_modes"), ["only one failure mode listed here"]
    ),
    "A3": lambda: mutate(("data", "dataset_hash"), "0" * 64),
    "A4": lambda: mutate(
        ("execution", "costs"), {"fee": 0.0, "slippage": 0.0, "stress_multiple": 2.0}
    ),
    "A5": lambda: mutate(("risk", "config_sha256"), "1" * 64),
    "A6": lambda: mutate(
        ("strategy", "configurations"),
        [
            {
                "id": "S1",
                "role": "primary",
                "description": "x",
                "parameters": [
                    {"name": f"p{i}", "value": i, "kind": "free", "source": ""} for i in range(4)
                ],
            }
        ],
    ),
    "A7": lambda: mutate(("expected", "entries_per_asset_year"), {"lo": 0.1, "hi": 0.2}),
    "A9": lambda: mutate(("family", "family_key"), "momentum_roc"),
    "A10": lambda: mutate(("declarations", "results_seen"), True),
    "A11": lambda: mutate(
        ("declarations", "holdout_metadata_acknowledged"), ["S1_listing_keys_and_last_month"]
    ),
}


@pytest.mark.parametrize("cid", sorted(MUTATIONS))
def test_each_check_fails_under_one_targeted_mutation(cid):
    r = f.gate(MUTATIONS[cid]())
    assert r["verdict"] == "GATE_FAIL" and cid in r["failed"], (cid, r["failed"])


def test_budget_check_fails_when_caps_are_exhausted_or_stop_rule_reached():
    full = copy.deepcopy(BUDGET)
    full["state"]["further_families"] = [
        {"id": f"F{i}", "configurations": 3, "market_runs": 0, "status": "preregistered"}
        for i in range(3)
    ]
    full["state"]["total_n"] = 43 + 9
    assert "A8" in failed(synthetic_example(), budget=full)
    stop = copy.deepcopy(BUDGET)
    stop["state"]["consecutive_rejected_under_v2"] = 2
    assert "A8" in failed(synthetic_example(), budget=stop)
    over = mutate(("budget", "new_configurations"), 3)
    assert "A6" in failed(over)  # configuration count must match the budget declaration


def test_duplicates_and_registered_ids_are_rejected():
    reg = json.loads(f.REGISTRY.read_text(encoding="utf-8"))
    d = synthetic_example()
    reg2 = copy.deepcopy(reg)
    reg2["registered"].append(
        {"family_id": "SYN-1", "title": "x", "spec_hash": "z", "config_hashes": []}
    )
    assert "A9" in failed(d, registry=reg2)
    reg3 = copy.deepcopy(reg)
    reg3["registered"].append(
        {
            "family_id": "OTHER",
            "title": "y",
            "spec_hash": "z",
            "config_hashes": [
                f.config_hash("synthetic_example", d["strategy"]["configurations"][0])
            ],
        }
    )
    assert "A9" in failed(d, registry=reg3)


def test_fail_closed_on_garbage_and_unreadable_inputs(monkeypatch):
    for bad in (None, 5, [], "x", {}, {"schema": "prereg-v1"}, {**synthetic_example(), "extra": 1}):
        r = f.gate(bad)
        assert (
            r["verdict"] == "GATE_FAIL"
            and "A1" in r["failed"]
            and r["authorizes_market_evaluation"] is False
        )
    nan = synthetic_example()
    nan["expected"]["rho"]["lo"] = float("nan")
    assert f.gate(nan)["verdict"] == "GATE_FAIL"
    inf = synthetic_example()
    inf["execution"]["max_participation"] = float("inf")
    assert f.gate(inf)["verdict"] == "GATE_FAIL"
    scalar = synthetic_example()
    scalar["strategy"]["configurations"][0]["parameters"][0]["value"] = [
        10,
        20,
        30,
    ]  # a search space
    assert "A6" in failed(scalar)
    monkeypatch.setattr(f, "CRITERIA", Path("/nonexistent/criteria.json"))
    assert f.gate(synthetic_example())["verdict"] == "GATE_FAIL"


def test_retrospective_changes_are_detected():
    d = synthetic_example()
    r = f.gate(d)
    rec = f.freeze_preregistration(d, r)
    assert f.gate(d, frozen=rec)["verdict"] == "GATE_PASS"
    d2 = copy.deepcopy(d)
    d2["strategy"]["configurations"][0]["parameters"][0]["value"] = 91  # edited after freezing
    assert "A10" in failed(d2, frozen=rec)
    d3 = copy.deepcopy(d)
    d3["declarations"]["gate_thresholds"] = {
        **TH,
        "min_raw_episodes_p05": 10,
    }  # loosened thresholds
    assert "A10" in failed(d3)
    assert f.gate(d3)["verdict"] == "GATE_FAIL"
    d4 = copy.deepcopy(d)
    d4["declarations"]["gate_thresholds"] = TH  # equal to the frozen ones is accepted
    assert f.gate(d4)["verdict"] == "GATE_PASS"
    with pytest.raises(f.Fail):
        f.freeze_preregistration(family_a_as_specified(), f.gate(family_a_as_specified()))
    bad_rec = {**rec, "thresholds_sha256": "0" * 64}
    assert "A10" in failed(d, frozen=bad_rec)


def test_result_is_deterministic_across_key_order_and_processes(tmp_path):
    d = synthetic_example()
    a = f.gate(d)
    b = f.gate(json.loads(json.dumps(d, sort_keys=True)))
    c = f.gate(dict(reversed(list(d.items()))))
    assert a["result_hash"] == b["result_hash"] == c["result_hash"]
    path = tmp_path / "p.json"
    path.write_text(json.dumps(d), encoding="utf-8")
    outs = [
        subprocess.run(
            [sys.executable, "-m", "quantlab.feasibility", "check", str(path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=Q,
        )
        for _ in range(2)
    ]
    assert outs[0].returncode == 0 and outs[0].stdout == outs[1].stdout
    assert json.loads(outs[0].stdout)["result_hash"] == a["result_hash"]


def test_a_gate_pass_never_authorises_a_run():
    d = synthetic_example()
    r = f.gate(d)
    rec = f.freeze_preregistration(d, r)
    budget = copy.deepcopy(BUDGET)
    # not registered in the budget yet -> no run
    assert f.may_start_market_run("SYN-1", budget, {"approvals": []}, rec)[0] is False
    budget["state"]["further_families"] = [
        {"id": "SYN-1", "configurations": 2, "market_runs": 0, "status": "preregistered"}
    ]
    budget["state"]["total_n"] = 45
    assert f.may_start_market_run("SYN-1", budget, {"approvals": []}, rec) == (
        False,
        "no explicit owner approval for this exact specification",
    )
    approval = {
        "family_id": "SYN-1",
        "approved_by": "owner",
        "spec_hash": rec["spec_hash"],
        "text_sha256": "a" * 64,
    }
    assert f.may_start_market_run("SYN-1", budget, {"approvals": [approval]}, rec) == (True, "ok")
    assert (
        f.may_start_market_run(
            "SYN-1", budget, {"approvals": [{**approval, "spec_hash": "0" * 64}]}, rec
        )[0]
        is False
    )
    assert (
        f.may_start_market_run(
            "SYN-1", budget, {"approvals": [{**approval, "approved_by": "agent"}]}, rec
        )[0]
        is False
    )
    assert f.may_start_market_run("SYN-1", budget, {"approvals": [approval]}, None)[0] is False
    # the real files: nothing but the amendment-declared H1 registration and its L1-only approval
    from amend_chain import accepted_approvals

    assert json.loads(f.APPROVALS.read_text(encoding="utf-8"))["approvals"] in accepted_approvals(
        []
    )
    assert [x["id"] for x in BUDGET["state"]["further_families"]] in ([], ["h1_lottery_max3"])


def test_template_is_machine_readable_and_not_passable():
    t = json.loads(f.TEMPLATE.read_text(encoding="utf-8"))
    r = f.gate(t)
    assert r["verdict"] == "GATE_FAIL" and {"A2", "A7"} <= set(
        r["failed"]
    )  # placeholders and zero episodes
    assert t["schema"] == "prereg-v1" and set(t) == set(f.SECTIONS)
