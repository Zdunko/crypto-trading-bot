"""S8 design study: stored results pin every verdict-bearing number of the S8 documents; reduced re-runs are
deterministic. Synthetic simulation only: the numbers describe statistical methods, not any market or strategy."""

from __future__ import annotations

import json
import math
from itertools import pairwise
from pathlib import Path
from statistics import NormalDist

import numpy as np

from quantlab import design_study as ds


Q = Path(__file__).resolve().parents[1]
R = json.loads((Q / "docs/phase4c/s8_design_study_results.json").read_text(encoding="utf-8"))
C = json.loads((Q / "docs/phase4c/s8_criteria.json").read_text(encoding="utf-8"))
D1 = R["d1_size_and_power"]
SIZE_LIMIT = 0.07
TARGET = C["simulation_fixed_parameters"]["target_power"]


def test_criteria_are_the_inputs_of_the_study():
    p = C["simulation_fixed_parameters"]
    assert (
        p["n_days_primary"] == ds.N_DAYS
        and tuple(p["annualised_information_ratios_grid"]) == ds.IR_GRID
    )
    assert tuple(p["dgp"]) == ds.DGPS and p["replications_per_cell"] == 400
    assert C["scope"].count("no holdout access") == 1 and R["synthetic_only"] is True


def test_naive_power_matches_the_analytic_value_and_is_far_from_target_at_ir_half():
    """Self-check of the study: simulated iid power at IR 1.0 equals Phi(IR*sqrt(years)-z), within MC error."""
    years = ds.N_DAYS / ds.DAYS
    norm = NormalDist()
    for ir in (0.5, 1.0):
        analytic = norm.cdf(ir * math.sqrt(years) - ds.Z95)
        sim = D1[f"iid_normal|ir{ir}"]["newey_west_lag10"]
        assert abs(sim - analytic) < 0.06
    for k, v in D1.items():
        if k.endswith("|ir0.5"):
            assert all(x < 0.4 for x in v.values()), (
                k
            )  # no inference method reaches 80 % at IR 0.5 on 4.5 years


def test_size_verdicts_pre_registered_limit():
    """Criterion (1): size <= 0.07 under every DGP. Newey-West and the L10 block bootstrap pass, naive/L20/L40 do not
    pass on iid (Monte-Carlo se ~0.011); the study reports it as found."""
    nw = [v["newey_west_lag10"] for k, v in D1.items() if k.endswith("|ir0.0")]
    assert max(nw) <= SIZE_LIMIT
    l10 = [v["circular_block_bootstrap_L10"] for k, v in D1.items() if k.endswith("|ir0.0")]
    assert max(l10) <= SIZE_LIMIT
    assert D1["iid_normal|ir0.0"]["circular_block_bootstrap_L20"] > SIZE_LIMIT
    assert (
        D1["ar1_0.15|ir0.0"]["naive_t"] > SIZE_LIMIT
    )  # naive t is over-sized under autocorrelation


def test_return_series_design_effect_is_modest_under_the_preregistered_dgps():
    d = R["d5_years_needed"]["design_effect_measured"]
    assert all(0.9 < v < 1.3 for v in d.values())
    assert d["ar1_0.15"] > d["iid_normal"]


def test_years_needed_for_80_percent_power():
    y = R["d5_years_needed"]["years_needed_80pct"]
    assert 20 < y["iid_normal"]["ir0.5"] < 35 and y["iid_normal"]["ir1.0"] < 8
    p = R["d5_years_needed"]["power_at_history_years"]
    for kind in ds.DGPS:
        assert p[kind]["13.0y|ir0.5"] < TARGET  # even 13 years do not reach target at IR 0.5
        assert p[kind]["4.5y|ir0.5"] < 0.35
    assert (
        p["iid_normal"]["13.0y|ir0.8"] > TARGET
    )  # but they would at IR 0.8 (not the pre-registered claim)


