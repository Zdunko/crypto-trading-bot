"""Research-budget enforcement (L5): caps, stop rule, ledger consistency, wired into check.sh."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from quantlab import budget


Q = Path(__file__).resolve().parents[1]
B = json.loads(budget.BUDGET.read_text(encoding="utf-8"))


def fam(i, cfg=3, runs=0, status="preregistered"):
    return {"id": f"F{i}", "configurations": cfg, "market_runs": runs, "status": status}


def with_state(**kw):
    b = copy.deepcopy(B)
    b["state"].update(kw)
    return b


def test_real_budget_and_ledger_pass_and_baseline_is_recorded():
    assert budget.violations(B) == []
    st = B["state"]
    assert (
        st["total_n"]
        == 43
        == budget.ledger_n(json.loads(budget.LEDGER.read_text(encoding="utf-8")))
    )
    assert st["further_families"] == [] and B["caps"]["max_total_n"] == 52
    assert budget.check() == 0


def test_every_cap_is_enforced():
    assert budget.violations(
        with_state(further_families=[fam(i) for i in range(4)], total_n=43 + 12)
    )
    assert any("configurations" in v for v in budget.violations(
        with_state(further_families=[fam(1, cfg=4)], total_n=47)))  # fmt: skip
    assert any(
        "market runs" in v
        for v in budget.violations(with_state(further_families=[fam(1, runs=2)], total_n=46))
    )
    assert any("exceeds the cap" in v for v in budget.violations(with_state(total_n=53)))
    assert any("inconsistent" in v for v in budget.violations(with_state(total_n=44)))
    assert any(
        "duplicate" in v
        for v in budget.violations(with_state(further_families=[fam(1), fam(1)], total_n=49))
    )
    assert any(
        "status" in v
        for v in budget.violations(with_state(further_families=[fam(1, status="x")], total_n=46))
    )


def test_stop_rule_after_two_consecutive_rejections():
    assert budget.violations(with_state(consecutive_rejected_under_v2=1)) == []
    v = budget.violations(with_state(consecutive_rejected_under_v2=2))
    assert any("stop rule" in x for x in v)
    ok, why = budget.can_start_run(with_state(consecutive_rejected_under_v2=2), "F1")
    assert not ok and "stop rule" in why


def test_a_run_cannot_start_without_a_preregistered_family_or_after_its_one_run():
    ok, why = budget.can_start_run(B, "F1", new_configurations=3)
    assert not ok and "not registered" in why
    b = with_state(further_families=[fam(1)], total_n=46)
    assert budget.can_start_run(b, "F1") == (True, "ok")
    used = with_state(further_families=[fam(1, runs=1, status="preregistered")], total_n=46)
    ok, why = budget.can_start_run(used, "F1")
    assert not ok and "market-run cap" in why
    done = with_state(further_families=[fam(1, runs=1, status="evaluated_rejected")], total_n=46)
    assert not budget.can_start_run(done, "F1")[0]
    full = with_state(further_families=[fam(i) for i in range(1, 4)], total_n=52)
    ok, why = budget.can_start_run(full, "F4", new_configurations=3)
    assert not ok and "cap" in why
    too_many = with_state(further_families=[fam(1)], total_n=46)
    assert not budget.can_start_run(too_many, "F2", new_configurations=7)[0]


def test_check_sh_runs_the_budget_check():
    assert "quantlab.budget check" in (Q / "scripts/check.sh").read_text(encoding="utf-8")
