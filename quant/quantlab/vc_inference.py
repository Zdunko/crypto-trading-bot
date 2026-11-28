"""M5 Phase 1: inference for the volatility-controlled (partial) rank IC, and its SYNTHETIC calibration.

The registered statistic is the mean over signal days of the daily cross-sectional partial correlation of the signal with the
h-day forward return controlling for the volatility rank. This module holds (a) the finite menu of inference methods declared in
``protocol/m5_calibration_protocol.json`` (M0-M4), (b) the synthetic data-generating process of the five declared scenarios, and
(c) the calibration / validation / power / surrogate steps of that protocol. Nothing here reads market data.

    python -m quantlab.vc_inference calibrate | validate | power | surrogates
"""

from __future__ import annotations

import json
import math
import sys
from itertools import pairwise
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np

from quantlab.design_study import block_boot_p


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocol" / "m5_calibration_protocol.json"
PROTOCOL2 = ROOT / "protocol" / "m5_calibration_protocol_round2.json"
OUT = ROOT / "docs" / "phase4c" / "m5_calibration_results.json"
OUT2 = ROOT / "docs" / "phase4c" / "m5_calibration_round2_results.json"
Z95 = NormalDist().inv_cdf(0.95)
DAYS, N_ASSETS, RHO, A_V = 1642, 115, 0.913, 0.025
SD_E, SD_F, SD_G, K = 0.02, 0.025, 0.01, 5
SCENARIOS = {
    "S1_baseline": {"phi_v": 0.98, "phi_e": 0.95, "cluster": False, "regime": False},
    "S2_high_persistence": {"phi_v": 0.99, "phi_e": 0.99, "cluster": False, "regime": False},
    "S3_low_persistence": {"phi_v": 0.95, "phi_e": 0.90, "cluster": False, "regime": False},
    "S4_volatility_clustering": {"phi_v": 0.98, "phi_e": 0.95, "cluster": True, "regime": False},
    "S5_regime_dependent_premium": {"phi_v": 0.98, "phi_e": 0.95, "cluster": False, "regime": True},
}
METHODS = ("M0", "M1", "M2", "M3", "M4")
ROUND2_METHODS = ("M0", "M1", "M5", "M6", "M7", "M8")
HORIZONS = (7, 28)
SIZE_TOL = 0.07
A_REF = 0.01


# --------------------------------------------------------------------------------------------- inference menu
def lag_for(method: str, h: int) -> int:
    if method == "M0":
        return 2 * h
    if method == "M2":
        return max(4 * h, 90)
    return max(2 * h, 60)  # M1, M3-M8


