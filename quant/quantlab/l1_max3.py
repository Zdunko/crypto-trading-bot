"""L1 signal test for H1 (lottery-demand avoidance, MAX3 over a fixed 28-day window).

Pure functions on a daily panel (arrays), so every rule is testable on synthetic data. The registered rules are in
``protocol/h1_l1_preregistration.json``; this module implements them and nothing else. Nothing here optimises or
searches: one formula, one window, two horizons.

Conventions: day index t = the daily candle opening on date t (it completes at t+1 00:00 UTC). The signal of day t
is computed at that completion from candles <= t; the (hypothetical) entry is the open of day t+1.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from quantlab.design_study import block_boot_p


QUANT = Path(__file__).resolve().parents[1]
PREREG = QUANT / "protocol/h1_l1_preregistration.json"
N = NormalDist()
Z95 = N.inv_cdf(0.95)
Z975 = N.inv_cdf(0.975)


@dataclass
class Panel:
    dates: pd.DatetimeIndex  # candle open dates, contiguous daily, UTC
    symbols: list[str]
    open: np.ndarray  # T x S, NaN = no candle
    close: np.ndarray
    member: np.ndarray  # T x S bool: point-in-time universe member on that date
    epoch_start: (
        np.ndarray
    )  # T x S int: first day index of the identity epoch containing the date, -1 if none


# ------------------------------------------------------------------------------------------ signal
def max3(close: np.ndarray, epoch_start: np.ndarray, window: int = 28, k: int = 3) -> np.ndarray:
    """S[t] = -(mean of the k largest daily simple returns over the ``window`` days ending at t).
    Invalid (NaN) unless all ``window`` returns exist, the prices are positive and the whole window lies inside
    one identity epoch. Higher S = less lottery-like."""
    t_n, s_n = close.shape
    out = np.full((t_n, s_n), np.nan)
    if t_n <= window:
        return out
    with np.errstate(invalid="ignore", divide="ignore"):
        ret = close[1:] / close[:-1] - 1.0
    ret[~(close[1:] > 0) | ~(close[:-1] > 0)] = np.nan
    for a in range(0, s_n, 100):
        w = sliding_window_view(ret[:, a : a + 100], window, axis=0)  # (T-window, s, window)
        ok = np.isfinite(w).all(axis=2)
        top = np.partition(np.where(np.isfinite(w), w, -np.inf), window - k, axis=2)[:, :, -k:]
        val = -top.mean(axis=2)
        val[~ok] = np.nan
        out[window:, a : a + 100] = val
    t_idx = np.arange(t_n)[:, None]
    out[~((epoch_start >= 0) & (epoch_start <= t_idx - window))] = np.nan
    return out


def forward_returns(
    open_: np.ndarray, close: np.ndarray, h: int, delist_return: float | None = None
) -> np.ndarray:
    """R[t] = open[t+1+h] / open[t+1] - 1 (open to open). If the exit candle is missing (gap or delisting) the exit is
    the last observed close in [t+1, t+h] (no recovery or jump is invented). With ``delist_return`` set (sensitivity:
    -1.0 = zero recovery) an asset that has no candle at all from t+1+h on gets that return instead."""
    t_n, s_n = open_.shape
    out = np.full((t_n, s_n), np.nan)
    last_finite = np.full(s_n, -1)
    for s in range(s_n):
        idx = np.where(np.isfinite(open_[:, s]))[0]
        last_finite[s] = idx[-1] if len(idx) else -1
    for t in range(t_n - 1 - h):
        entry = open_[t + 1]
        exit_ = open_[t + 1 + h].copy()
        miss = ~np.isfinite(exit_) & np.isfinite(entry)
        if miss.any():
            win = close[t + 1 : t + 1 + h]
            for s in np.where(miss)[0]:
                fin = np.where(np.isfinite(win[:, s]))[0]
                exit_[s] = win[fin[-1], s] if len(fin) else np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            r = exit_ / entry - 1.0
        r[~(entry > 0)] = np.nan
        if delist_return is not None:
            ended = (last_finite < t + 1 + h) & np.isfinite(entry)
            r[ended] = delist_return
        out[t] = r
    return out


# ------------------------------------------------------------------------------------------ statistics
def rank_ic(x: np.ndarray, y: np.ndarray, mask: np.ndarray, min_n: int) -> tuple[float, int]:
    """Cross-sectional Spearman = Pearson of average ranks (ties averaged). NaN if fewer than ``min_n`` valid assets
    or a constant cross-section."""
    m = mask & np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < min_n:
        return float("nan"), n
    rx = pd.Series(x[m]).rank(method="average").to_numpy()
    ry = pd.Series(y[m]).rank(method="average").to_numpy()
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return float("nan"), n
    return float(np.mean((rx - rx.mean()) * (ry - ry.mean())) / (sx * sy)), n


def ic_series(
    sig: np.ndarray, ret: np.ndarray, member: np.ndarray, min_n: int
) -> tuple[np.ndarray, np.ndarray]:
    t_n = sig.shape[0]
    ic, cnt = np.full(t_n, np.nan), np.zeros(t_n, dtype=int)
    for t in range(t_n):
        ic[t], cnt[t] = rank_ic(sig[t], ret[t], member[t], min_n)
    return ic, cnt


def newey_west(x: np.ndarray, lag: int) -> tuple[float, float, float]:
    """(mean, standard error of the mean, naive standard error) with Bartlett weights."""
    x = x[np.isfinite(x)]
    n = len(x)
    d = x - x.mean()
    var = float(np.mean(d * d))
    long_run = var
    for k in range(1, lag + 1):
        long_run += 2.0 * (1.0 - k / (lag + 1)) * float(np.mean(d[k:] * d[:-k]))
    long_run = max(long_run, 1e-300)
    return float(x.mean()), math.sqrt(long_run / n), math.sqrt(max(var, 1e-300) / n)


def holm(p: list[float]) -> list[float]:
    order = sorted(range(len(p)), key=lambda i: p[i])
    adj, run = [0.0] * len(p), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(p) - rank) * p[i]))
        adj[i] = run
    return adj


def test_series(ic: np.ndarray, lag: int, boot_draws: int, boot_seed: int) -> dict:
    x = ic[np.isfinite(ic)]
    mean, se, naive_se = newey_west(x, lag)
    t = mean / se
    p = 1.0 - N.cdf(t)
    out = {
        "n_days": len(x),
        "mean_ic": mean,
        "median_ic": float(np.median(x)),
        "hac_lag": lag,
        "hac_se": se,
        "naive_se": naive_se,
        "t_hac": t,
        "p_one_sided_raw": p,
        "ci95_two_sided": [mean - Z975 * se, mean + Z975 * se],
        "lower95_one_sided": mean - Z95 * se,
        "effective_n_days": float(len(x) * (naive_se / se) ** 2),
    }
    bl = max(lag, 2)
    rng = np.random.default_rng(boot_seed)
    out["bootstrap_p_one_sided"] = float(block_boot_p((x - 0.0)[None, :], rng, bl, boot_draws)[0])
    out["bootstrap_block"] = bl
    return out


# ------------------------------------------------------------------------------------------ disguise references
def _roll(a: np.ndarray, n: int, fn) -> np.ndarray:
    out = np.full_like(a, np.nan, dtype=float)
    if a.shape[0] >= n:
        out[n - 1 :] = fn(sliding_window_view(a, n, axis=0))
    return out


def reference_signals(close: np.ndarray) -> dict[str, np.ndarray]:
    """Cross-sectional ranks of styles of the rejected families, from daily closes only (see the registration)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        ret = np.vstack([np.full((1, close.shape[1]), np.nan), close[1:] / close[:-1] - 1.0])
        ret7, ret28 = np.full_like(close, np.nan), np.full_like(close, np.nan)
        ret7[7:] = close[7:] / close[:-7] - 1.0
        ret28[28:] = close[28:] / close[:-28] - 1.0
        gain, loss = np.where(ret > 0, ret, 0.0), np.where(ret < 0, -ret, 0.0)
        gain[~np.isfinite(ret)], loss[~np.isfinite(ret)] = np.nan, np.nan
        g14, l14 = (
            _roll(gain, 14, lambda w: w.mean(axis=2)),
            _roll(loss, 14, lambda w: w.mean(axis=2)),
        )
        rsi14 = g14 / (g14 + l14)  # Cutler (simple-average) RSI
        donch = close / _roll(close, 20, lambda w: w.max(axis=2))
        df = pd.DataFrame(close)
        ema = (
            df.ewm(span=12, adjust=False).mean().to_numpy()
            / df.ewm(span=26, adjust=False).mean().to_numpy()
            - 1.0
        )
        vol28 = _roll(ret, 28, lambda w: w.std(axis=2))
    return {"trailing_return_7d": ret7, "trailing_return_28d": ret28, "rsi14_cutler": rsi14,
            "donchian20_position": donch, "ema12_26_gap": ema, "realised_vol_28d_informational": vol28}  # fmt: skip


