"""M5 design validation (SYNTHETIC only): can a volatility-controlled test tell a genuine incremental MAX3 effect from a
pure volatility effect?

Data-generating process: every asset carries a persistent volatility characteristic v (AR(1)) and a persistent MAX3-specific
characteristic eta (AR(1)). The MAX3-like score is m = RHO * v + sqrt(1 - RHO^2) * eta, so its cross-sectional correlation with
volatility equals the value observed in M3 (0.913). Expected returns fall with v (a low-volatility premium of size A_V, present
in EVERY scenario) and with eta (the incremental effect of size a_m; zero under the null). The tested signal is S = -m
(higher = less lottery-like), as in H1.

Two tests are compared on the same data, with the registered statistic (mean of the daily cross-sectional correlation, Newey-West
lag 2h, one-sided 5 %): the NAIVE IC of S, and the PARTIAL IC of S controlling for v
(rho_SR.V = (r_SR - r_SV r_VR) / sqrt((1 - r_SV^2)(1 - r_VR^2))). Under a_m = 0 the naive test should reject (the volatility premium
passes through S) while the partial test must keep its size. Writes ``docs/phase4c/m5_incremental_power_results.json``
(byte-reproducible). Nothing here touches market data."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

from quantlab.gate_audit import _hac_t


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase4c" / "m5_incremental_power_results.json"
Z95 = NormalDist().inv_cdf(0.95)
SEED, DAYS, REPS, N_ASSETS = 20261201, 1642, 400, 115
RHO = 0.913  # M3: mean daily rank correlation between S and trailing volatility (absolute value)
PHI_V, PHI_E = (
    0.98,
    0.95,
)  # persistence of the volatility characteristic and of the MAX3-specific part (assumptions)
A_V = 0.025  # volatility premium loading: daily IC of -v about 0.02 (an assumption of the order of the M3 effect)
A_M_GRID = (0.0, 0.005, 0.01, 0.02)
SD_E, SD_F, SD_G, K = 0.02, 0.025, 0.01, 5
HORIZONS = (7, 28)


def _rowcorr(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = a - a.mean(axis=-1, keepdims=True), b - b.mean(axis=-1, keepdims=True)
    return (a * b).sum(-1) / np.sqrt((a * a).sum(-1) * (b * b).sum(-1))


def _ar1(reps: int, t_n: int, n: int, phi: float, rng: np.random.Generator) -> np.ndarray:
    x = np.empty((reps, t_n, n))
    x[:, 0] = rng.normal(0, 1, (reps, n))
    eps = rng.normal(0, 1, (reps, t_n, n)) * math.sqrt(1 - phi**2)
    for i in range(1, t_n):
        x[:, i] = phi * x[:, i - 1] + eps[:, i]
    return x


def chunk(a_m: float, h: int, reps: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    t_n = DAYS + h + 1
    sector = np.arange(N_ASSETS) % K
    v = _ar1(reps, t_n, N_ASSETS, PHI_V, rng)
    eta = _ar1(reps, t_n, N_ASSETS, PHI_E, rng)
    m = RHO * v + math.sqrt(1 - RHO**2) * eta
    f = rng.normal(0, SD_F, (reps, t_n, 1))
    g = rng.normal(0, SD_G, (reps, t_n, K))[:, :, sector]
    u = rng.standard_t(3, (reps, t_n, N_ASSETS)) / math.sqrt(3)
    r = np.zeros((reps, t_n, N_ASSETS))
    r[:, 1:] = f[:, 1:] + g[:, 1:] + SD_E * (u[:, 1:] - A_V * v[:, :-1] - a_m * eta[:, :-1])
    cum = np.cumsum(r, axis=1)
    fwd = cum[:, h + 1 : DAYS + h + 1] - cum[:, 1 : DAYS + 1]
    s, vv = -m[:, :DAYS], v[:, :DAYS]
    r_sr, r_sv, r_vr = _rowcorr(s, fwd), _rowcorr(s, vv), _rowcorr(vv, fwd)
    partial = (r_sr - r_sv * r_vr) / np.sqrt((1 - r_sv**2) * (1 - r_vr**2))
    daily = _rowcorr(s, r[:, 1 : DAYS + 1])
    vol_only = _rowcorr(-vv, fwd)
    return {
        "naive": r_sr,
        "partial": partial,
        "daily_naive": daily,
        "vol_only": vol_only,
        "corr_sv": r_sv,
    }


def run_all() -> dict:
    rng = np.random.default_rng(SEED)
    cells: dict = {}
    for h in HORIZONS:
        for a_m in A_M_GRID:
            rej_n = rej_p = 0
            mean_n, mean_p, mean_d, mean_v, mean_c = [], [], [], [], []
            for _ in range(REPS // 20):
                c = chunk(a_m, h, 20, rng)
                rej_n += int(np.sum(_hac_t(c["naive"], lag=2 * h) > Z95))
                rej_p += int(np.sum(_hac_t(c["partial"], lag=2 * h) > Z95))
                mean_n.append(c["naive"].mean(axis=1))
                mean_p.append(c["partial"].mean(axis=1))
                mean_d.append(c["daily_naive"].mean(axis=1))
                mean_v.append(c["vol_only"].mean(axis=1))
                mean_c.append(c["corr_sv"].mean(axis=1))
            cells[f"h{h}|a_m{a_m}"] = {
                "naive_ic_rejection_rate": rej_n / REPS,
                "partial_ic_rejection_rate": rej_p / REPS,
                "mean_naive_ic_h": float(np.concatenate(mean_n).mean()),
                "mean_partial_ic_h": float(np.concatenate(mean_p).mean()),
                "mean_naive_daily_ic": float(np.concatenate(mean_d).mean()),
                "mean_volatility_only_ic_h": float(np.concatenate(mean_v).mean()),
                "mean_corr_signal_volatility": float(np.concatenate(mean_c).mean()),
            }
    return {"synthetic_only": True, "days": DAYS, "reps": REPS, "assets": N_ASSETS, "rho": RHO, "phi_v": PHI_V, "phi_eta": PHI_E, "a_v": A_V,
            "a_m_grid": list(A_M_GRID), "hac_lag": "2h", "cells": cells}  # fmt: skip


def main() -> None:
    OUT.write_text(json.dumps(run_all(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
