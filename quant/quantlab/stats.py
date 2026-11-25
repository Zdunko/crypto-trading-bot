"""
Statistical credibility toolkit, fixed BEFORE any Family A result exists (protocol_v4_stats.json).

Definitions follow Bailey & Lopez de Prado (2014) for PSR / DSR / minimum track record length and
Bailey, Borwein, Lopez de Prado, Zhu (2017) for PBO (CSCV). Sharpe ratios here are PER PERIOD
(not annualised) unless a function says otherwise. Standard library only (``NormalDist``).

Guard rails encoded in :func:`credibility`: a result is never called significant when the sample is
too small to detect a plausible effect (``underpowered``) and a volatility-targeting overlay by itself
is not evidence of alpha (the caller must compare against the unscaled basket).
"""

from __future__ import annotations

import math
from itertools import combinations
from statistics import NormalDist

import numpy as np


_N = NormalDist()
EULER_GAMMA = 0.5772156649015329


def moments(returns: np.ndarray) -> tuple[float, float, float, int]:
    """(per-period Sharpe, skewness, raw kurtosis, n)."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    sd = r.std(ddof=1) if n > 1 else 0.0
    if n < 4 or sd == 0:
        return float("nan"), float("nan"), float("nan"), n
    z = (r - r.mean()) / r.std(ddof=0)
    return float(r.mean() / sd), float((z**3).mean()), float((z**4).mean()), n


def sharpe_se(sr: float, skew: float, kurt: float, n: int) -> float:
    """Standard error of a per-period Sharpe estimate (non-normal returns, Mertens 2002)."""
    return math.sqrt(max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr, 1e-12) / (n - 1))


def psr(sr: float, n: int, skew: float, kurt: float, sr_star: float = 0.0) -> float:
    """Probabilistic Sharpe ratio: P(true SR > sr_star) given the estimate."""
    return _N.cdf((sr - sr_star) / sharpe_se(sr, skew, kurt, n))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Expected maximum of ``n_trials`` independent zero-mean Sharpe estimates (selection bias)."""
    if n_trials <= 1:
        return 0.0
    g = EULER_GAMMA
    return math.sqrt(var_sr) * (
        (1 - g) * _N.inv_cdf(1 - 1.0 / n_trials) + g * _N.inv_cdf(1 - 1.0 / (n_trials * math.e))
    )


def deflated_sharpe(returns: np.ndarray, n_trials: int, var_sr: float | None = None) -> dict:
    """DSR: PSR against the expected best Sharpe of ``n_trials`` trials. ``var_sr`` defaults to the
    sampling variance 1/(n-1) of a Sharpe estimate under no skill (pre-registered assumption)."""
    sr, skew, kurt, n = moments(returns)
    if not math.isfinite(sr):
        return {"dsr": float("nan"), "sr": sr, "sr_star": float("nan"), "n": n}
    v = var_sr if var_sr is not None else 1.0 / (n - 1)
    star = expected_max_sharpe(n_trials, v)
    return {
        "dsr": psr(sr, n, skew, kurt, star),
        "sr": sr,
        "sr_star": star,
        "n": n,
        "trials": n_trials,
    }


def min_track_record(
    sr: float, sr_star: float, skew: float, kurt: float, alpha: float = 0.05
) -> float:
    """Observations needed for the estimate to exceed ``sr_star`` at confidence 1-alpha."""
    if sr <= sr_star:
        return math.inf
    z = _N.inv_cdf(1 - alpha)
    return 1 + max(1 - skew * sr + (kurt - 1) / 4 * sr * sr, 1e-12) * (z / (sr - sr_star)) ** 2


def min_detectable_sharpe(
    n: int, periods_per_year: float, alpha: float = 0.05, power: float = 0.8
) -> float:
    """Smallest ANNUALISED Sharpe a one-sided test can detect at the given power (normal returns)."""
    return (
        (_N.inv_cdf(1 - alpha) + _N.inv_cdf(power))
        / math.sqrt(max(n - 1, 1))
        * math.sqrt(periods_per_year)
    )


