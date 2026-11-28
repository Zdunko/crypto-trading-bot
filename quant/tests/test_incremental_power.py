"""M5 design validation: stored synthetic results pin the claims of the proposal (naive IC test cannot tell volatility from
MAX3, the partial-IC test keeps its size and has power). Synthetic only."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import numpy as np

from quantlab import incremental_power as ip


Q = Path(__file__).resolve().parents[1]
R = json.loads((Q / "docs/phase4c/m5_incremental_power_results.json").read_text(encoding="utf-8"))
C = R["cells"]


def mde(h: int) -> float:
    xs = sorted(
        (C[f"h{h}|a_m{a}"]["mean_partial_ic_h"], C[f"h{h}|a_m{a}"]["partial_ic_rejection_rate"])
        for a in ip.A_M_GRID
    )
    for (x0, p0), (x1, p1) in pairwise(xs):
        if p0 < 0.8 <= p1:
            return x0 + (0.8 - p0) * (x1 - x0) / (p1 - p0)
    raise AssertionError("80 % power not reached on the grid")


def test_the_naive_test_cannot_separate_volatility_from_an_incremental_effect():
    for h in (7, 28):
        null = C[f"h{h}|a_m0.0"]
        assert (
            null["naive_ic_rejection_rate"] > 0.95
        )  # rejects although MAX3 has no incremental content
        assert (
            null["mean_volatility_only_ic_h"] > 0.04
            and abs(null["mean_corr_signal_volatility"] + 0.912) < 0.01
        )


def test_the_partial_test_keeps_its_size_and_has_power():
    for h in (7, 28):
        null = C[f"h{h}|a_m0.0"]
        assert abs(null["mean_partial_ic_h"]) < 0.002 and null["partial_ic_rejection_rate"] < 0.10
        rates = [C[f"h{h}|a_m{a}"]["partial_ic_rejection_rate"] for a in ip.A_M_GRID]
        assert rates == sorted(rates) and rates[-1] == 1.0
    assert 0.011 < mde(7) < 0.016 and 0.020 < mde(28) < 0.026  # quoted in the proposal
    assert mde(7) > 0.003522504892367907 * np.sqrt(7) and mde(28) > 0.003522504892367907 * np.sqrt(
        28
    )  # powered for ~1.2-1.5x the threshold


def test_the_h7_size_slightly_exceeds_the_s9_limit_and_is_reported_as_such():
    assert (
        C["h7|a_m0.0"]["partial_ic_rejection_rate"] > 0.07
        and C["h28|a_m0.0"]["partial_ic_rejection_rate"] < 0.08
    )
    text = (Q / "docs/phase4c/m5_incremental_value_proposal.md").read_text(encoding="utf-8")
    assert "slightly exceeds the 0.07 size limit" in text


def test_reduced_rerun_is_deterministic():
    a = ip.chunk(0.01, 7, 2, np.random.default_rng(3))
    b = ip.chunk(0.01, 7, 2, np.random.default_rng(3))
    assert all(np.array_equal(a[k], b[k]) for k in a)
