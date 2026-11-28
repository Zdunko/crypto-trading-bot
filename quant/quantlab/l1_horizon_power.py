"""M2: do the S9 power estimates (1-day IC) transfer to the registered 7- and 28-day horizons?

Synthetic only. Assets carry a persistent characteristic q (AR(1), daily persistence PHI) that shifts expected
returns: r[t+1] = f + sector + sigma*(u + a*q[t]). The signal is q[t]; the statistic is the cross-sectional Pearson IC
between q[t] and the overlapping h-day forward return, tested with the registered Newey-West lag 2h.
The per-day-equivalent IC reported is the REALISED mean of the 1-day IC of the same data, so results are comparable
to ``s9_signal_power_results.json``. Writes ``docs/phase4c/m2_horizon_power_results.json`` (byte-reproducible)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

from quantlab.gate_audit import _hac_t


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase4c" / "m2_horizon_power_results.json"
Z95 = NormalDist().inv_cdf(0.95)
SEED, DAYS, REPS = 20261129, 1642, 400
PHIS = (
    0.9,
    0.97,
)  # daily persistence of the signal; the real value is unknown (assumption, both reported)
SD_E, SD_F, SD_G, K = 0.02, 0.025, 0.01, 5
A_GRID = (0.0, 0.01, 0.02, 0.04)  # skill loading a; realised daily IC is measured, not assumed
SCENARIOS = ("baseline_student_t3_noise", "regime_dependent_skill")


def _rowcorr(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = a - a.mean(axis=-1, keepdims=True), b - b.mean(axis=-1, keepdims=True)
    return (a * b).sum(-1) / np.sqrt((a * a).sum(-1) * (b * b).sum(-1))


def chunk(
    scn: str, n_assets: int, a: float, h: int, reps: int, rng: np.random.Generator, phi: float = 0.9
) -> tuple[np.ndarray, np.ndarray]:
    """(IC_h series reps x T, daily IC_1 series reps x T) for one chunk of replications."""
    t_n = DAYS + h + 1
    sector = np.arange(n_assets) % K
    f = rng.normal(0, SD_F, (reps, t_n, 1))
    g = rng.normal(0, SD_G, (reps, t_n, K))[:, :, sector]
    u = (
        rng.standard_t(3, (reps, t_n, n_assets)) / math.sqrt(3)
        if scn == "baseline_student_t3_noise"
        else rng.normal(0, 1, (reps, t_n, n_assets))
    )
    q = np.empty((reps, t_n, n_assets))
    q[:, 0] = rng.normal(0, 1, (reps, n_assets))
    eps = rng.normal(0, 1, (reps, t_n, n_assets)) * math.sqrt(1 - phi**2)
    for i in range(1, t_n):
        q[:, i] = phi * q[:, i - 1] + eps[:, i]
    if scn == "regime_dependent_skill":
        flips = rng.random((reps, t_n)) > 0.99
        state = np.empty((reps, t_n))
        state[:, 0] = (rng.random(reps) < 0.5).astype(float)
        for i in range(1, t_n):
            state[:, i] = np.where(flips[:, i], 1.0 - state[:, i - 1], state[:, i - 1])
        loading = (2.0 * a * state)[:, :, None]
    else:
        loading = np.full((reps, t_n, 1), a)
    r = np.zeros((reps, t_n, n_assets))
    r[:, 1:] = f[:, 1:] + g[:, 1:] + SD_E * (u[:, 1:] + loading[:, :-1] * q[:, :-1])
    cum = np.cumsum(r, axis=1)
    ic_h = _rowcorr(q[:, :DAYS], cum[:, h + 1 : DAYS + h + 1] - cum[:, 1 : DAYS + 1])
    ic_1 = _rowcorr(q[:, :DAYS], r[:, 1 : DAYS + 1])
    return ic_h, ic_1


def run_all() -> dict:
    rng = np.random.default_rng(SEED)
    out: dict = {
        "synthetic_only": True,
        "days": DAYS,
        "reps": REPS,
        "signal_persistence_grid": list(PHIS),
        "hac_lag": "2h",
        "cells": {},
    }
    for scn in SCENARIOS:
        for phi in PHIS:
            for n_assets in (40, 100):
                for h in (7, 28):
                    for a in A_GRID:
                        rej, ic1_means, ich_means = 0, [], []
                        for _ in range(REPS // 20):
                            ic_h, ic_1 = chunk(scn, n_assets, a, h, 20, rng, phi)
                            rej += int(np.sum(_hac_t(ic_h, lag=2 * h) > Z95))
                            ic1_means.append(ic_1.mean(axis=1))
                            ich_means.append(ic_h.mean(axis=1))
                        out["cells"][f"{scn}|phi{phi}|N{n_assets}|h{h}|a{a}"] = {
                            "power_or_size": rej / REPS,
                            "realised_daily_ic": float(np.concatenate(ic1_means).mean()),
                            "realised_mean_ic_h": float(np.concatenate(ich_means).mean()),
                        }
    return out


def main() -> None:
    OUT.write_text(json.dumps(run_all(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
