"""Active-window statistics and layered reporting helpers (reconciles the Family A reporting inconsistencies)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from quantlab.stats import min_detectable_sharpe


def active_days(exposure: pd.Series | list[float]) -> np.ndarray:
    """Boolean per UTC day: the strategy held a position at some close of that day (daily exposure series input)."""
    return np.asarray(exposure, dtype=float) > 1e-9


def _moments(r: np.ndarray) -> dict:
    n = len(r)
    sd = r.std(ddof=1) if n > 2 else 0.0
    rho = float(np.corrcoef(r[:-1], r[1:])[0, 1]) if n > 3 and sd > 0 else 0.0
    rho = 0.0 if not math.isfinite(rho) else max(min(rho, 0.95), -0.95)
    n_eff = min(n, n * (1 - rho) / (1 + rho)) if n else 0.0  # never above the raw n
    return {
        "n": n,
        "sharpe": float(r.mean() / sd * math.sqrt(365)) if sd > 0 else None,
        "lag1_autocorrelation": rho,
        "effective_n": float(n_eff),
        "min_detectable_sharpe": min_detectable_sharpe(int(n_eff), 365.0) if n_eff > 2 else None,
    }


def active_stats(
    daily_equity: list[float] | np.ndarray, daily_exposure: list[float] | np.ndarray, wallet: float
) -> dict:
    """
    Two separate notions (they are NOT interchangeable and were conflated in earlier reports):

    * **trading window**: from the start to the last day on which the strategy held or traded a position
      (after a terminal liquidation the account is idle and carries no information). Statistics here include
      the zero-return days the strategy chose to sit in cash inside the window.
    * **invested days**: days with a position held, traded or a non-zero return; the conservative base for
      statistical power because the information about skill sits in these days.
    ``daily_equity`` and ``daily_exposure`` are day-end series of equal length starting at the evaluation start.
    """
    eq = np.asarray(daily_equity, dtype=float)
    ex = np.asarray(daily_exposure, dtype=float)
    ret = np.diff(np.r_[wallet, eq]) / np.r_[wallet, eq][:-1]
    prev_ex = np.r_[0.0, ex[:-1]]
    invested = (ex > 1e-9) | (prev_ex > 1e-9) | (np.abs(ret) > 1e-12)
    n_cal = len(eq)
    window = int(np.flatnonzero(invested).max()) + 1 if invested.any() else 0
    out = {
        "calendar_days": n_cal,
        "trading_window_days": window,
        "invested_days": int(invested.sum()),
        "idle_days_after_window": n_cal - window,
        "exposure_avg_calendar": float(ex.mean()) if n_cal else None,
        "exposure_avg_window": float(ex[:window].mean()) if window else None,
        "time_in_market_calendar": float((ex > 1e-9).mean()) if n_cal else None,
        "time_in_market_window": float((ex[:window] > 1e-9).mean()) if window else None,
        "zero_return_share_calendar": float((np.abs(ret) < 1e-12).mean()) if n_cal else None,
    }
    out["window"] = _moments(ret[:window]) if window > 3 else {"n": window}
    out["invested"] = _moments(ret[invested]) if invested.sum() > 3 else {"n": int(invested.sum())}
    return out


def layered_report(
    result_stats: dict, risk_report: dict | None, cost: dict | None, signal_ic: dict | None = None
) -> dict:
    """Four separable tables (L1 signal, L2 portfolio, L3 execution, L4 risk); each layer only reports its own metrics."""
    out = {"L1_signal": signal_ic or {"note": "no signal log supplied"}}
    out["L2_portfolio"] = {
        k: result_stats.get(k)
        for k in ("exposure_avg_window", "exposure_avg_calendar", "time_in_market_window")
    }
    out["L3_execution"] = cost or {}
    if risk_report:
        total = sum(risk_report["candles_in_state"].values()) or 1
        out["L4_risk"] = {
            "final_state": risk_report["state"],
            "safety_disqualified": risk_report["safety_disqualified"],
            "share_of_candles_in_state": {
                k: v / total for k, v in risk_report["candles_in_state"].items()
            },
            "transitions": [
                (r["t"], r["from"], r["to"], r["cause"]) for r in risk_report["transitions"]
            ],
            "flat_cycles": risk_report["flat_cycles"],
        }
    return out


def signal_information(scores: pd.DataFrame, next_returns: pd.DataFrame) -> dict:
    """L1 diagnostics from a signal log: pooled rank information coefficient and hit rate (both aligned DataFrames)."""
    s, r = scores.stack(), next_returns.stack()
    idx = s.index.intersection(r.index)
    if len(idx) < 10 or s[idx].nunique() < 2:
        return {"n": len(idx), "ic": None, "hit_rate": None}
    ic = float(s[idx].rank().corr(r[idx].rank()))
    pos = s[idx] > s[idx].median()
    hit = float(((r[idx] > 0) == pos).mean())
    return {"n": len(idx), "ic": ic, "hit_rate": hit}
