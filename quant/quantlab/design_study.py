"""S8 research-design study: seeded Monte Carlo on SYNTHETIC returns only.

Answers the pre-registered design questions D1-D6 of ``docs/phase4c/s8_criteria.json``. Nothing here reads market
data, evaluates a strategy or touches the feasibility gate and its thresholds. Results are stored in
``docs/phase4c/s8_design_study_results.json``; re-running must reproduce the file byte for byte.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

from quantlab.gate_audit import _dgp, _hac_t


_ROOT = Path(__file__).resolve().parents[1]
CRITERIA = _ROOT / "docs" / "phase4c" / "s8_criteria.json"
RESULTS = _ROOT / "docs" / "phase4c" / "s8_design_study_results.json"
DAYS = 365
SD = 0.03
N_DAYS = 1642
Z95 = NormalDist().inv_cdf(0.95)
Z80 = NormalDist().inv_cdf(0.80)
IR_GRID = (0.0, 0.3, 0.5, 0.8, 1.0)
DGPS = ("iid_normal", "student_t3", "ar1_0.15", "vol_clustering", "regime_persistent_mean")
BLOCKS = (10, 20, 40)


def _params() -> dict:
    return json.loads(CRITERIA.read_text(encoding="utf-8"))["simulation_fixed_parameters"]


def mu_for_ir(ir: float, sd: float = SD) -> float:
    """Daily mean that gives an annualised information ratio ``ir`` at daily volatility ``sd``."""
    return ir * sd / math.sqrt(DAYS)


def gen(kind: str, rng: np.random.Generator, reps: int, n: int, mu: float) -> np.ndarray:
    if kind == "regime_persistent_mean":
        stay = 0.99
        state = np.empty((reps, n))
        state[:, 0] = np.where(rng.random(reps) < 0.5, 1.0, -1.0)
        flips = rng.random((reps, n)) > stay
        for i in range(1, n):
            state[:, i] = np.where(flips[:, i], -state[:, i - 1], state[:, i - 1])
        return mu + 0.001 * state + rng.normal(0.0, SD, (reps, n))
    return _dgp(kind, rng, reps, n, SD, mu)


def block_boot_p(
    x: np.ndarray, rng: np.random.Generator, block: int, draws: int, chunk: int = 50
) -> np.ndarray:
    """One-sided p-value of mean(x) > 0 from a centred circular block bootstrap (rows are independent series)."""
    reps, n = x.shape
    nb = n // block
    out = np.empty(reps)
    for a in range(0, reps, chunk):
        xs = x[a : a + chunk]
        r = xs.shape[0]
        ext = np.concatenate([xs, xs[:, :block]], axis=1)
        cs = np.concatenate([np.zeros((r, 1)), np.cumsum(ext, axis=1)], axis=1)
        starts = rng.integers(0, n, size=(r, draws, nb))
        rows = np.arange(r)[:, None, None]
        sums = cs[rows, starts + block] - cs[rows, starts]
        boot = sums.sum(axis=2) / (nb * block)
        obs = xs.mean(axis=1)
        centred = boot - boot.mean(axis=1, keepdims=True)
        out[a : a + r] = (1 + np.sum(centred >= obs[:, None], axis=1)) / (draws + 1)
    return out


# --------------------------------------------------------------------------------------------- D1
def d1_inference(reps: int, draws: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    out: dict = {}
    for kind in DGPS:
        for ir in IR_GRID:
            x = gen(kind, rng, reps, N_DAYS, mu_for_ir(ir))
            naive = x.mean(axis=1) / (x.std(axis=1, ddof=1) / math.sqrt(N_DAYS))
            cell = {
                "naive_t": float(np.mean(naive > Z95)),
                "newey_west_lag10": float(np.mean(_hac_t(x) > Z95)),
            }
            for blk in BLOCKS:
                cell[f"circular_block_bootstrap_L{blk}"] = float(
                    np.mean(block_boot_p(x, rng, blk, draws) <= 0.05)
                )
            out[f"{kind}|ir{ir}"] = cell
    return out


# --------------------------------------------------------------------------------------------- D2
def d2_negative_vs_underpowered(reps: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    out: dict = {}
    for kind in ("iid_normal", "regime_persistent_mean"):
        for ir in (-0.5, 0.0, 0.3, 0.5):
            x = gen(kind, rng, reps, N_DAYS, mu_for_ir(ir))
            t = _hac_t(x)
            mean = x.mean(axis=1)
            se = mean / np.where(np.abs(t) < 1e-12, 1e-12, t)
            se = np.abs(se)
            ir_hat = mean / SD * math.sqrt(DAYS)
            upper = (mean + Z95 * se) / SD * math.sqrt(DAYS)
            out[f"{kind}|true_ir{ir}"] = {
                "p_fail_to_reject_one_sided": float(np.mean(t <= Z95)),
                "p_conclusive_negative_upper95_below_0": float(np.mean(upper < 0.0)),
                "p_upper95_below_reference_ir_0.3": float(np.mean(upper < 0.3)),
                "mean_halfwidth_annual_ir_95": float(np.mean(Z95 * se / SD * math.sqrt(DAYS))),
                "ir_hat_sd": float(np.std(ir_hat)),
            }
    return out


# --------------------------------------------------------------------------------------------- D3
def _knn_predict(x_tr: np.ndarray, y_tr: np.ndarray, x_test: np.ndarray, k: int) -> np.ndarray:
    d = np.abs(x_test[:, None] - x_tr[None, :])
    idx = np.argpartition(d, k, axis=1)[:, :k]
    return y_tr[idx].mean(axis=1)


def d3_purging(reps: int, folds: int, h: int, embargo: int, k: int, n: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    ic: dict[str, list[float]] = {
        "shuffled_kfold": [],
        "contiguous_unpurged": [],
        "contiguous_purged_embargoed": [],
    }
    lost_train = []
    for _ in range(reps):
        r = rng.normal(0, SD, n + h)
        cs = np.concatenate([[0.0], np.cumsum(r)])
        y = (
            cs[h + 1 : n + h + 1] - cs[1 : n + 1]
        )  # sum of the next h returns for t = 0..n-1 (overlapping labels)
        x = np.empty(n)
        x[0] = 0.0
        eps = rng.normal(0, 1, n)
        for i in range(1, n):
            x[i] = 0.98 * x[i - 1] + eps[i]
        t_idx = np.arange(n)
        perm = rng.permutation(n)
        for scheme, scores in ic.items():
            preds = np.empty(n)
            for f in range(folds):
                if scheme == "shuffled_kfold":
                    test_idx = np.sort(perm[f::folds])
                    tr = np.setdiff1d(t_idx, test_idx)
                else:
                    lo, hi = f * n // folds, (f + 1) * n // folds
                    test_idx = t_idx[lo:hi]
                    if scheme == "contiguous_unpurged":
                        tr = np.concatenate([t_idx[:lo], t_idx[hi:]])
                    else:
                        tr = np.concatenate(
                            [t_idx[: max(0, lo - h)], t_idx[min(n, hi + embargo) :]]
                        )
                        lost_train.append(1.0 - len(tr) / (n - len(test_idx)))
                preds[test_idx] = _knn_predict(x[tr], y[tr], x[test_idx], k)
            scores.append(float(np.corrcoef(preds, y)[0, 1]))
    return {
        **{f"{s}_mean_ic_on_noise": float(np.mean(v)) for s, v in ic.items()},
        **{f"{s}_ic_se": float(np.std(v) / math.sqrt(len(v))) for s, v in ic.items()},
        "purged_fraction_of_train_removed": float(np.mean(lost_train)),
        "label_horizon_days": h,
        "embargo_days": embargo,
    }


# --------------------------------------------------------------------------------------------- D4
def d4_cross_section(reps: int, seed: int, params: dict) -> dict:
    rng = np.random.default_rng(seed)
    cs = params["cross_section"]
    out: dict = {}
    days = cs["days"]
    clusters = cs["sector_factors"]["clusters"]
    for n_assets in cs["assets"]:
        sector = np.arange(n_assets) % clusters
        for rho_x in cs["rho_idiosyncratic_extra"]:
            for ic_a in cs["ic_grid"]:
                rej_ic = rej_act = 0
                n_eff = []
                act_ir = []
                avg_corr = []
                for _ in range(reps):
                    f = rng.normal(0, 0.025, (days, 1))
                    g = rng.normal(0, 0.01, (days, clusters))[:, sector]
                    u = rng.normal(0, 1, (days, n_assets))
                    c = rng.normal(0, 1, (days, 1))
                    e = 0.02 * (math.sqrt(1 - rho_x) * u + math.sqrt(rho_x) * c)
                    ret = f + g + e
                    sig = ic_a * u + math.sqrt(1 - ic_a**2) * rng.normal(0, 1, (days, n_assets))
                    rc = ret - ret.mean(axis=1, keepdims=True)
                    sc = sig - sig.mean(axis=1, keepdims=True)
                    ic_t = (rc * sc).sum(axis=1) / np.sqrt(
                        (rc**2).sum(axis=1) * (sc**2).sum(axis=1)
                    )
                    rej_ic += int(_hac_t(ic_t[None, :])[0] > Z95)
                    top = max(1, n_assets // 5)
                    sel = np.argsort(-sig, axis=1)[:, :top]
                    long_ret = np.take_along_axis(ret, sel, axis=1).mean(axis=1)
                    active = long_ret - ret.mean(axis=1)
                    act_ir.append(float(active.mean() / active.std(ddof=1) * math.sqrt(DAYS)))
                    rej_act += int(_hac_t(active[None, :])[0] > Z95)
                    ew = ret.mean(axis=1)
                    n_eff.append(float(ret.var(axis=0, ddof=1).mean() / ew.var(ddof=1)))
                    if n_assets > 1:
                        cm = np.corrcoef(ret.T)
                        avg_corr.append(float((cm.sum() - n_assets) / (n_assets * (n_assets - 1))))
                out[f"N{n_assets}|extra_rho{rho_x}|ic{ic_a}"] = {
                    "power_or_size_ic_test": rej_ic / reps,
                    "power_or_size_top_quintile_active_return": rej_act / reps,
                    "mean_annual_active_ir_top_quintile_vs_equal_weight": float(np.mean(act_ir)),
                    "effective_independent_assets_equal_weight_portfolio": float(np.mean(n_eff)),
                    "average_pairwise_return_correlation": float(np.mean(avg_corr))
                    if avg_corr
                    else 0.0,
                }
    return out


# --------------------------------------------------------------------------------------------- D5
def d5_years_needed(d1: dict, reps: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    deff: dict = {}
    for kind in DGPS:
        x = gen(kind, rng, reps, N_DAYS, 0.0)
        within = np.mean(x.var(axis=1, ddof=1))
        deff[kind] = float(N_DAYS * np.var(x.mean(axis=1), ddof=1) / within)
    out: dict = {
        "design_effect_measured": deff,
        "years_needed_80pct": {},
        "power_at_history_years": {},
    }
    for kind, d in deff.items():
        out["years_needed_80pct"][kind] = {
            f"ir{ir}": float(((Z95 + Z80) / ir) ** 2 * max(d, 1.0)) for ir in IR_GRID if ir > 0
        }
        out["power_at_history_years"][kind] = {
            f"{yrs}y|ir{ir}": float(NormalDist().cdf(ir * math.sqrt(yrs / max(d, 1.0)) - Z95))
            for yrs in (4.5, 8.0, 13.0)
            for ir in IR_GRID
            if ir > 0
        }
    out["note"] = (
        "analytic normal approximation using the simulated design effect; validated against D1 at 4.5 years"
    )
    out["d1_reference_power_ir0.5_nw"] = {
        k: v["newey_west_lag10"] for k, v in d1.items() if k.endswith("|ir0.5")
    }
    return out


# --------------------------------------------------------------------------------------------- D6
def d6_selection(reps: int, seed: int, sizes: tuple[int, ...]) -> dict:
    rng = np.random.default_rng(seed)
    se = math.sqrt(DAYS / N_DAYS)
    norm = NormalDist()
    out: dict = {}
    for m in sizes:
        z = rng.normal(0.0, 1.0, (reps, m))
        best = z.max(axis=1)
        p_best = 1.0 - np.array([norm.cdf(v) for v in best])
        oos = rng.normal(0.0, 1.0, reps)
        out[f"n{m}"] = {
            "mean_best_in_sample_annual_sharpe": float(best.mean() * se),
            "mean_out_of_sample_sharpe_of_selected": float(oos.mean() * se),
            "p_best_unadjusted_significant": float(np.mean(p_best <= 0.05)),
            "p_best_holm_or_bonferroni_significant": float(np.mean(p_best * m <= 0.05)),
            "expected_max_z_analytic_sqrt_2ln_n": float(math.sqrt(2 * math.log(m)))
            if m > 1
            else 0.0,
        }
    return out


def run_all() -> dict:
    p = _params()
    seeds = p["seeds"]
    reps = p["replications_per_cell"]
    d1 = d1_inference(reps, p["bootstrap_draws"], seeds["d1"])
    return {
        "criteria": "docs/phase4c/s8_criteria.json",
        "synthetic_only": True,
        "d1_size_and_power": d1,
        "d2_negative_vs_underpowered": d2_negative_vs_underpowered(reps, seeds["d2"]),
        "d3_purging": d3_purging(
            p["purge"]["reps"],
            p["purge"]["folds"],
            p["purge"]["label_horizon_days"],
            p["purge"]["embargo_days"],
            p["purge"]["knn_k"],
            p["purge"]["days"],
            seeds["d3"],
        ),
        "d4_cross_section": d4_cross_section(reps, seeds["d4"], p),
        "d5_years_needed": d5_years_needed(d1, reps, seeds["d5"]),
        "d6_selection": d6_selection(
            p["multiple_testing"]["reps"], seeds["d6"], tuple(p["multiple_testing"]["n_families"])
        ),
    }


def main() -> None:
    doc = run_all()
    RESULTS.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()
