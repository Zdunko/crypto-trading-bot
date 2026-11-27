"""M2: pins the horizon-power numbers quoted in the M2 report; reduced rerun is deterministic. Synthetic only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from quantlab import l1_horizon_power as hp


Q = Path(__file__).resolve().parents[1]
C = json.loads((Q / "docs/phase4c/m2_horizon_power_results.json").read_text(encoding="utf-8"))[
    "cells"
]
S9 = json.loads((Q / "docs/phase4c/s9_signal_power_results.json").read_text(encoding="utf-8"))[
    "power_by_scenario_assets_ic"
]


def cell(scn, phi, n, h, a):
    return C[f"{scn}|phi{phi}|N{n}|h{h}|a{a}"]


def test_size_is_near_nominal_but_mildly_inflated_at_h28():
    sizes7 = [v["power_or_size"] for k, v in C.items() if "|h7|" in k and k.endswith("|a0.0")]
    sizes28 = [v["power_or_size"] for k, v in C.items() if "|h28|" in k and k.endswith("|a0.0")]
    assert max(sizes7) < 0.085 and max(sizes28) < 0.10 and min(sizes7 + sizes28) > 0.03
    assert max(sizes28) > 0.07  # reported as a discrepancy with the S9 size limit


def test_s9_power_transfers_to_h7_but_is_optimistic_for_h28_at_low_persistence():
    s9_n40 = min(
        S9["baseline_student_t3_noise|N40|ic0.01"], S9["regime_dependent_skill|N40|ic0.01"]
    )
    base7 = cell("baseline_student_t3_noise", 0.9, 40, 7, 0.01)["power_or_size"]
    base28 = cell("baseline_student_t3_noise", 0.9, 40, 28, 0.01)["power_or_size"]
    assert abs(base7 - s9_n40) < 0.15 and base28 < s9_n40 - 0.25
    assert (
        cell("baseline_student_t3_noise", 0.97, 40, 28, 0.01)["power_or_size"] > base28 + 0.2
    )  # persistence matters
    assert cell("baseline_student_t3_noise", 0.9, 100, 28, 0.01)["power_or_size"] < 0.6


def test_realised_daily_ic_is_comparable_and_ic_h_scales_below_sqrt_h():
    for k, v in C.items():
        if k.endswith("|a0.01"):
            h = int(k.split("|h")[1].split("|")[0])
            assert 0.008 < v["realised_daily_ic"] < 0.011
            assert 1.2 < v["realised_mean_ic_h"] / v["realised_daily_ic"] < np.sqrt(h)


def test_reduced_rerun_is_deterministic():
    a = hp.chunk("baseline_student_t3_noise", 20, 0.02, 7, 2, np.random.default_rng(3), 0.9)
    b = hp.chunk("baseline_student_t3_noise", 20, 0.02, 7, 2, np.random.default_rng(3), 0.9)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
