"""S7 methodology audit of the S6 feasibility gate: seeded Monte Carlo on SYNTHETIC returns only.

Nothing here touches market data, the gate or its thresholds. Each function answers one design-level
question and returns plain numbers that are stored in ``docs/phase4c/s7_gate_audit_results.json``.
The numbers describe the statistical behaviour of the gate's formulas, not any real strategy.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

from quantlab.stats import min_detectable_sharpe


_ROOT = Path(__file__).resolve().parents[1]
N = NormalDist()
Z_ONE_SIDED_5 = N.inv_cdf(0.95)
DAYS = 365


def _hac_t(x: np.ndarray, lag: int = 10) -> np.ndarray:
    """Newey-West t statistic of the mean for each row of ``x`` (reps x n)."""
    n = x.shape[1]
    d = x - x.mean(axis=1, keepdims=True)
    var = (d * d).mean(axis=1)
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1)
        var = var + 2.0 * w * (d[:, k:] * d[:, :-k]).mean(axis=1)
    return x.mean(axis=1) / np.sqrt(np.maximum(var, 1e-300) / n)


# ---------------------------------------------------------------------------- Q1 exposure
def q1_exposure_bias(
    years: float = 4.5, serial: float = 0.05, reps: int = 400, seed: int = 1
) -> dict:
    """(a) The gate's MDE as a function of the invested-day share. (b) Is the active-day basis coherent?
    Simulate a strategy invested a share s of days with true ACTIVE-day annual Sharpe 1.0 and flat days at zero:
    the t-test on active days and on the calendar series have the same power, so the gate measures the
    detectability of the ACTIVE-day Sharpe, which falls with s only because there are fewer active days."""
    shares = [0.1, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0]
    mde = {
        str(s): min_detectable_sharpe(int(years * DAYS * s * (1 - serial) / (1 + serial)), DAYS)
        for s in shares
    }
    rng = np.random.default_rng(seed)
    n = int(years * DAYS)
    sd = 0.03
    mu = 1.0 * sd / math.sqrt(DAYS)  # active-day annual Sharpe 1.0
    out = {}
    for s in (0.2, 0.9):
        active = rng.random((reps, n)) < s
        r = np.where(active, rng.normal(mu, sd, (reps, n)), 0.0)
        cal = r
        t_cal = cal.mean(axis=1) / (cal.std(axis=1, ddof=1) / math.sqrt(n))
        pw_cal = float(np.mean(t_cal > Z_ONE_SIDED_5))
        ta = np.array(
            [
                (row[a].mean() / (row[a].std(ddof=1) / math.sqrt(a.sum())))
                for row, a in zip(r, active, strict=True)
            ]
        )
        pw_act = float(np.mean(ta > Z_ONE_SIDED_5))
        out[str(s)] = {"power_active_days": pw_act, "power_calendar_series": pw_cal}
    return {"mde_active_sharpe_by_share": mde, "power_at_active_sharpe_1": out}


# ---------------------------------------------------------------------------- Q2/Q3 episodes
def q2_design_effect(reps: int = 120, seed: int = 2, k_assets: int = 40, t_days: int = 500, p_enter: float = 0.02,
                     durations: tuple[int, ...] = (1, 5, 20), regime: bool = False) -> dict:  # fmt: skip
    """True design effect of the mean EPISODE return (variance inflation versus independent episodes) from a factor
    model with overlapping holding periods, against the gate's Kish formula 1 + (m - 1) * rho, where m is the mean
    number of entries on an entry day and rho the within-day correlation of episode returns. ``regime`` adds a slow
    regime mean (bull/bear) shared by all assets."""
    rng = np.random.default_rng(seed)
    sf, se, beta = 0.03, 0.03, 1.0
    res = {}
    for d in durations:
        means, ns, ms = [], [], []
        for _ in range(reps):
            f = rng.normal(0, sf, t_days + d)
            if regime:
                reg = np.repeat(
                    rng.choice([-0.0015, 0.0015], size=math.ceil((t_days + d) / 120)), 120
                )[: t_days + d]
                f = f + reg
            eps = rng.normal(0, se, (k_assets, t_days + d))
            r = beta * f[None, :] + eps
            csum = np.concatenate([np.zeros((k_assets, 1)), np.cumsum(r, axis=1)], axis=1)
            ep, entries_per_day = [], np.zeros(t_days)
            for a in range(k_assets):
                t = 0
                while t < t_days:
                    if rng.random() < p_enter:
                        ep.append(csum[a, t + d] - csum[a, t])
                        entries_per_day[t] += 1
                        t += d
                    else:
                        t += 1
            ep_arr = np.array(ep)
            means.append(ep_arr.mean())
            ns.append(len(ep_arr))
            ms.append(entries_per_day[entries_per_day > 0].mean())
        var_single = d * (beta**2 * sf**2 + se**2)
        n_mean = float(np.mean(ns))
        deff_true = float(np.var(means, ddof=1) * n_mean / var_single)
        rho = beta**2 * sf**2 / (beta**2 * sf**2 + se**2)
        m = float(np.mean(ms))
        res[str(d)] = {"episodes": n_mean, "deff_true": deff_true, "deff_gate_formula": 1 + (m - 1) * rho,
                       "effective_true": n_mean / deff_true, "effective_gate": n_mean / (1 + (m - 1) * rho)}  # fmt: skip
    return res


# ---------------------------------------------------------------------------- Q4 MDE
def _dgp(
    kind: str, rng: np.random.Generator, reps: int, n: int, sd: float = 0.03, mu: float = 0.0
) -> np.ndarray:
    if kind == "iid_normal":
        return rng.normal(mu, sd, (reps, n))
    if kind == "student_t3":
        return mu + sd * rng.standard_t(3, (reps, n)) / math.sqrt(3.0)
    if kind == "ar1_0.15":
        e = rng.normal(0, sd, (reps, n))
        x = np.empty_like(e)
        x[:, 0] = e[:, 0]
        for i in range(1, n):
            x[:, i] = 0.15 * x[:, i - 1] + e[:, i]
        return mu + x * math.sqrt(1 - 0.15**2)
    if kind == "vol_clustering":
        h = np.empty((reps, n))
        h[:, 0] = sd**2
        z = rng.normal(0, 1, (reps, n))
        x = np.empty((reps, n))
        x[:, 0] = sd * z[:, 0]
        for i in range(1, n):
            h[:, i] = 0.05 * sd**2 + 0.10 * x[:, i - 1] ** 2 + 0.85 * h[:, i - 1]
            x[:, i] = np.sqrt(h[:, i]) * z[:, i]
        return mu + x
    raise ValueError(kind)


def q4_mde_validity(reps: int = 600, seed: int = 4, sizes: tuple[int, ...] = (500, 1642)) -> dict:
    """Size (null) and power (at the gate's MDE) of the naive iid Sharpe test and of a Newey-West test across
    return processes and sample lengths. The gate's MDE assumes normal, serially uncorrelated returns."""
    rng = np.random.default_rng(seed)
    sd = 0.03
    out: dict = {}
    for n in sizes:
        mde = min_detectable_sharpe(n, DAYS)
        mu_mde = mde * sd / math.sqrt(DAYS)
        for kind in ("iid_normal", "student_t3", "ar1_0.15", "vol_clustering"):
            x0 = _dgp(kind, rng, reps, n, sd, 0.0)
            t_naive = x0.mean(axis=1) / (x0.std(axis=1, ddof=1) / math.sqrt(n))
            x1 = _dgp(kind, rng, reps, n, sd, mu_mde)
            p_naive = x1.mean(axis=1) / (x1.std(axis=1, ddof=1) / math.sqrt(n))
            out[f"n{n}_{kind}"] = {
                "mde_annual_sharpe": mde,
                "size_naive": float(np.mean(t_naive > Z_ONE_SIDED_5)),
                "size_newey_west": float(np.mean(_hac_t(x0) > Z_ONE_SIDED_5)),
                "power_naive_at_mde": float(np.mean(p_naive > Z_ONE_SIDED_5)),
                "power_newey_west_at_mde": float(np.mean(_hac_t(x1) > Z_ONE_SIDED_5)),
            }
    return out


# ---------------------------------------------------------------------------- Q5 defensive strategies
def q5_defensive_timing_power(
    reps: int = 80, seed: int = 5, n: int = 1642, block: int = 10, draws: int = 199
) -> dict:
    """Power of the circular-block random-timing null for an exposure schedule with a given base share and timing skill
    kappa (P(exposed | next return > 0) = base + kappa, P(exposed | < 0) = base - kappa). Shows what a low-frequency
    defensive design CAN detect when the right statistic is used, independent of the gate's absolute-Sharpe MDE."""
    rng = np.random.default_rng(seed)
    out: dict = {}
    nb = n // block
    for base in (0.2, 0.9):
        for kappa in (0.0, 0.01, 0.02, 0.05):
            if base + kappa > 1 or base - kappa < 0:
                continue
            rej = 0
            for _ in range(reps):
                f = rng.normal(0, 0.03, n)
                up = f > 0
                e = (rng.random(n) < np.where(up, base + kappa, base - kappa)).astype(float)
                eb = e[: nb * block].reshape(nb, block)
                null = np.empty(draws)
                for j in range(draws):
                    perm = eb[rng.permutation(nb)].ravel()
                    null[j] = (perm * f[: nb * block]).mean()
                p = (1 + np.sum(null >= (e[: nb * block] * f[: nb * block]).mean())) / (draws + 1)
                rej += int(p <= 0.05)
            out[f"base{base}_kappa{kappa}"] = {"rejection_rate": rej / reps}
    return out


# ---------------------------------------------------------------------------- Q6 exposure after the risk layer
def q6_exposure_after_risk_layer(paths: int = 60, seed: int = 6, years: float = 4.5) -> dict:
    """Run a fully invested equal-weight crypto-like synthetic book through the FROZEN S2 wrapper (daily candles,
    8 assets, common factor correlation 0.6) at several asset volatilities: realised invested-day share, share of
    paths that end in SHUTDOWN, and median day of the first shutdown. Synthetic: it says how restrictive the layer is
    for a book of a given volatility, not what the market will do."""
    import pandas as pd

    from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run
    from quantlab.risk_v2 import RiskManagedStrategy, RiskStateMachine, RiskV2Config

    class HoldAll(Strategy):
        def __init__(self, pairs):
            self.pairs = pairs

        def on_candle(self, t, hist, view):
            return [
                Order(p, "buy", notional=1000.0 / len(self.pairs))
                for p in self.pairs
                if p not in view.positions
            ]

    n = int(years * DAYS)
    idx = pd.date_range("2021-01-01", periods=n, freq="1D", tz="UTC")
    rng = np.random.default_rng(seed)
    pairs = [f"A{i}/USDT" for i in range(8)]
    res: dict = {}
    for sd in (0.02, 0.035, 0.05):
        shares, shut, first = [], 0, []
        for _ in range(paths):
            f = rng.normal(0.0004, sd, n)
            cands = {}
            for p in pairs:
                r = math.sqrt(0.6) * f + math.sqrt(0.4) * rng.normal(0.0, sd, n)
                c = 100.0 * np.exp(np.cumsum(r))
                o = np.concatenate([[100.0], c[:-1]])
                cands[p] = pd.DataFrame(
                    {
                        "date": idx,
                        "open": o,
                        "high": np.maximum(o, c),
                        "low": np.minimum(o, c),
                        "close": c,
                        "volume": 1e12,
                    }
                )
            machine = RiskStateMachine.new(RiskV2Config(), 1000.0)
            out = run(
                RiskManagedStrategy(HoldAll(pairs), machine),
                PriceData(cands, idx),
                ExecConfig(wallet=1000.0),
            )
            shares.append(float((out.exposure > 0.01).mean()))
            sh = next((r for r in machine.records if r["to"] == "SHUTDOWN"), None)
            if sh is not None:
                shut += 1
                first.append((pd.Timestamp(sh["t"]) - idx[0]).days)
        res[f"asset_daily_sd_{sd}"] = {"portfolio_annual_vol_approx": sd * math.sqrt(0.6 + 0.4 / 8) * math.sqrt(DAYS),
                                       "invested_day_share_mean": float(np.mean(shares)),
                                       "invested_day_share_p10": float(np.quantile(shares, 0.1)),
                                       "share_of_paths_shut_down": shut / paths,
                                       "median_day_of_first_shutdown": float(np.median(first)) if first else None}  # fmt: skip
    return res


# ---------------------------------------------------------------------------- Q7 benchmarks
def q7_benchmark_comparisons(reps: int = 200, seed: int = 7, n: int = 1642) -> dict:
    """Behaviour of the comparison machinery under a TRUE NULL: a strategy whose exposure is random (20-day blocks,
    mean 0.5) and independent of returns. Reports (a) how often the paired block-bootstrap Sharpe test rejects against
    the plain benchmark and against the best of 5 correlated baskets (selection makes the bar HIGHER, i.e. the
    comparison is conservative, not flattering); (b) the mean annual Sharpe difference of the no-skill strategy minus its
    benchmark; (c) hindsight of the cash-mix
    comparator: its static share k* is chosen with knowledge of the whole path, so a no-skill strategy that meets the
    20 % drawdown limit and also beats it is rare."""
    import pandas as pd

    from quantlab import benchmarks as bm

    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="1D")
    rej_plain = rej_best = 0
    sdiff, meets_dd, beats_mix = [], 0, 0
    for _ in range(reps):
        common = rng.normal(0.0005, 0.02, n)
        baskets = [
            common + rng.normal(0, 0.012, n) for _ in range(5)
        ]  # pairwise correlation about 0.73
        b = baskets[0]
        e = np.repeat(rng.random(n // 20 + 1), 20)[:n]
        s_ret = e * b
        sa, ba = pd.Series(s_ret, index=idx), pd.Series(b, index=idx)
        rej_plain += bm.compare(sa, ba, n=199, seed=1)["p_one_sided"] <= 0.05
        sharpe = lambda x: x.mean() / x.std(ddof=1)
        best = max(baskets, key=sharpe)
        rej_best += bm.compare(sa, pd.Series(best, index=idx), n=199, seed=1)["p_one_sided"] <= 0.05
        sdiff.append(float(sharpe(s_ret) - sharpe(b)) * math.sqrt(DAYS))
        k = bm.solve_cash_mix(b, 0.20)
        dd_s = bm.max_drawdown_of_mix(s_ret, 1.0)
        if dd_s <= 0.20:
            meets_dd += 1
            beats_mix += float(np.prod(1 + s_ret) - 1) > float(np.prod(1 + k * b) - 1)
    return {"size_vs_plain_benchmark": rej_plain / reps, "size_vs_best_of_5": rej_best / reps,
            "mean_annual_sharpe_difference_no_skill_minus_benchmark": float(np.mean(sdiff)),
            "no_skill_paths_meeting_20pct_drawdown": meets_dd / reps,
            "no_skill_paths_meeting_drawdown_and_beating_cash_mix": beats_mix / reps}  # fmt: skip


def q6b_bounded_sleeve(paths: int = 30, seed: int = 11, years: float = 4.5) -> dict:
    """Does a SMALL constant sleeve (a fraction of the wallet in an equal-weight crypto-like basket, rest cash) stay
    clear of the frozen risk layer? Same synthetic factor model as q6 (note: its geometric drift is harsh at high
    volatility). Reports invested-day share, share of paths shut down and the shutdown causes."""
    import pandas as pd

    from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run
    from quantlab.risk_v2 import RiskManagedStrategy, RiskStateMachine, RiskV2Config

    class Hold(Strategy):
        def __init__(self, pairs, total):
            self.pairs, self.total = pairs, total

        def on_candle(self, t, hist, view):
            return [
                Order(p, "buy", notional=self.total / len(self.pairs))
                for p in self.pairs
                if p not in view.positions
            ]

    n = int(years * DAYS)
    idx = pd.date_range("2021-01-01", periods=n, freq="1D", tz="UTC")
    pairs = [f"A{i}/USDT" for i in range(8)]
    out: dict = {}
    for frac in (1.0, 0.5, 0.25, 0.15):
        for sd in (0.035, 0.05):
            rng = np.random.default_rng(seed)
            shares, shut = [], 0
            causes: dict[str, int] = {}
            for _ in range(paths):
                f = rng.normal(0.0004, sd, n)
                cands = {}
                for p in pairs:
                    r = math.sqrt(0.6) * f + math.sqrt(0.4) * rng.normal(0.0, sd, n)
                    c = 100.0 * np.exp(np.cumsum(r))
                    o = np.concatenate([[100.0], c[:-1]])
                    cands[p] = pd.DataFrame(
                        {
                            "date": idx,
                            "open": o,
                            "high": np.maximum(o, c),
                            "low": np.minimum(o, c),
                            "close": c,
                            "volume": 1e12,
                        }
                    )
                machine = RiskStateMachine.new(RiskV2Config(), 1000.0)
                res = run(
                    RiskManagedStrategy(Hold(pairs, 1000.0 * frac), machine),
                    PriceData(cands, idx),
                    ExecConfig(wallet=1000.0),
                )
                shares.append(float((res.exposure > 0.01).mean()))
                sh = next((r for r in machine.records if r["to"] == "SHUTDOWN"), None)
                if sh is not None:
                    shut += 1
                    causes[sh["cause"]] = causes.get(sh["cause"], 0) + 1
            out[f"fraction_{frac}_asset_daily_sd_{sd}"] = {"invested_day_share_mean": float(np.mean(shares)),
                                                          "share_of_paths_shut_down": shut / paths, "shutdown_causes": causes}  # fmt: skip
    return out


def gate_power_under_exposure(doc: dict, shares: dict[str, tuple[float, float]]) -> dict:
    """Re-run the UNCHANGED gate's power arithmetic (A7) on a pre-registration with other invested-share ranges, e.g.
    those measured in q6 after the frozen risk layer. Arithmetic on declared ranges; nothing is evaluated."""
    import copy

    from quantlab import feasibility as f

    th = f.thresholds()
    out = {}
    for name, (lo, hi) in shares.items():
        x = copy.deepcopy(doc)
        x["expected"]["active_day_share"] = {"lo": lo, "hi": hi}
        p = f.power(x, th)
        out[name] = {"invested_share": [lo, hi], "mde_sharpe_p95": p["mde_sharpe_p95"],
                     "passes_mde_criterion": p["mde_sharpe_p95"] <= th["max_mde_annualised_sharpe_p95"]}  # fmt: skip
    return out


def run_all() -> dict:
    """The stored S7 audit (fixed seeds and repetitions)."""
    return {
        "q1_exposure": q1_exposure_bias(),
        "q2_overlapping_holdings": q2_design_effect(),
        "q3_regime_means": q2_design_effect(regime=True, seed=3),
        "q4_mde_validity": q4_mde_validity(),
        "q5_defensive_timing_power": q5_defensive_timing_power(),
        "q6_exposure_after_frozen_risk_layer": q6_exposure_after_risk_layer(),
        "q6b_bounded_sleeve": q6b_bounded_sleeve(),
        "q7_benchmark_comparisons": q7_benchmark_comparisons(),
        "b2_draft_under_realistic_exposure": gate_power_under_exposure(
            json.loads(
                (_ROOT / "docs/phase4c/proposals/b2_draft_preregistration.json").read_text(
                    encoding="utf-8"
                )
            ),
            {
                "declared_0.90_1.00": (0.9, 1.0),
                "risk_layer_31pct_vol_0.50_0.80": (0.5, 0.8),
                "risk_layer_54pct_vol_0.25_0.50": (0.25, 0.5),
                "risk_layer_77pct_vol_0.20_0.45": (0.2, 0.45),
            },
        ),
    }


if __name__ == "__main__":
    import sys

    out = run_all()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(out, indent=1, sort_keys=True))
