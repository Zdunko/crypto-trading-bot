"""Statistical toolkit: closed-form checks, known orderings, and the guard rails."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from quantlab import stats


RULES = json.loads(
    (Path(__file__).resolve().parents[1] / "protocol" / "protocol_v4_stats.json").read_text()
)


def test_psr_is_one_half_at_the_benchmark_and_grows_with_sample_and_sharpe():
    assert stats.psr(0.1, 500, 0.0, 3.0, 0.1) == pytest.approx(0.5)
    assert stats.psr(0.1, 2000, 0.0, 3.0) > stats.psr(0.1, 500, 0.0, 3.0) > 0.5


def test_expected_max_sharpe_is_zero_for_one_trial_and_increases_with_trials():
    assert stats.expected_max_sharpe(1, 0.01) == 0.0
    vals = [stats.expected_max_sharpe(n, 0.01) for n in (2, 10, 100, 1000)]
    assert vals == sorted(vals) and vals[0] > 0
    # known value: N=100, var 1 -> about 2.5 (Bailey & Lopez de Prado 2014, selection bias)
    assert 2.4 < stats.expected_max_sharpe(100, 1.0) < 2.6


def test_deflated_sharpe_falls_as_the_number_of_trials_grows():
    r = np.random.default_rng(0).normal(0.001, 0.01, 1500)
    d = [stats.deflated_sharpe(r, n)["dsr"] for n in (1, 10, 100)]
    assert d[0] > d[1] > d[2]


def test_min_track_record_and_min_detectable_sharpe_reproduce_the_closed_forms():
    assert stats.min_track_record(0.1, 0.0, 0.0, 3.0) == pytest.approx(
        1 + 1.005 * (1.6449 / 0.1) ** 2, rel=1e-3
    )
    assert math.isinf(stats.min_track_record(0.0, 0.1, 0, 3))
    # 4.5 years of daily data: about 1.17 annualised Sharpe is the smallest detectable effect
    assert stats.min_detectable_sharpe(1642, 365) == pytest.approx(1.17, abs=0.02)


def test_pbo_is_high_for_pure_noise_and_low_when_one_config_truly_dominates():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 0.01, (800, 12))
    assert 0.3 < stats.pbo_cscv(noise)["pbo"] < 0.7
    skill = noise.copy()
    skill[:, 3] += 0.004  # persistent edge in one configuration
    assert stats.pbo_cscv(skill)["pbo"] < 0.1
    assert math.isnan(stats.pbo_cscv(noise[:, :1])["pbo"])


def test_holm_and_benjamini_hochberg_known_example():
    p = [0.01, 0.04, 0.03]
    assert stats.holm(p) == [True, False, False]
    assert stats.benjamini_hochberg(p) == [True, True, True]


def test_credibility_never_calls_an_underpowered_sample_significant():
    rng = np.random.default_rng(2)
    short = rng.normal(0.004, 0.01, 120)  # big edge, but 120 days only
    out = stats.credibility(short, 41, RULES["stat_screen"])
    assert out["verdict"] == "underpowered" and out["mde_sharpe_annualised"] > 1.5


def test_credibility_rejects_noise_even_with_a_long_sample_and_many_trials():
    r = np.random.default_rng(3).normal(0.0002, 0.01, 6000)  # ~16 years, tiny edge
    assert stats.credibility(r, 41, RULES["stat_screen"])["verdict"] in (
        "not_credible",
        "underpowered",
    )
    assert (
        stats.credibility(np.zeros(100), 41, RULES["stat_screen"])["verdict"] == "insufficient_data"
    )


def test_pre_registered_levels_are_the_documented_ones():
    s = RULES["stat_screen"]
    assert (s["alpha"], s["power"], s["min_dsr"], s["max_pbo"]) == (0.05, 0.8, 0.95, 0.25)
    assert RULES["levels"]["bootstrap_ci"] == 0.95