def nw(x: np.ndarray, lag: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Row-wise (mean, Newey-West Bartlett standard error of the mean, naive standard error) of x (rows x n)."""
    n = x.shape[1]
    d = x - x.mean(axis=1, keepdims=True)
    var = (d * d).mean(axis=1)
    lr = var.copy()
    for k in range(1, lag + 1):
        lr += 2.0 * (1.0 - k / (lag + 1)) * (d[:, k:] * d[:, :-k]).mean(axis=1)
    lr = np.maximum(lr, 1e-300)
    return x.mean(axis=1), np.sqrt(lr / n), np.sqrt(np.maximum(var, 1e-300) / n)


def t_quantile(p: float, df: np.ndarray) -> np.ndarray:
    """Cornish-Fisher expansion of the Student-t quantile (accurate for df >= 5)."""
    z = NormalDist().inv_cdf(p)
    return z + (z**3 + z) / (4.0 * df) + (5 * z**5 + 16 * z**3 + 3 * z) / (96.0 * df**2)


def batch_means(x: np.ndarray, block: int) -> tuple[np.ndarray, np.ndarray, int]:
    """(mean of block means, standard error from the spread of the block means, number of blocks) for rows of x."""
    nb = x.shape[1] // block
    bm = x[:, : nb * block].reshape(x.shape[0], nb, block).mean(axis=2)
    return bm.mean(axis=1), bm.std(axis=1, ddof=1) / math.sqrt(nb), nb


def infer(
    method: str, x: np.ndarray, h: int, rng: np.random.Generator | None = None, draws: int = 999
) -> dict:
    """Row-wise test of mean(x) > 0 at one-sided 5 %. Returns arrays: mean (on the scale of x), se, t, crit, reject, n_eff, plus
    ``tf`` (the transformed scale used by Fisher-z methods) so confidence limits can be mapped back."""
    n = x.shape[1]
    lag = lag_for(method, h)
    fisher = method in ("M7", "M8")
    y = np.arctanh(np.clip(x, -0.999999, 0.999999)) if fisher else x
    if method in ("M6", "M8"):
        mean_b, se, nb = batch_means(y, lag)
        t = mean_b / se
        crit = np.full(len(t), float(t_quantile(0.95, np.array(float(nb - 1)))))
        mean = mean_b
        n_eff = np.full(len(t), float(nb))
        p = np.full(len(t), np.nan)
        reject = t > crit
    else:
        mean, se, naive = nw(y, lag)
        t = mean / se
        n_eff = n * (naive / se) ** 2
        if method == "M3":
            crit = t_quantile(0.95, np.maximum(5.0, np.floor(n_eff) - 1.0))
        elif method == "M5":
            crit = np.full(len(t), float(t_quantile(0.95, np.array(float(max(5, n // lag - 1))))))
        else:
            crit = np.full(len(t), Z95)
        if method == "M4":
            if rng is None:
                raise ValueError("the bootstrap method needs a random generator")
            p = block_boot_p(x, rng, lag, draws)
            reject = p <= 0.05
        else:
            p = np.full(len(t), np.nan)
            reject = t > crit
    return {
        "mean": mean,
        "se": se,
        "t": t,
        "crit": crit,
        "p": p,
        "reject": reject,
        "n_eff": n_eff,
        "lag": lag,
        "fisher": fisher,
    }


# --------------------------------------------------------------------------------------------- synthetic DGP
def _rowcorr(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = a - a.mean(axis=-1, keepdims=True), b - b.mean(axis=-1, keepdims=True)
    return (a * b).sum(-1) / np.sqrt((a * a).sum(-1) * (b * b).sum(-1))


def _ar1(
    reps: int, t_n: int, n: int, phi: float, rng: np.random.Generator, sd: float = 1.0
) -> np.ndarray:
    x = np.empty((reps, t_n, n))
    x[:, 0] = rng.normal(0, sd, (reps, n))
    eps = rng.normal(0, sd, (reps, t_n, n)) * math.sqrt(1 - phi**2)
    for i in range(1, t_n):
        x[:, i] = phi * x[:, i - 1] + eps[:, i]
    return x


def simulate_core(
    scn: str, a_m: float, h: int, reps: int, rng: np.random.Generator
) -> dict[str, np.ndarray]:
    """Arrays (reps, DAYS, N): volatility characteristic v, signal S = -m, forward h-day return fwd."""
    p = SCENARIOS[scn]
    t_n = DAYS + h + 1
    sector = np.arange(N_ASSETS) % K
    v = _ar1(reps, t_n, N_ASSETS, p["phi_v"], rng)
    eta = _ar1(reps, t_n, N_ASSETS, p["phi_e"], rng)
    m = RHO * v + math.sqrt(1 - RHO**2) * eta
    f = rng.normal(0, SD_F, (reps, t_n, 1))
    g = rng.normal(0, SD_G, (reps, t_n, K))[:, :, sector]
    u = rng.standard_t(3, (reps, t_n, N_ASSETS)) / math.sqrt(3)
    if p["cluster"]:
        u = u * np.exp(_ar1(reps, t_n, N_ASSETS, 0.98, rng, 0.5) - 0.125)
    av = np.full((reps, t_n, 1), A_V)
    if p["regime"]:
        flips = rng.random((reps, t_n)) > 0.99
        st = np.empty((reps, t_n))
        st[:, 0] = (rng.random(reps) < 0.5).astype(float)
        for i in range(1, t_n):
            st[:, i] = np.where(flips[:, i], 1.0 - st[:, i - 1], st[:, i - 1])
        av = (2.0 * A_V * st)[:, :, None]
    r = np.zeros((reps, t_n, N_ASSETS))
    r[:, 1:] = f[:, 1:] + g[:, 1:] + SD_E * (u[:, 1:] - av[:, :-1] * v[:, :-1] - a_m * eta[:, :-1])
    cum = np.cumsum(r, axis=1)
    fwd = cum[:, h + 1 : DAYS + h + 1] - cum[:, 1 : DAYS + 1]
    return {"v": v[:, :DAYS], "S": -m[:, :DAYS], "fwd": fwd}


def partial_series(S: np.ndarray, v: np.ndarray, fwd: np.ndarray) -> np.ndarray:
    r_sr, r_sv, r_vr = _rowcorr(S, fwd), _rowcorr(S, v), _rowcorr(v, fwd)
    return (r_sr - r_sv * r_vr) / np.sqrt((1 - r_sv**2) * (1 - r_vr**2))


def cell_rng(seed: int, scn: str, h: int, a_m: float) -> np.random.Generator:
    return np.random.default_rng([seed, list(SCENARIOS).index(scn), h, round(a_m * 1000)])


def run_cell(seed: int, scn: str, h: int, a_m: float, reps: int, methods: tuple[str, ...]) -> dict:
    rng = cell_rng(seed, scn, h, a_m)
    rej = {m: 0 for m in methods}
    means = []
    for _ in range(reps // 20):
        d = simulate_core(scn, a_m, h, 20, rng)
        x = partial_series(d["S"], d["v"], d["fwd"])
        means.append(x.mean(axis=1))
        for m in methods:
            rej[m] += int(infer(m, x, h, rng)["reject"].sum())
    return {
        "reps": reps,
        "rejection_rate": {m: rej[m] / reps for m in methods},
        "mean_partial_ic_h": float(np.concatenate(means).mean()),
    }


# --------------------------------------------------------------------------------------------- protocol steps
def _ctx(rnd: int) -> tuple[Path, tuple[str, ...], Path]:
    return (PROTOCOL, METHODS, OUT) if rnd == 1 else (PROTOCOL2, ROUND2_METHODS, OUT2)


def _load(out: Path) -> dict:
    return json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"synthetic_only": True}


def _save(out: Path, doc: dict) -> None:
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def step_calibrate(rnd: int) -> dict:
    proto_path, methods, _ = _ctx(rnd)
    proto = json.loads(proto_path.read_text(encoding="utf-8"))["procedure"]["step1_calibration"]
    cells: dict = {}
    for scn in SCENARIOS:
        for h in HORIZONS:
            cells[f"{scn}|h{h}"] = {
                "size": run_cell(proto["seed"], scn, h, 0.0, proto["reps_per_cell"], methods),
                "power_ref": run_cell(
                    proto["seed"], scn, h, A_REF, proto["reps_per_cell"], methods
                ),
            }
    valid = {
        m: all(c["size"]["rejection_rate"][m] <= SIZE_TOL for c in cells.values()) for m in methods
    }
    power = {
        m: float(np.mean([c["power_ref"]["rejection_rate"][m] for c in cells.values()]))
        for m in methods
    }
    size_max = {m: max(c["size"]["rejection_rate"][m] for c in cells.values()) for m in methods}
    selected = None
    cands = [m for m in methods if valid[m]]
    if cands:
        best = max(power[m] for m in cands)
        selected = next(m for m in methods if m in cands and power[m] >= best - 0.005)
    return {"cells": cells, "valid": valid, "mean_power_at_reference": power, "max_size_over_cells": size_max, "selected_method": selected,
            "rule": "valid iff size <= 0.07 in all 10 cells; highest mean power; ties within 0.005 -> lower index"}  # fmt: skip


def step_validate(rnd: int, method: str) -> dict:
    proto_path, _, _ = _ctx(rnd)
    proto = json.loads(proto_path.read_text(encoding="utf-8"))["procedure"]["step2_validation"]
    runs = {}
    for seed in proto["seeds"]:
        cells = {
            f"{scn}|h{h}": run_cell(seed, scn, h, 0.0, proto["reps_per_cell"], (method,))
            for scn in SCENARIOS
            for h in HORIZONS
        }
        sizes = [c["rejection_rate"][method] for c in cells.values()]
        runs[str(seed)] = {
            "cells": cells,
            "max_size": max(sizes),
            "min_size": min(sizes),
            "mean_size": float(np.mean(sizes)),
            "pass": max(sizes) <= SIZE_TOL,
        }
    return {
        "method": method,
        "runs": runs,
        "pass": all(r["pass"] for r in runs.values()),
        "monte_carlo_se_at_0.05": math.sqrt(0.05 * 0.95 / proto["reps_per_cell"]),
    }


def step_power(rnd: int, method: str) -> dict:
    proto_path, _, _ = _ctx(rnd)
    proto = json.loads(proto_path.read_text(encoding="utf-8"))["procedure"]["step3_power_report"]
    thr = {7: 0.0093, 28: 0.0186}
    cells = {}
    for scn in ("S1_baseline", "S3_low_persistence"):
        for h in HORIZONS:
            for a in (0.005, 0.01, 0.02):
                cells[f"{scn}|h{h}|a{a}"] = run_cell(
                    proto["seed"], scn, h, a, proto["reps_per_cell"], (method,)
                )
    mde: dict[str, dict[str, Any]] = {}
    for scn in ("S1_baseline", "S3_low_persistence"):
        for h in HORIZONS:
            pts = sorted(
                (
                    cells[f"{scn}|h{h}|a{a}"]["mean_partial_ic_h"],
                    cells[f"{scn}|h{h}|a{a}"]["rejection_rate"][method],
                )
                for a in (0.005, 0.01, 0.02)
            )
            val: float | None = None
            for (x0, p0), (x1, p1) in pairwise(pts):
                if p0 < 0.8 <= p1:
                    val = x0 + (0.8 - p0) * (x1 - x0) / (p1 - p0)
            # power at twice the economic threshold by linear interpolation of the (partial IC, power) points
            xs, ps = [q[0] for q in pts], [q[1] for q in pts]
            pw2 = float(np.interp(2 * thr[h], xs, ps))
            mde[f"{scn}|h{h}"] = {"mde_80pct_partial_ic_h": val, "threshold": thr[h], "ratio": (val / thr[h]) if val else None,
                                  "power_at_2x_threshold_interpolated": pw2, "points": pts}  # fmt: skip
    stop = any(
        mde[f"S1_baseline|h{h}"]["power_at_2x_threshold_interpolated"] < 0.8 for h in HORIZONS
    )
    return {
        "method": method,
        "cells": cells,
        "mde": mde,
        "stop_power_at_2x_threshold_below_0.8": stop,
    }


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial interval via bisection on the regularised incomplete beta (no scipy)."""
    from math import comb

    def cdf(x: int, p: float) -> float:
        return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(x + 1))

    lo, hi = 0.0, 1.0
    if k > 0:
        a, b = 0.0, 1.0
        for _ in range(60):
            mid = (a + b) / 2
            if 1.0 - cdf(k - 1, mid) < alpha / 2:
                a = mid
            else:
                b = mid
        lo = (a + b) / 2
    if k < n:
        a, b = 0.0, 1.0
        for _ in range(60):
            mid = (a + b) / 2
            if cdf(k, mid) > alpha / 2:
                a = mid
            else:
                b = mid
        hi = (a + b) / 2
    else:
        hi = 1.0
    return lo, hi


