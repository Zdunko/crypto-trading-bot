"""S9: power of the cross-sectional IC test under the pre-registered dependence scenarios (SYNTHETIC only), the
economic break-even IC of each hypothesis, and the pre-registered ranking. Reads ``s9_criteria.json`` and
``s9_selection.json``; writes ``s9_signal_power_results.json`` (byte-reproducible). No market data is touched."""

from __future__ import annotations

import json
import math
from itertools import pairwise
from pathlib import Path
from statistics import NormalDist

import numpy as np

from quantlab.gate_audit import _hac_t


_ROOT = Path(__file__).resolve().parents[1]
CRITERIA = _ROOT / "docs" / "phase4c" / "s9_criteria.json"
SELECTION = _ROOT / "docs" / "phase4c" / "s9_selection.json"
RESULTS = _ROOT / "docs" / "phase4c" / "s9_signal_power_results.json"
Z95 = NormalDist().inv_cdf(0.95)
SCENARIOS = ("baseline_student_t3_noise", "regime_dependent_skill", "volatility_clustering_noise")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ic_series(
    scn: str, n_assets: int, ic: float, reps: int, days: int, rng: np.random.Generator, cfg: dict
) -> np.ndarray:
    """Daily cross-sectional Pearson IC series (reps x days) between a signal and next-day returns."""
    sd_e, sd_f = cfg["daily_idiosyncratic_sd"], cfg["market_factor_sd"]
    k, sd_g = cfg["sector_factors"]["clusters"], cfg["sector_factors"]["sd"]
    sector = np.arange(n_assets) % k
    f = rng.normal(0.0, sd_f, (reps, days, 1))
    g = rng.normal(0.0, sd_g, (reps, days, k))[:, :, sector]
    if scn == "baseline_student_t3_noise":
        u = rng.standard_t(3, (reps, days, n_assets)) / math.sqrt(3.0)
        ic_t = np.full((reps, days, 1), ic)
        scale = np.full((reps, days, n_assets), sd_e)
    elif scn == "regime_dependent_skill":
        u = rng.normal(0.0, 1.0, (reps, days, n_assets))
        flips = rng.random((reps, days)) > 0.99
        state = np.empty((reps, days))
        state[:, 0] = (rng.random(reps) < 0.5).astype(float)
        for i in range(1, days):
            state[:, i] = np.where(flips[:, i], 1.0 - state[:, i - 1], state[:, i - 1])
        ic_t = (2.0 * ic * state)[:, :, None]
        scale = np.full((reps, days, n_assets), sd_e)
    elif scn == "volatility_clustering_noise":
        u = rng.normal(0.0, 1.0, (reps, days, n_assets))
        ic_t = np.full((reps, days, 1), ic)
        phi = 0.98
        x = rng.normal(0.0, 0.5, (reps, n_assets))
        scale = np.empty((reps, days, n_assets))
        z = rng.normal(0.0, 1.0, (reps, days, n_assets))
        for i in range(days):
            x = phi * x + math.sqrt(1 - phi**2) * 0.5 * z[:, i, :]
            scale[:, i, :] = sd_e * np.exp(x - 0.125)
    else:
        raise ValueError(scn)
    eta = rng.normal(0.0, 1.0, (reps, days, n_assets))
    sig = ic_t * u + np.sqrt(1.0 - ic_t**2) * eta
    ret = f + g + scale * u
    rc = ret - ret.mean(axis=2, keepdims=True)
    sc = sig - sig.mean(axis=2, keepdims=True)
    return (rc * sc).sum(axis=2) / np.sqrt((rc**2).sum(axis=2) * (sc**2).sum(axis=2))


def power_cell(
    scn: str, n_assets: int, ic: float, cfg: dict, rng: np.random.Generator, chunk: int = 20
) -> float:
    reps, days = cfg["replications"], cfg["days"]
    rej = 0
    for a in range(0, reps, chunk):
        s = ic_series(scn, n_assets, ic, min(chunk, reps - a), days, rng, cfg)
        rej += int(np.sum(_hac_t(s) > Z95))
    return rej / reps


