"""S7 methodology audit: stored results pin every claim of the audit document; reduced re-runs are deterministic.
Synthetic simulation only: these numbers describe the gate's formulas, not any market."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

from quantlab import gate_audit as ga


Q = Path(__file__).resolve().parents[1]
R = json.loads((Q / "docs/phase4c/s7_gate_audit_results.json").read_text(encoding="utf-8"))


def test_q1_active_day_basis_is_coherent_but_power_scales_with_exposure():
    q = R["q1_exposure"]
    m = [
        q["mde_active_sharpe_by_share"][k]
        for k in ("0.1", "0.2", "0.4", "0.6", "0.8", "0.9", "1.0")
    ]
    assert all(a > b for a, b in pairwise(m)) and m[0] > 3 and m[-1] < 1.3
    for v in q["power_at_active_sharpe_1"].values():
        assert (
            abs(v["power_active_days"] - v["power_calendar_series"]) < 0.02
        )  # same test, same power
    p = q["power_at_active_sharpe_1"]
    assert p["0.9"]["power_active_days"] > p["0.2"]["power_active_days"] + 0.3


def test_q2_q3_kish_formula_understates_dependence_of_overlapping_episodes():
    for tag in ("q2_overlapping_holdings", "q3_regime_means"):
        r = R[tag]
        for d in ("1", "5", "20"):
            assert r[d]["deff_true"] > r[d]["deff_gate_formula"]
        assert r["20"]["deff_true"] > 5 * r["20"]["deff_gate_formula"]
        assert r["20"]["effective_true"] < r["20"]["effective_gate"] / 5
    assert R["q3_regime_means"]["1"]["deff_true"] > R["q2_overlapping_holdings"]["1"]["deff_true"]


def test_q4_normal_mde_is_approximately_right_for_daily_returns():
    for k, v in R["q4_mde_validity"].items():
        assert v["size_naive"] <= 0.10 and v["size_newey_west"] <= 0.10, k
        assert 0.65 <= v["power_naive_at_mde"] <= 0.9, k
    assert (
        R["q4_mde_validity"]["n500_iid_normal"]["mde_annual_sharpe"] > 2.0
    )  # duration, not distribution, is the limit


def test_q5_timing_null_has_power_at_low_exposure_too():
    q = R["q5_defensive_timing_power"]
    assert (
        q["base0.2_kappa0.05"]["rejection_rate"] >= 0.95
        and q["base0.9_kappa0.05"]["rejection_rate"] >= 0.95
    )
    assert (
        q["base0.2_kappa0.0"]["rejection_rate"] <= 0.12
        and q["base0.9_kappa0.0"]["rejection_rate"] <= 0.12
    )
    assert (
        abs(q["base0.2_kappa0.02"]["rejection_rate"] - q["base0.9_kappa0.02"]["rejection_rate"])
        < 0.2
    )


def test_q6_frozen_risk_layer_cuts_exposure_far_below_the_declared_share():
    for v in R["q6_exposure_after_frozen_risk_layer"].values():
        assert v["invested_day_share_mean"] < 0.75 and v["share_of_paths_shut_down"] >= 0.4
    b2 = R["b2_draft_under_realistic_exposure"]
    assert b2["declared_0.90_1.00"]["passes_mde_criterion"]
    assert not any(v["passes_mde_criterion"] for k, v in b2.items() if k != "declared_0.90_1.00")


def test_q7_comparison_machinery_is_conservative_under_a_true_null():
    q = R["q7_benchmark_comparisons"]
    assert q["size_vs_plain_benchmark"] <= 0.05 and q["size_vs_best_of_5"] <= 0.05
    assert (
        q["no_skill_paths_meeting_drawdown_and_beating_cash_mix"]
        <= q["no_skill_paths_meeting_20pct_drawdown"]
        <= 0.1
    )


def test_reduced_reruns_are_deterministic_and_agree_in_direction():
    assert ga.q1_exposure_bias(reps=40, seed=3) == ga.q1_exposure_bias(reps=40, seed=3)
    q2 = ga.q2_design_effect(reps=20, seed=5, durations=(1, 20))
    assert q2["20"]["deff_true"] > 2 * q2["20"]["deff_gate_formula"]
    q6 = ga.q6_exposure_after_risk_layer(paths=4, seed=9)
    assert all(0.0 <= v["invested_day_share_mean"] <= 1.0 for v in q6.values())
    assert ga.q6_exposure_after_risk_layer(paths=4, seed=9) == q6
