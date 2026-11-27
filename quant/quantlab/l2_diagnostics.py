"""M4 verification diagnostics of the L1 result (registered in ``protocol/m4_l2_preregistration.json``; run once, inside the
single approved replay): independent re-implementation, within-day permutation placebo, one-day-delayed entry, survivorship
split and a liquidity split. They answer 'is the unexpectedly large IC an artefact?'; they never change any verdict."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantlab import l1_max3 as l1


def _range(panel: l1.Panel, l1spec: dict, h: int) -> np.ndarray:
    ev = l1spec["evaluation"]
    t0 = int(panel.dates.searchsorted(pd.Timestamp(ev["first_signal_date"], tz="UTC")))
    last = int(panel.dates.searchsorted(pd.Timestamp(ev["last_candle_open"], tz="UTC"))) - (1 + h)
    m = np.zeros(len(panel.dates), dtype=bool)
    m[t0 : last + 1] = True
    return m


def _summ(ic: np.ndarray, rng_mask: np.ndarray, lag: int) -> dict:
    x = np.where(rng_mask, ic, np.nan)
    x = x[np.isfinite(x)]
    if len(x) <= lag + 5:
        return {"n_days": len(x), "mean_ic": None, "t_hac": None}
    mean, se, _ = l1.newey_west(x, lag)
    return {"n_days": len(x), "mean_ic": mean, "t_hac": mean / se}


def independent_ic(panel: l1.Panel, l1spec: dict, h: int) -> np.ndarray:
    """Re-implementation with pandas (rolling windows, row-wise rank correlation); shares no code with ``l1_max3``."""
    sg, st = l1spec["signal"], l1spec["statistics"]
    close = pd.DataFrame(panel.close, index=panel.dates)
    open_ = pd.DataFrame(panel.open, index=panel.dates)
    ret = close.pct_change(fill_method=None)
    top = ret.rolling(sg["window_days"]).apply(
        lambda w: np.sort(w)[-sg["top_k"] :].mean() if np.isfinite(w).all() else np.nan, raw=True
    )
    t_idx = np.arange(len(panel.dates))[:, None]
    epoch_ok = (panel.epoch_start >= 0) & (panel.epoch_start <= t_idx - sg["window_days"])
    sig = (-top).where(pd.DataFrame(epoch_ok, index=panel.dates))
    entry = open_.shift(-1)
    exit_open = open_.shift(-(1 + h))
    last_obs = close.ffill().shift(-h)
    exit_ = exit_open.where(exit_open.notna(), last_obs)
    fwd = exit_ / entry - 1.0
    fwd = fwd.where(entry > 0)
    mem = pd.DataFrame(panel.member, index=panel.dates)
    ok = mem & sig.notna() & fwd.notna()
    rs, rr = sig.where(ok).rank(axis=1), fwd.where(ok).rank(axis=1)
    n = ok.sum(axis=1)
    ic = rs.corrwith(rr, axis=1)
    ic[n < st["min_assets_per_day"]] = np.nan
    return ic.to_numpy()


def permutation_placebo(
    sig: np.ndarray,
    ret: np.ndarray,
    member: np.ndarray,
    rng_mask: np.ndarray,
    min_n: int,
    reps: int,
    seed: int,
    lag: int,
) -> dict:
    rng = np.random.default_rng(seed)
    days = []
    for t in np.where(rng_mask)[0]:
        m = member[t] & np.isfinite(sig[t]) & np.isfinite(ret[t])
        if m.sum() < min_n:
            continue
        rx = pd.Series(sig[t][m]).rank().to_numpy()
        ry = pd.Series(ret[t][m]).rank().to_numpy()
        days.append((rx, ry - ry.mean(), float(((ry - ry.mean()) ** 2).sum())))
    means = np.empty(reps)
    for r in range(reps):
        acc = []
        for rx, ryc, syy in days:
            p = rng.permutation(rx)
            pc = p - p.mean()
            den = np.sqrt(float((pc**2).sum()) * syy)
            acc.append(float((pc * ryc).sum() / den) if den > 0 else np.nan)
        means[r] = np.nanmean(acc)
    return {
        "reps": reps,
        "mean_of_means": float(means.mean()),
        "sd_of_means": float(means.std(ddof=1)),
        "max_abs_mean": float(np.abs(means).max()),
        "days": len(days),
    }


def run_diagnostics(ds, panel: l1.Panel, spec: dict, l1spec: dict, qvol: np.ndarray) -> dict:
    dg = spec["diagnostics"]
    sg, st = l1spec["signal"], l1spec["statistics"]
    sig = l1.max3(panel.close, panel.epoch_start, sg["window_days"], sg["top_k"])
    out: dict = {}
    # failed vs surviving assets: no candle during the last 30 days of the panel
    tail = np.isfinite(panel.open[-30:]).any(axis=0)
    survivors = tail
    # trailing 90-day median quote volume (completed days only; the value at day t uses days <= t)
    med = pd.DataFrame(qvol).rolling(90, min_periods=60).median().to_numpy()
    for cfg in spec["configurations"]:
        h = cfg["horizon_days"]
        lag = st["hac_lag_multiplier"] * h
        rng_mask = _range(panel, l1spec, h)
        ret = l1.forward_returns(panel.open, panel.close, h)
        ic_reg, _ = l1.ic_series(sig, ret, panel.member, st["min_assets_per_day"])
        d: dict = {"registered": _summ(ic_reg, rng_mask, lag)}
        ind = independent_ic(panel, l1spec, h)
        both = np.isfinite(ic_reg) & np.isfinite(ind) & rng_mask
        d["V1_independent_reimplementation"] = {
            "days_compared": int(both.sum()), "max_abs_daily_ic_difference": float(np.max(np.abs(ic_reg[both] - ind[both]))) if both.any() else None,
            "mean_ic_independent": float(np.nanmean(np.where(rng_mask, ind, np.nan))),
            "days_finite_only_in_registered": int((np.isfinite(ic_reg) & ~np.isfinite(ind) & rng_mask).sum()),
            "days_finite_only_in_independent": int((~np.isfinite(ic_reg) & np.isfinite(ind) & rng_mask).sum()),
            "tolerance": dg["V1_tolerance"]}  # fmt: skip
        d["V2_permutation_placebo"] = permutation_placebo(
            sig,
            ret,
            panel.member,
            rng_mask,
            st["min_assets_per_day"],
            dg["permutation_reps"],
            dg["permutation_seed"] + h,
            lag,
        )
        delayed = l1.forward_returns(panel.open[1:], panel.close[1:], h)
        delayed = np.vstack([delayed, np.full((1, delayed.shape[1]), np.nan)])
        ic_del, _ = l1.ic_series(sig, delayed, panel.member, st["min_assets_per_day"])
        d["V2_entry_delayed_one_day"] = _summ(ic_del, rng_mask, lag)
        ic_sv, _ = l1.ic_series(
            sig, ret, panel.member & survivors[None, :], st["min_assets_per_day"]
        )
        d["V3_survivors_only"] = {**_summ(ic_sv, rng_mask, lag), "assets_surviving": int(survivors.sum()), "assets_failed": int((~survivors).sum()),
            "share_member_days_failed_assets": float((panel.member & ~survivors[None, :] & rng_mask[:, None]).sum() / max((panel.member & rng_mask[:, None]).sum(), 1))}  # fmt: skip
        mem_med = np.where(panel.member, med, np.nan)
        cut = np.nanmedian(mem_med, axis=1)[:, None]
        liquid = panel.member & (med >= cut)
        illiquid = panel.member & (med < cut)
        d["V4_liquid_half"] = _summ(
            l1.ic_series(sig, ret, liquid, st["min_assets_per_day"] // 2)[0], rng_mask, lag
        )
        d["V4_illiquid_half"] = _summ(
            l1.ic_series(sig, ret, illiquid, st["min_assets_per_day"] // 2)[0], rng_mask, lag
        )
        full = d["registered"]["mean_ic"]
        d["flags"] = {
            "implementation_matches": bool(d["V1_independent_reimplementation"]["max_abs_daily_ic_difference"] is not None
                                           and d["V1_independent_reimplementation"]["max_abs_daily_ic_difference"] <= dg["V1_tolerance"]),
            "observed_ic_beyond_placebo": bool(full > d["V2_permutation_placebo"]["max_abs_mean"]),
            "survivors_only_retains_half": bool(d["V3_survivors_only"]["mean_ic"] is not None and d["V3_survivors_only"]["mean_ic"] >= 0.5 * full),
            "liquid_half_retains_half": bool(d["V4_liquid_half"]["mean_ic"] is not None and d["V4_liquid_half"]["mean_ic"] >= 0.5 * full),
        }  # fmt: skip
        out[cfg["id"]] = d
    return out