def interpolate_mde(points: dict[float, float], target: float = 0.8) -> float | None:
    """Smallest IC at which the (piecewise-linear) power curve reaches ``target``; None if not reached on the grid."""
    xs = sorted(points)
    for x0, x1 in pairwise(xs):
        p0, p1 = points[x0], points[x1]
        if p0 >= target:
            return x0
        if p1 >= target:
            return x0 + (target - p0) * (x1 - x0) / (p1 - p0)
    return xs[0] if points[xs[0]] >= target else None


def break_even_ic(turnover: float, cfg: dict) -> float:
    m = cfg["minimum_economically_relevant_ic"]
    return (
        m["margin"]
        * turnover
        * m["cost_one_way"]
        / (m["top_quintile_mean_z"] * cfg["daily_idiosyncratic_sd"] * 365.0)
    )


def ranking(rubric: dict, selection: dict) -> list[dict]:
    rows = []
    for h in selection["hypotheses"]:
        score = sum(rubric["criteria"][c] * h["scores"][c] for c in rubric["criteria"])
        rows.append(
            {
                "id": h["id"],
                "score": round(score, 6),
                "turnover": h["annual_one_way_turnover_assumption"],
                "params": len(h["free_parameters"]),
            }
        )
    return sorted(rows, key=lambda r: (-r["score"], r["turnover"], r["params"]))


def run_all() -> dict:
    crit, sel = _load(CRITERIA), _load(SELECTION)
    cfg = crit["power_study"]
    rng = np.random.default_rng(cfg["seed"])
    grid = [0.0, *cfg["ic_grid"]]  # 0.0 is a size diagnostic outside the pre-registered grid
    power: dict = {}
    for scn in SCENARIOS:
        for n in cfg["assets"]:
            for ic in grid:
                power[f"{scn}|N{n}|ic{ic}"] = power_cell(scn, n, ic, cfg, rng)
    mde: dict = {}
    for scn in SCENARIOS:
        for n in cfg["assets"]:
            pts = {ic: power[f"{scn}|N{n}|ic{ic}"] for ic in cfg["ic_grid"]}
            mde[f"{scn}|N{n}"] = interpolate_mde(pts)
    hyp: dict = {}
    for h in sel["hypotheses"]:
        ic_min = break_even_ic(h["annual_one_way_turnover_assumption"], cfg)
        worst_cell = {
            n: min(power[f"{s}|N{n}|ic{cfg['ic_grid'][0]}"] for s in SCENARIOS)
            for n in cfg["assets"]
        }
        hyp[h["id"]] = {
            "break_even_ic": ic_min,
            "gross_annual_active_return_at_break_even_ic": ic_min
            * 1.4
            * cfg["daily_idiosyncratic_sd"]
            * 365.0,
            "break_even_ic_with_3x_cost_stress": 3.0 * ic_min,
            "pessimistic_power_at_smallest_grid_ic_by_n": {
                str(n): v for n, v in worst_cell.items()
            },
            "powered_at_break_even_ic_n40": False
            if (ic_min <= cfg["ic_grid"][0] and worst_cell[40] < 0.8)
            else None,
        }
    pessimistic_mde = {str(n): _worst_mde(mde, n) for n in cfg["assets"]}
    return {
        "criteria": "docs/phase4c/s9_criteria.json",
        "synthetic_only": True,
        "power_by_scenario_assets_ic": power,
        "minimum_detectable_ic_at_80pct_interpolated": mde,
        "pessimistic_minimum_detectable_ic_by_n": pessimistic_mde,
        "hypotheses": hyp,
        "ranking": ranking(crit["selection_rubric"], sel),
    }


def _worst_mde(mde: dict, n: int) -> float | str:
    vals = [mde[f"{s}|N{n}"] for s in SCENARIOS]
    return "not reached on the grid (> 0.02)" if any(v is None for v in vals) else max(vals)


def main() -> None:
    RESULTS.write_text(json.dumps(run_all(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()