def test_failing_to_reject_is_not_evidence_of_negative_performance():
    d2 = R["d2_negative_vs_underpowered"]
    pos = d2["iid_normal|true_ir0.5"]
    assert (
        pos["p_fail_to_reject_one_sided"] > 0.65
        and pos["p_conclusive_negative_upper95_below_0"] < 0.02
    )
    neg = d2["iid_normal|true_ir-0.5"]
    assert (
        neg["p_conclusive_negative_upper95_below_0"] < 0.4
    )  # even a clearly negative IR is rarely "proven" negative
    assert (
        pos["mean_halfwidth_annual_ir_95"] > 0.7
    )  # the confidence interval spans most plausible IRs


def test_purging_removes_shuffled_cv_leakage_not_a_contiguous_effect():
    d3 = R["d3_purging"]
    assert d3["shuffled_kfold_mean_ic_on_noise"] > 10 * d3["shuffled_kfold_ic_se"]
    assert (
        abs(
            d3["contiguous_purged_embargoed_mean_ic_on_noise"]
            - d3["contiguous_unpurged_mean_ic_on_noise"]
        )
        < 4 * d3["contiguous_purged_embargoed_ic_se"]
    )
    assert 0 < d3["purged_fraction_of_train_removed"] < 0.05


def test_more_assets_do_not_make_independent_observations_for_absolute_claims():
    for k, v in R["d4_cross_section"].items():
        assert v["effective_independent_assets_equal_weight_portfolio"] < 2.0, k
        assert v["average_pairwise_return_correlation"] > 0.5, k


def test_breadth_helps_relative_claims_through_the_achievable_ir_not_through_independence():
    d4 = R["d4_cross_section"]
    pw = [d4[f"N{n}|extra_rho0.0|ic0.01"]["power_or_size_ic_test"] for n in (5, 20, 40, 100)]
    ir = [
        d4[f"N{n}|extra_rho0.0|ic0.01"]["mean_annual_active_ir_top_quintile_vs_equal_weight"]
        for n in (5, 20, 40, 100)
    ]
    assert all(a < b for a, b in pairwise(pw)) and all(a < b for a, b in pairwise(ir))
    # power of the tradable (long-only active return) test follows the IR it delivers, like any other test
    norm = NormalDist()
    for n in (20, 40, 100):
        cell = d4[f"N{n}|extra_rho0.0|ic0.01"]
        analytic = norm.cdf(
            cell["mean_annual_active_ir_top_quintile_vs_equal_weight"] * math.sqrt(4.5) - ds.Z95
        )
        assert abs(cell["power_or_size_top_quintile_active_return"] - analytic) < 0.12
    # size of both cross-sectional tests at zero skill stays near nominal
    for k, v in d4.items():
        if k.endswith("|ic0.0"):
            assert (
                v["power_or_size_ic_test"] < 0.09
                and v["power_or_size_top_quintile_active_return"] < 0.09
            ), k


def test_selection_bias_and_holm():
    d6 = R["d6_selection"]
    assert (
        d6["n43"]["mean_best_in_sample_annual_sharpe"] > 0.9
        and d6["n43"]["p_best_unadjusted_significant"] > 0.8
    )
    assert abs(d6["n43"]["mean_out_of_sample_sharpe_of_selected"]) < 0.05
    for m in ("n5", "n15", "n43"):
        assert d6[m]["p_best_holm_or_bonferroni_significant"] < 0.07


def test_reduced_reruns_are_deterministic_and_match_the_stored_results():
    a = ds.d6_selection(2000, C["simulation_fixed_parameters"]["seeds"]["d6"], (1, 5, 15, 43))
    assert a == ds.d6_selection(
        2000, C["simulation_fixed_parameters"]["seeds"]["d6"], (1, 5, 15, 43)
    )
    assert a == R["d6_selection"]
    x = ds.gen("ar1_0.15", np.random.default_rng(3), 4, 300, 0.0)
    y = ds.gen("ar1_0.15", np.random.default_rng(3), 4, 300, 0.0)
    assert np.array_equal(x, y)
    p1 = ds.block_boot_p(x, np.random.default_rng(5), 20, 99)
    assert np.array_equal(p1, ds.block_boot_p(x, np.random.default_rng(5), 20, 99))