def disguise(
    sig: np.ndarray,
    close: np.ndarray,
    member: np.ndarray,
    valid_from: int,
    min_n: int,
    bound: float,
) -> dict:
    out: dict = {}
    for name, ref in reference_signals(close).items():
        rhos = np.array(
            [rank_ic(sig[t], ref[t], member[t], min_n)[0] for t in range(valid_from, sig.shape[0])]
        )
        rhos = rhos[np.isfinite(rhos)]
        m = float(rhos.mean()) if len(rhos) else float("nan")
        out[name] = {"mean_rank_corr": m, "share_days_abs_above_bound": float(np.mean(np.abs(rhos) > bound)) if len(rhos) else None,
                     "days": len(rhos), "gating": not name.endswith("informational")}  # fmt: skip
    gating = [v["mean_rank_corr"] for v in out.values() if v["gating"]]
    out["max_abs_mean_rank_corr_gating"] = (
        float(max(abs(g) for g in gating)) if gating else float("nan")
    )
    out["passes"] = bool(gating) and out["max_abs_mean_rank_corr_gating"] <= bound
    return out


# ------------------------------------------------------------------------------------------ one configuration
def evaluate(panel: Panel, spec: dict, h: int, seed_offset: int = 0) -> dict:
    sg, st = spec["signal"], spec["statistics"]
    sig = max3(panel.close, panel.epoch_start, sg["window_days"], sg["top_k"])
    first, last_open = (
        spec["evaluation"]["first_signal_date"],
        spec["evaluation"]["last_candle_open"],
    )
    dates = panel.dates
    t0 = int(dates.searchsorted(pd.Timestamp(first, tz="UTC")))
    last_sig = dates.searchsorted(pd.Timestamp(last_open, tz="UTC")) - (1 + h)
    ret = forward_returns(panel.open, panel.close, h)
    ret_zero = forward_returns(panel.open, panel.close, h, delist_return=-1.0)
    member = panel.member
    ic, cnt = ic_series(sig, ret, member, st["min_assets_per_day"])
    ic_zero, _ = ic_series(sig, ret_zero, member, st["min_assets_per_day"])
    rng_mask = np.zeros(len(dates), dtype=bool)
    rng_mask[t0 : last_sig + 1] = True
    ic = np.where(rng_mask, ic, np.nan)
    ic_zero = np.where(rng_mask, ic_zero, np.nan)
    lag = st["hac_lag_multiplier"] * h
    res = test_series(ic, lag, st["bootstrap_draws"], st["bootstrap_seed"] + seed_offset)
    res["sensitivity_delisting_zero_recovery"] = {"mean_ic": float(np.nanmean(ic_zero)),
        "t_hac": float(np.nanmean(ic_zero) / newey_west(ic_zero, lag)[1])}  # fmt: skip
    # sub-periods and regimes (fixed ex ante)
    sub = {}
    for name, (a, b) in spec["evaluation"]["subperiods"].items():
        i0, i1 = (
            int(dates.searchsorted(pd.Timestamp(a, tz="UTC"))),
            int(dates.searchsorted(pd.Timestamp(b, tz="UTC"), side="right")),
        )
        seg = ic[i0:i1]
        seg = seg[np.isfinite(seg)]
        sub[name] = {"n_days": len(seg), "mean_ic": float(seg.mean()) if len(seg) else None,
                     "t_hac": float(seg.mean() / newey_west(seg, lag)[1]) if len(seg) > lag + 5 else None}  # fmt: skip
    res["subperiods"] = sub
    reg_cfg = spec["evaluation"]["regime"]
    btc = (
        panel.symbols.index(reg_cfg["reference_symbol"])
        if reg_cfg["reference_symbol"] in panel.symbols
        else None
    )
    if btc is not None:
        lb = reg_cfg["lookback_days"]
        c = panel.close[:, btc]
        reg = np.full(len(dates), np.nan)
        reg[lb:] = c[lb:] / c[:-lb] - 1.0
        regimes = {}
        for name, sel in (("up", reg > 0), ("down", reg <= 0)):
            seg = ic[sel & np.isfinite(ic)]
            regimes[name] = {
                "n_days": len(seg),
                "mean_ic": float(seg.mean()) if len(seg) else None,
            }
        res["regimes_btc_trailing_return_sign"] = regimes
    # coverage and missing observations
    valid_days = np.isfinite(ic)
    res["cross_section"] = {
        "mean_assets_per_valid_day": float(cnt[valid_days].mean()) if valid_days.any() else 0.0,
        "min_assets_per_valid_day": int(cnt[valid_days].min()) if valid_days.any() else 0,
        "days_in_range": int(rng_mask.sum()),
        "days_skipped_too_few_assets": int((rng_mask & ~valid_days).sum()),
    }
    in_rng = rng_mask[:, None] & member
    both = in_rng & np.isfinite(sig) & np.isfinite(ret)
    res["coverage"] = {
        "member_days_in_range": int(in_rng.sum()),
        "member_days_with_valid_signal": int((in_rng & np.isfinite(sig)).sum()),
        "member_days_with_valid_signal_and_return": int(both.sum()),
        "coverage_ratio": float(both.sum() / max(in_rng.sum(), 1)),
        "member_days_missing_signal": int((in_rng & ~np.isfinite(sig)).sum()),
        "member_days_missing_return": int((in_rng & ~np.isfinite(ret)).sum()),
        "distinct_assets_with_valid_observation": int(both.any(axis=0).sum()),
    }
    res["horizon_days"] = h
    res["last_signal_index"] = last_sig
    return res


