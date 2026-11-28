"""
Family A market evaluation runner (ONE research CI run, evaluation period only).

    python -m quantlab.family_a_eval

Runs exactly what protocol_v5_family_a.json (+ amendment A1) prescribes: A1, A0, V0 with the breaker ON
at base costs and A1 at double costs; benchmarks B1-B5; T1-T10; statistical screen; causality checks
(T10 for a stateful engine strategy); breaker impact. The holdout is never loaded: candles are cut at
the evaluation end before anything is built. No parameter is read from results.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

from quantlab import causality, stats
from quantlab import protocol as protocol_mod
from quantlab.costs import BASE, STRESS
from quantlab.execution import PriceData, Result
from quantlab.family_a import VARIANTS, FamilyAStrategy, episodes, exec_config, run_family_a
from quantlab.metrics import daily_returns, monthly_returns, sharpe, summarize, with_start
from quantlab.phase3 import emit, load_candles
from quantlab.phase4 import bench_threshold, benchmark_set
from quantlab.validation import (
    calendar_windows,
    daily_regimes,
    evaluate_criteria,
    pair_profit_shares,
    regime_stats,
    window_stats,
)


N_TRIALS = 43  # 40 ledger configurations + A1, A0, V0
CUTS_MUTATION = ("2022-01-01", "2024-01-01")  # prices and volumes randomised from here
CUT_VOLUME_ONLY = "2023-01-01"
CUT_RESTART = "2023-07-01"


def guard() -> tuple[dict, dict]:
    errs = protocol_mod.consistency_errors() + protocol_mod.verify_all()
    if errs:
        print("PROTOCOL / AMENDMENT CHECK FAILED:\n" + "\n".join(errs), file=sys.stderr)
        raise SystemExit(1)
    spec = json.loads(
        (protocol_mod.QUANT_DIR / "protocol" / "protocol_v5_family_a.json").read_text()
    )
    return protocol_mod.load_protocol(), spec


def load_research_candles(proto: dict) -> dict[str, pd.DataFrame]:
    """Candles strictly before the holdout start; asserts that no later row survives."""
    cut = pd.Timestamp(proto["periods"]["evaluation"]["end_exclusive"], tz="UTC")
    out = {}
    for pair, df in load_candles(proto).items():
        d = pd.to_datetime(df["date"], utc=True)
        out[pair] = df[d < cut].reset_index(drop=True)
        if (d[d < cut] >= cut).any():
            raise SystemExit("holdout candle leaked into the research data")
    return out


def ep_frame(trades: pd.DataFrame) -> pd.DataFrame:
    """Position episodes in the shape the validation library expects."""
    if trades.empty:
        return pd.DataFrame(
            columns=["pair", "open_date", "close_date", "profit_abs", "profit_ratio", "open_value"]
        )
    ep = episodes(trades)
    ep["profit_ratio"] = ep["profit_abs"] / ep["cost"]
    ep["open_value"] = ep["cost"]
    return ep


def fmt_series(s: pd.Series) -> list[float]:
    return [round(float(x), 2) for x in s.resample("1D").last().dropna()]


def paired_pvalue(a: np.ndarray, b: np.ndarray, n: int, seed: int, block: int) -> float:
    """One-sided p for 'Sharpe(a) <= Sharpe(b)': circular block bootstrap, same blocks for both."""
    t = len(a)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(t / block))
    starts = rng.integers(0, t, size=(n, nb))
    idx = ((starts[:, :, None] + np.arange(block)) % t).reshape(n, -1)[:, :t]
    diff = np.array([sharpe(a[i]) - sharpe(b[i]) for i in idx])
    diff = diff[np.isfinite(diff)]
    return float((np.sum(diff <= 0) + 1) / (len(diff) + 1))


def breaker_impact(res: Result, start: pd.Timestamp) -> dict:
    halts = [e for e in res.breaker_events if e["type"] == "halt"]
    liq = res.trades[res.trades["exit_reason"] == "halt"] if not res.trades.empty else res.trades
    out: dict = {
        "halts": halts,
        "resumes": [e for e in res.breaker_events if e["type"] == "resume"],
    }
    out["entries_blocked"] = sum(1 for r in res.rejects if r["reason"] == "halted")
    if halts:
        t_halt = pd.Timestamp(halts[0]["time"])
        end = res.equity.index[-1]
        out["period_traded_share"] = float((t_halt - start) / (end + pd.Timedelta("1h") - start))
        out["days_flat_after_halt"] = float(
            (end + pd.Timedelta("1h") - (liq["close_date"].max() if len(liq) else t_halt)).days
        )
        out["liquidation"] = {
            "fills": len(liq),
            "candles_to_flat": int((liq["close_date"].max() - t_halt) / pd.Timedelta("1h")) + 1
            if len(liq)
            else 0,
            "net_pnl": float(liq["profit_abs"].sum()) if len(liq) else 0.0,
            "positions": sorted(set(liq["pair"])) if len(liq) else [],
            "by_fill": [
                {
                    "time": str(r.close_date),
                    "pair": r.pair,
                    "amount": float(r.amount),
                    "price": float(r.close_rate),
                    "pnl": float(r.profit_abs),
                }
                for r in liq.itertuples()
            ],
        }
    else:
        out["period_traded_share"] = 1.0
    return out


def cost_accounting(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"total_cost": 0.0}
    gross = (trades["amount"] * (trades["close_rate"] - trades["open_rate"])).sum()
    net = trades["profit_abs"].sum()
    traded = (2 * trades["open_value"] + trades["profit_abs"]).sum()
    return {
        "gross_profit_at_reference": float(gross),
        "net_profit": float(net),
        "total_cost": float(gross - net),
        "traded_notional": float(traded),
    }


def run_all(proto: dict, spec: dict, candles: dict | None = None, cuts: dict | None = None) -> dict:
    wallet = float(proto["initial_wallet"])
    per = proto["periods"]["evaluation"]
    start, end = per["start"], per["end_exclusive"]
    candles = load_research_candles(proto) if candles is None else candles
    cuts = cuts or {"mutation": CUTS_MUTATION, "volume": CUT_VOLUME_ONLY, "restart": CUT_RESTART}
    index_eval = pd.date_range(start, end, freq="1h", inclusive="left", tz="UTC")
    t_start = pd.Timestamp(start, tz="UTC")

    # ---- benchmarks (legacy, base costs, NO breaker and NO liquidity cap: disclosed)
    from quantlab.equity import buy_and_hold

    _, chosen = buy_and_hold(candles, index_eval, wallet, BASE)
    ctx = SimpleNamespace(candles=candles, index=index_eval, bench_pairs=chosen)
    bench = benchmark_set(ctx, wallet)
    bench_stats = {k: summarize(v, None, wallet) for k, v in bench.items()}
    thr = bench_threshold(bench_stats)

    # ---- variants
    runs: dict[str, Result] = {}
    for name in ("A1", "A0", "V0"):
        runs[name] = run_family_a(candles, start, end, name, exec_config())
    runs["A1_stress"] = run_family_a(candles, start, end, "A1", exec_config(costs=STRESS))

    regimes = daily_regimes(
        candles[proto["regime"]["proxy_pair"]],
        proto["regime"]["ema_period"],
        proto["regime"]["adx_trend"],
    )
    windows = calendar_windows(
        start, end, proto["walk_forward"]["months"], proto["walk_forward"]["min_tail_months"]
    )
    bs = proto["bootstrap"]

    daily = {k: daily_returns(with_start(r.equity, wallet)).to_numpy() for k, r in runs.items()}
    daily_b = {k: daily_returns(with_start(v, wallet)).to_numpy() for k, v in bench.items()}
    pbo = stats.pbo_cscv(np.column_stack([daily[k] for k in ("A1", "A0", "V0")]), 16)

    # ---- causality (T10 for a stateful engine strategy), identical for every variant
    n_all = len(candles)
    caus: dict[str, dict] = {}
    full_index = pd.date_range(
        min(pd.to_datetime(d["date"], utc=True).min() for d in candles.values()).floor("1D"),
        pd.Timestamp(end, tz="UTC"),
        freq="1h",
        inclusive="left",
    )
    i0 = int(full_index.searchsorted(t_start))
    data_full = PriceData(candles, full_index)
    for name in ("A1", "A0", "V0"):
        mk = lambda d, name=name: FamilyAStrategy(VARIANTS[name], n_all)  # noqa: E731
        checks = {}
        for cut in cuts["mutation"]:
            checks[f"mutation_prices_and_volumes_{cut}"] = causality.mutation_mismatches_at(
                mk, candles, full_index, exec_config(), pd.Timestamp(cut, tz="UTC"), start=i0
            )
        checks[f"mutation_volumes_only_{CUT_VOLUME_ONLY}"] = causality.mutation_mismatches_at(
            mk,
            candles,
            full_index,
            exec_config(),
            pd.Timestamp(CUT_VOLUME_ONLY, tz="UTC"),
            start=i0,
            prices=False,
        )
        k = int(full_index.searchsorted(pd.Timestamp(cuts["restart"], tz="UTC")))
        checks[f"restart_{cuts['restart']}"] = causality.restart_mismatches_at(
            lambda name=name: FamilyAStrategy(VARIANTS[name], n_all),
            data_full,
            exec_config(),
            i0,
            k,
        )
        caus[name] = {"checks": checks, "clean": all(len(v) == 0 for v in checks.values())}

    out: dict = {
        "period": per,
        "benchmarks": bench_stats,
        "bench_threshold": thr,
        "pbo_cscv": pbo,
        "trials": N_TRIALS,
        "variants": {},
        "causality": caus,
    }
    rules = json.loads(
        (protocol_mod.QUANT_DIR / "protocol" / "protocol_v4_stats.json").read_text()
    )["stat_screen"]
    p_h2 = paired_pvalue(
        daily["A1"], daily_b["B1 equal-weight all 8"], bs["n"], bs["seed"], bs["block_days"]
    )

    for name, res in runs.items():
        ep = ep_frame(res.trades)
        s = summarize(res.equity, ep if len(ep) else None, wallet)
        s.setdefault("trades", 0)
        s.setdefault("profit_factor", float("nan"))
        ret = daily[name]
        years = len(ret) / 365.0
        net = float(res.equity.iloc[-1] / wallet - 1)
        v: dict = {
            "stats": s,
            "annualised_return": float((1 + net) ** (1 / years) - 1) if net > -1 else -1.0,
            "exposure_avg": float(res.exposure.mean()),
            "exposure_peak": float(res.exposure.max()),
            "monthly": monthly_returns(res.equity, wallet).round(4).to_dict(),
            "windows": window_stats(res.equity, windows, wallet),
            "pair_profit_share": pair_profit_shares(ep) if len(ep) else {},
            "regimes_trades": regime_stats(ep, regimes) if len(ep) else {},
            "costs": cost_accounting(res.trades),
            "breaker": breaker_impact(res, t_start),
            "orders": len(res.orders),
            "rejects": {
                r: sum(1 for x in res.rejects if x["reason"] == r)
                for r in {x["reason"] for x in res.rejects}
            },
            "hash": res.hash,
            "sharpe_ci95": block_ci(ret, bs),
        }
        lab = pd.Series(regimes)
        daily_idx = res.equity.resample("1D").last().index[: len(ret)]
        prev = (daily_idx - pd.Timedelta("1D")).as_unit("ns")
        day_labels = pd.Series(lab.reindex(prev).fillna("unknown").to_numpy())
        v["regime_daily"] = {
            r: {
                "days": int((day_labels == r).sum()),
                "mean_daily_return": float(np.mean(ret[(day_labels == r).to_numpy()]))
                if (day_labels == r).any()
                else None,
                "total_return": float(np.prod(1 + ret[(day_labels == r).to_numpy()]) - 1)
                if (day_labels == r).any()
                else None,
            }
            for r in ("bull", "bear", "sideways", "unknown")
        }
        v["credibility"] = stats.credibility(ret, N_TRIALS, rules)
        if name in ("A1", "A0", "V0"):
            m = {
                "base": {
                    k: s[k]
                    for k in ("trades", "net_return", "max_drawdown", "sortino", "profit_factor")
                },
                "pair_share_max": max(v["pair_profit_share"].values())
                if v["pair_profit_share"]
                else None,
                "bench": thr,
                "stress": {
                    "net_return": out["variants"]["A1_stress"]["stats"]["net_return"],
                    "profit_factor": out["variants"]["A1_stress"]["stats"]["profit_factor"],
                }
                if name == "A1" and "A1_stress" in out["variants"]
                else {"net_return": float("nan"), "profit_factor": float("nan")},
                "windows": v["windows"],
                "regimes": v["regimes_trades"],
                "variants": [],
                "bias_clean": caus[name]["clean"],
            }
            v["_m"] = m
        out["variants"][name] = v

    # stress is evaluated before A1's criteria: recompute A1 matrix once the stress run is available
    for name in ("A1", "A0", "V0"):
        v = out["variants"][name]
        m = v.pop("_m")
        if name == "A1":
            st = out["variants"]["A1_stress"]["stats"]
            m["stress"] = {"net_return": st["net_return"], "profit_factor": st["profit_factor"]}
        rows = evaluate_criteria(m, proto["criteria"])
        for r in rows:
            if r["id"] == "T9" or (r["id"] == "T6" and name != "A1"):
                r["passed"], r["value"], r["note"] = None, None, "not evaluated"
        v["criteria"] = rows
        v["verdict_T1_T10"] = {
            "failed": [r["id"] for r in rows if r["passed"] is False],
            "not_evaluated": [r["id"] for r in rows if r["passed"] is None],
            "validated": False,
        }
    h1_p = out["variants"]["A1"]["credibility"].get("p_value_sharpe_gt_0", float("nan"))
    out["hypotheses"] = {
        "H1_p": h1_p,
        "H2_p_A1_vs_B1": p_h2,
        "holm_reject": stats.holm([h1_p, p_h2], 0.05),
    }
    out["series_daily"] = {k: fmt_series(r.equity) for k, r in runs.items()} | {
        k: fmt_series(v) for k, v in bench.items()
    }
    out["exposure_daily"] = {
        k: [round(float(x), 4) for x in r.exposure.resample("1D").last().dropna()]
        for k, r in runs.items()
    }
    out["series_start"] = start
    return out


def block_ci(ret: np.ndarray, bs: dict) -> tuple[float, float]:
    from quantlab.validation import block_bootstrap_ci

    return block_bootstrap_ci([ret], sharpe, bs["n"], bs["seed"], bs["block_days"], bs["level"])


def main() -> int:
    proto, spec = guard()
    print(
        "PREFLIGHT: manifests and amendments verified; holdout excluded from loaded candles",
        flush=True,
    )
    out = run_all(proto, spec)
    emit("FAMILYA_RESULT_JSON", json.dumps(out, default=float))
    print("FAMILYA DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