def step_surrogates(rnd: int, method: str) -> dict:
    """Surrogate construction of the protocol: S* = beta_t V + (MAX3-specific residual shifted circularly by Delta in [180, T-180])."""
    proto_path, _, _ = _ctx(rnd)
    proto = json.loads(proto_path.read_text(encoding="utf-8"))["procedure"][
        "step4_surrogate_validation"
    ]
    out: dict[str, dict[str, Any]] = {}
    for scn in proto["scenarios"]:
        for a_m in proto["a_m"]:
            for h in HORIZONS:
                rng = cell_rng(proto["seed"], scn, h, a_m)
                rej = tot = 0
                naive_rej = 0
                for _ in range(proto["panels"]):
                    d = simulate_core(scn, a_m, h, 1, rng)
                    s, v, fwd = d["S"][0], d["v"][0], d["fwd"][0]
                    sc, vc = s - s.mean(axis=1, keepdims=True), v - v.mean(axis=1, keepdims=True)
                    beta = (sc * vc).sum(axis=1, keepdims=True) / (vc * vc).sum(
                        axis=1, keepdims=True
                    )
                    resid = sc - beta * vc
                    part_rows, naive_rows = [], []
                    for _s in range(proto["surrogates_per_panel"]):
                        delta = int(rng.integers(180, DAYS - 180 + 1))
                        s_star = beta * vc + np.roll(resid, -delta, axis=0)
                        part_rows.append(partial_series(s_star[None], v[None], fwd[None])[0])
                        naive_rows.append(_rowcorr(s_star, fwd))
                    part, naive = np.array(part_rows), np.array(naive_rows)
                    rej += int(infer(method, part, h, rng)["reject"].sum())
                    naive_rej += int(infer("M0", naive, h)["reject"].sum())
                    tot += len(part)
                lo, hi = clopper_pearson(rej, tot)
                out[f"{scn}|a_m{a_m}|h{h}"] = {
                    "surrogates": tot,
                    "partial_rejection_rate": rej / tot,
                    "cp95": [lo, hi],
                    "naive_ic_rejection_rate_M0": naive_rej / tot,
                }
    ok = all(c["partial_rejection_rate"] <= 0.10 for c in out.values())
    return {
        "method": method,
        "cells": out,
        "pass": ok,
        "note": "surrogates of one panel share the same returns, so the Clopper-Pearson interval is optimistic",
    }


def main(argv: list[str]) -> int:
    cmd = argv[0]
    rnd = int(argv[1]) if len(argv) > 1 else 1
    _, _, out = _ctx(rnd)
    doc = _load(out)
    if cmd == "calibrate":
        doc["calibration"] = step_calibrate(rnd)
    elif cmd == "validate":
        doc["validation"] = step_validate(rnd, doc["calibration"]["selected_method"])
    elif cmd == "power":
        doc["power"] = step_power(rnd, doc["calibration"]["selected_method"])
    elif cmd == "surrogates":
        doc["surrogates"] = step_surrogates(rnd, doc["calibration"]["selected_method"])
    _save(out, doc)
    print(cmd, rnd, "done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