def decide(spec: dict, results: dict[str, dict], disguise_res: dict, checks_ok: bool) -> dict:
    """Pre-registered decision. L1 PASS only if one configuration passes every criterion after Holm correction."""
    crit, st = spec["criteria"], spec["statistics"]
    names = sorted(results)
    holm_p = holm([results[n]["p_one_sided_raw"] for n in names])
    out: dict = {"configurations": {}}
    for n, hp in zip(names, holm_p, strict=True):
        r = results[n]
        h = r["horizon_days"]
        thr = crit["practical_threshold_per_day_ic"] * math.sqrt(h)
        gates = {
            "sample_days": r["n_days"] >= st["min_valid_ic_days"],
            "mean_assets": r["cross_section"]["mean_assets_per_valid_day"] >= st["min_mean_assets"],
            "coverage": r["coverage"]["coverage_ratio"] >= st["min_coverage_ratio"],
        }
        subs = [v["mean_ic"] for v in r["subperiods"].values()]
        conds = {
            "data_gates": all(gates.values()),
            "holm_p_le_alpha": hp <= crit["alpha_family"],
            "practical_mean_ic_ge_threshold": r["mean_ic"] >= thr,
            "positive_in_every_subperiod": all(s is not None and s > 0 for s in subs),
        }
        out["configurations"][n] = {"p_holm": hp, "practical_threshold_mean_ic": thr, "gates": gates,
                                    "criteria": conds, "passes": all(conds.values())}  # fmt: skip
    out["disguise_passes"] = bool(disguise_res["passes"])
    out["reproducibility_and_causality_checks_ok"] = bool(checks_ok)
    out["L1_PASS"] = bool(
        any(c["passes"] for c in out["configurations"].values())
        and out["disguise_passes"]
        and checks_ok
    )
    out["decision"] = (
        "L1 PASS"
        if out["L1_PASS"]
        else "NO-GO: H1 is terminated (no variants, windows, horizons or filters)"
    )
    return out