def pbo_cscv(returns: np.ndarray, n_splits: int = 16) -> dict:
    """
    Probability of backtest overfitting by combinatorially symmetric cross-validation.
    ``returns`` is T x N (periods x configurations). Deterministic (all C(S, S/2) splits).
    """
    r = np.asarray(returns, dtype=float)
    t, n_cfg = r.shape
    if n_cfg < 2 or n_splits % 2 or t < n_splits * 2:
        return {
            "pbo": float("nan"),
            "splits": 0,
            "note": "needs >= 2 configurations and enough rows",
        }
    blocks = np.array_split(np.arange(t), n_splits)

    def sharpe(rows: np.ndarray) -> np.ndarray:
        sd = rows.std(axis=0, ddof=1)
        return np.where(sd > 0, rows.mean(axis=0) / np.where(sd > 0, sd, 1), 0.0)

    logits = []
    for is_ids in combinations(range(n_splits), n_splits // 2):
        oos_ids = [b for b in range(n_splits) if b not in is_ids]
        is_rows = r[np.concatenate([blocks[b] for b in is_ids])]
        oos_rows = r[np.concatenate([blocks[b] for b in oos_ids])]
        best = int(np.argmax(sharpe(is_rows)))
        oos_sr = sharpe(oos_rows)
        rank = (np.sum(oos_sr < oos_sr[best]) + 1) / (n_cfg + 1)  # relative OOS rank in (0, 1)
        logits.append(math.log(rank / (1 - rank)))
    lam = np.array(logits)
    return {
        "pbo": float((lam <= 0).mean()),
        "splits": len(lam),
        "median_logit": float(np.median(lam)),
    }


def holm(pvalues: list[float], alpha: float = 0.05) -> list[bool]:
    """Holm-Bonferroni: family-wise error control; True = hypothesis rejected."""
    order = np.argsort(pvalues)
    m = len(pvalues)
    out = [False] * m
    for rank, idx in enumerate(order):
        if pvalues[idx] <= alpha / (m - rank):
            out[idx] = True
        else:
            break
    return out


def benjamini_hochberg(pvalues: list[float], q: float = 0.05) -> list[bool]:
    """BH false-discovery-rate control (reported as a secondary view only)."""
    m = len(pvalues)
    order = np.argsort(pvalues)
    cutoff = -1
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= q * rank / m:
            cutoff = rank
    out = [False] * m
    for rank, idx in enumerate(order, start=1):
        out[idx] = rank <= cutoff
    return out


def credibility(
    returns: np.ndarray, n_trials: int, rules: dict, periods_per_year: float = 365.0
) -> dict:
    """
    Verdict for ONE candidate return series against the pre-registered ``rules``
    (``protocol/protocol_v4_stats.json``). It never returns "credible" for an underpowered sample.
    """
    sr, skew, kurt, n = moments(returns)
    out: dict = {
        "n": n,
        "sharpe_annualised": sr * math.sqrt(periods_per_year) if math.isfinite(sr) else None,
    }
    if not math.isfinite(sr):
        return {**out, "verdict": "insufficient_data", "reasons": ["too few or constant returns"]}
    mde = min_detectable_sharpe(n, periods_per_year, rules["alpha"], rules["power"])
    d = deflated_sharpe(returns, n_trials)
    p_value = 1.0 - psr(sr, n, skew, kurt, 0.0)
    out.update(
        mde_sharpe_annualised=mde, dsr=d["dsr"], p_value_sharpe_gt_0=p_value, trials=n_trials
    )
    reasons = []
    if mde > rules["max_mde_annualised_sharpe"]:
        reasons.append(
            f"underpowered: detectable annualised Sharpe {mde:.2f} > {rules['max_mde_annualised_sharpe']}"
        )
    if d["dsr"] < rules["min_dsr"]:
        reasons.append(f"DSR {d['dsr']:.3f} < {rules['min_dsr']} with {n_trials} trials")
    out["reasons"] = reasons
    out["verdict"] = (
        "underpowered" if any(x.startswith("underpowered") for x in reasons)
        else ("not_credible" if reasons else "passes_statistical_screen")
    )  # fmt: skip
    return out
