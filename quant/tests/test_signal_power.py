"""S9: stored synthetic power results pin the numbers quoted in the S9 documents; the ranking is recomputed from the
pre-registered rubric; the evidence ladder cannot imply a higher level. No market data is used anywhere."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from quantlab import signal_power as sp


Q = Path(__file__).resolve().parents[1]
R = json.loads((Q / "docs/phase4c/s9_signal_power_results.json").read_text(encoding="utf-8"))
C = json.loads((Q / "docs/phase4c/s9_criteria.json").read_text(encoding="utf-8"))
S = json.loads((Q / "docs/phase4c/s9_selection.json").read_text(encoding="utf-8"))
LAD = json.loads((Q / "protocol/evidence_ladder_v1.json").read_text(encoding="utf-8"))
P = R["power_by_scenario_assets_ic"]


def test_size_at_zero_skill_is_near_nominal_in_every_scenario_and_n():
    for s in sp.SCENARIOS:
        for n in C["power_study"]["assets"]:
            assert 0.02 <= P[f"{s}|N{n}|ic0.0"] <= 0.07, (s, n)


def test_power_rises_with_ic_and_with_assets():
    for s in sp.SCENARIOS:
        for n in (10, 40, 100):
            row = [P[f"{s}|N{n}|ic{ic}"] for ic in (0.005, 0.01, 0.02)]
            assert row == sorted(row)
        for ic in (0.005, 0.01, 0.02):
            col = [P[f"{s}|N{n}|ic{ic}"] for n in (10, 40, 100)]
            assert col == sorted(col)


def test_quoted_power_ranges():
    lo = {
        n: [min(P[f"{s}|N{n}|ic{ic}"] for s in sp.SCENARIOS) for ic in (0.005, 0.01, 0.02)]
        for n in (10, 40, 100)
    }
    assert 0.2 < lo[40][0] < 0.35 and 0.6 < lo[40][1] < 0.72 and lo[40][2] > 0.95
    assert 0.5 < lo[100][0] < 0.6 and lo[100][1] > 0.9
    assert lo[10][0] < 0.15 and lo[10][2] < 0.7  # N = 10 never reaches 0.8 on the grid
    assert R["pessimistic_minimum_detectable_ic_by_n"]["10"].startswith("not reached")
    assert 0.012 < R["pessimistic_minimum_detectable_ic_by_n"]["40"] < 0.016
    assert 0.007 < R["pessimistic_minimum_detectable_ic_by_n"]["100"] < 0.01


def test_regime_dependent_skill_and_vol_clustering_do_not_collapse_power_but_are_not_better_than_baseline_by_much():
    for n in (40, 100):
        base = P[f"baseline_student_t3_noise|N{n}|ic0.01"]
        for s in ("regime_dependent_skill", "volatility_clustering_noise"):
            assert abs(P[f"{s}|N{n}|ic0.01"] - base) < 0.08


def test_break_even_ic_follows_the_pre_registered_formula_and_no_hypothesis_is_powered():
    cfg = C["power_study"]
    for h in S["hypotheses"]:
        expected = 2.0 * h["annual_one_way_turnover_assumption"] * 0.0015 / (1.4 * 0.02 * 365)
        got = R["hypotheses"][h["id"]]["break_even_ic"]
        assert (
            abs(got - expected) < 1e-12
            and abs(sp.break_even_ic(h["annual_one_way_turnover_assumption"], cfg) - expected)
            < 1e-12
        )
        assert R["hypotheses"][h["id"]]["powered_at_break_even_ic_n40"] is False
        assert (
            got < R["pessimistic_minimum_detectable_ic_by_n"]["100"]
        )  # break-even is below the detectable effect


def test_ranking_is_recomputed_from_the_pre_registered_rubric():
    rub = C["selection_rubric"]
    assert abs(sum(rub["criteria"].values()) - 1.0) < 1e-12
    rank = sp.ranking(rub, S)
    assert [r["id"] for r in rank] == ["H1", "H3", "H2"] == [r["id"] for r in R["ranking"]]
    assert rank[0]["score"] == 3.55 and rank[1]["score"] == 3.35 and rank[2]["score"] == 3.15
    assert len(S["hypotheses"]) == C["hypotheses"]["count"] == 3
    assert all(len(h["free_parameters"]) <= 1 for h in S["hypotheses"])
    assert all(1 <= v <= 5 for h in S["hypotheses"] for v in h["scores"].values())


def test_evidence_ladder_levels_are_ordered_and_never_imply_a_higher_level():
    ids = [lv["level"] for lv in LAD["levels"]]
    assert ids == ["L1", "L2", "L3", "L4", "L5"]
    for lv in LAD["levels"][:4]:
        for f in C["evidence_ladder"]["required_fields_per_level"]:
            assert lv[f], (lv["level"], f)
        assert (
            "not" in lv["what_passing_does_not_mean"].lower()
            or "nothing" in lv["what_passing_does_not_mean"].lower()
        )
    assert "unreachable" in LAD["levels"][4]["rejection_criteria"]
    rules = " ".join(LAD["non_implication_rules"])
    assert "T1-T10" in rules and "never reclassified" in rules and "holdout" in rules


def test_reduced_rerun_is_deterministic():
    cfg = dict(C["power_study"], replications=4, days=200)
    a = sp.power_cell("regime_dependent_skill", 10, 0.01, cfg, np.random.default_rng(1), chunk=2)
    b = sp.power_cell("regime_dependent_skill", 10, 0.01, cfg, np.random.default_rng(1), chunk=2)
    assert a == b
    s1 = sp.ic_series("baseline_student_t3_noise", 10, 0.0, 2, 50, np.random.default_rng(2), cfg)
    assert s1.shape == (2, 50) and np.all(np.abs(s1) <= 1.0)