# ------------------------------------------------------------------------------------------ loading
def load_panel(ds, spec: dict) -> Panel:
    """Daily panel from the frozen PIT dataset (verified, completed candles only; the loader refuses the holdout)."""
    from quantlab import pit_loader as pl

    ev, un = spec["evaluation"], spec["universe"]
    first = pd.Timestamp(ev["panel_first_candle_open"], tz="UTC")
    last = pd.Timestamp(ev["last_candle_open"], tz="UTC")
    dates = pd.date_range(first, last, freq="1D", tz="UTC")
    months = sorted({d.strftime("%Y-%m") for d in dates})
    member_by_month = {
        m: set(
            ds.universe_at(pd.Timestamp(m + "-01", tz="UTC"), un["threshold"], un["max_stale_days"])
        )
        for m in months
    }
    symbols = sorted(
        set().union(*member_by_month.values()) | {spec["evaluation"]["regime"]["reference_symbol"]}
    )
    as_of = last + pd.Timedelta(days=1)
    o, c = np.full((len(dates), len(symbols)), np.nan), np.full((len(dates), len(symbols)), np.nan)
    for j, s in enumerate(symbols):
        df = ds.candles(s, "1d", as_of, start=first, allow_gaps=True)
        pos = dates.get_indexer(df["date"])
        ok = pos >= 0
        o[pos[ok], j], c[pos[ok], j] = df["open"].to_numpy()[ok], df["close"].to_numpy()[ok]
    member = np.zeros(o.shape, dtype=bool)
    mon_idx = np.array([d.strftime("%Y-%m") for d in dates])
    for m, mem in member_by_month.items():
        sel = mon_idx == m
        for j, s in enumerate(symbols):
            if s in mem:
                member[sel, j] = True
    epoch_start = np.full(o.shape, -1, dtype=int)
    with gzip.open(Path(ds.dataset_dir) / "epochs.csv.gz", "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["symbol"] not in symbols:
                continue
            j = symbols.index(r["symbol"])
            a = pd.Timestamp(int(r["start_ms"]), unit="ms", tz="UTC")
            b = pd.Timestamp(
                int(r["end_ms"]), unit="ms", tz="UTC"
            )  # end of the last candle (exclusive)
            i0, i1 = int(dates.searchsorted(a)), int(dates.searchsorted(b))
            epoch_start[i0:i1, j] = i0  # an epoch that began before the panel starts at index 0
    _ = pl  # the import documents that every read goes through the verified loader
    return Panel(dates, symbols, o, c, member, epoch_start)


def spec_sha256(spec: dict) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
