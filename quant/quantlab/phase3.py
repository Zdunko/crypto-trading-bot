"""
Phase 3 research runner: bias stage, evaluation stage, holdout stage.

The pure part (:func:`assess_strategy`) turns raw Freqtrade trades into costed equity curves,
metrics, uncertainty intervals and the mechanical T1-T10 verdict; it is unit-tested offline. The
I/O part shells out to ``freqtrade`` (needs exchange market metadata, so it runs in GitHub
Actions) and prints machine-readable results between markers.

    python -m quantlab.phase3 bias
    python -m quantlab.phase3 eval        # evaluation period only; the holdout is never loaded
    python -m quantlab.phase3 holdout     # survivors only, exactly once

Every stage first verifies that the frozen protocol, strategies and configs are unchanged.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from quantlab import bias as bias_mod
from quantlab import protocol as protocol_mod
from quantlab.costs import BASE, SCENARIOS, apply_costs
from quantlab.equity import build_equity, buy_and_hold, close_matrix, hourly_index
from quantlab.metrics import (
    daily_returns,
    monthly_returns,
    profit_factor,
    sharpe,
    sortino,
    summarize,
    with_start,
)
from quantlab.validation import (
    block_bootstrap_ci,
    bootstrap_ci,
    calendar_windows,
    daily_regimes,
    evaluate_criteria,
    pair_profit_shares,
    regime_stats,
    verdict,
    window_stats,
)


ROOT = Path(__file__).resolve().parents[2]
USER_DATA = ROOT / "user_data"
STRATEGY_DIR = ROOT / "quant" / "strategies"
PROTO_DIR = ROOT / "quant" / "protocol"
PERIOD_LIKE = ("period", "lookback")  # variant parameters that lengthen the indicator warm-up


# ====================================================================== pure assessment
@dataclass
class Context:
    proto: dict
    candles: dict[str, pd.DataFrame]
    index: pd.DatetimeIndex
    closes: pd.DataFrame
    regimes: pd.Series
    bench: dict[str, pd.Series]  # scenario name -> equal-weight buy-and-hold equity
    bench_pairs: list[str]
    bias: dict | None


def _num(x):
    return None if x is None else float(x)


def _stats_block(eq: pd.Series, trades: pd.DataFrame, wallet: float) -> dict:
    s = summarize(eq, trades, wallet)
    s.setdefault("trades", 0)
    s.setdefault("profit_factor", float("nan"))
    return s


def assess_strategy(
    name: str,
    raw_trades: dict[str, pd.DataFrame],
    variant_returns: list[float] | None,
    ctx: Context,
    judge: bool = True,
) -> dict:
    """Costed equity, metrics, uncertainty and (optionally) the T1-T10 verdict for one strategy."""
    p = ctx.proto
    wallet = p["initial_wallet"]
    eq, costed, stats = {}, {}, {}
    for sc_name, scen in SCENARIOS.items():
        costed[sc_name] = apply_costs(raw_trades[sc_name], scen)
        eq[sc_name] = build_equity(costed[sc_name], ctx.closes, wallet, scen)
        stats[sc_name] = _stats_block(eq[sc_name], costed[sc_name], wallet)
    base_trades = costed["base"]

    bench_stats = {k: summarize(v, None, wallet) for k, v in ctx.bench.items()}
    windows = window_stats(eq["base"], _windows_for(ctx), wallet)
    regimes = regime_stats(base_trades, ctx.regimes) if len(base_trades) else {}
    shares = pair_profit_shares(base_trades) if len(base_trades) else {}

    out = {
        "strategy": name,
        "stats": stats,
        "benchmark": bench_stats,
        "windows": windows,
        "regimes": regimes,
        "pair_profit_share": shares,
        "monthly": monthly_returns(eq["base"], wallet).round(4).to_dict(),
        "by_exit_reason": base_trades["exit_reason"].value_counts().to_dict()
        if len(base_trades)
        else {},
        "uncertainty": _uncertainty(eq["base"], ctx.bench["base"], base_trades, p),
    }
    if judge:
        m = {
            "base": {
                "trades": stats["base"]["trades"],
                "net_return": stats["base"]["net_return"],
                "max_drawdown": stats["base"]["max_drawdown"],
                "sortino": stats["base"]["sortino"],
                "profit_factor": stats["base"]["profit_factor"],
            },
            "pair_share_max": max(shares.values()) if shares else None,
            "bench": {
                "sortino": bench_stats["base"]["sortino"],
                "max_drawdown": bench_stats["base"]["max_drawdown"],
            },
            "stress": {
                "net_return": stats["stress"]["net_return"],
                "profit_factor": stats["stress"]["profit_factor"],
            },
            "windows": windows,
            "regimes": regimes,
            "variants": variant_returns or [],
            "bias_clean": _bias_clean(ctx.bias, name),
        }
        rows = evaluate_criteria(m, p["criteria"])
        out["criteria"] = rows
        out["verdict"] = verdict(rows)
        out["variant_returns"] = variant_returns or []
    return out


def _windows_for(ctx: Context):
    start = ctx.index[0].strftime("%Y-%m-%d")
    end = (ctx.index[-1] + pd.Timedelta("1h")).strftime("%Y-%m-%d")
    w = ctx.proto["walk_forward"]
    return calendar_windows(start, end, w["months"], w["min_tail_months"])


def _bias_clean(bias: dict | None, name: str):
    if not bias:
        return None
    return bias["strategies"].get(name, {}).get("clean")


def _uncertainty(eq_s: pd.Series, eq_b: pd.Series, trades: pd.DataFrame, p: dict) -> dict:
    bs = p["bootstrap"]
    n, seed, block, level = bs["n"], bs["seed"], bs["block_days"], bs["level"]
    wallet = p["initial_wallet"]
    ds = daily_returns(with_start(eq_s, wallet)).to_numpy()
    db = daily_returns(with_start(eq_b, wallet)).to_numpy()

    def total(r):
        return float(np.prod(1.0 + r) - 1.0)

    unc = {
        "method": f"trade-level bootstrap (iid) and circular block bootstrap ({block}-day blocks), "
        f"n={n}, seed={seed}, {int(level * 100)}% percentile intervals",
        "net_return_ci": block_bootstrap_ci([ds], total, n, seed, block, level),
        "sortino_ci": block_bootstrap_ci([ds], sortino, n, seed, block, level),
        "sharpe_ci": block_bootstrap_ci([ds], sharpe, n, seed, block, level),
        "sortino_diff_vs_benchmark_ci": block_bootstrap_ci(
            [ds, db], lambda a, b: sortino(a) - sortino(b), n, seed, block, level
        ),
        "net_return_diff_vs_benchmark_ci": block_bootstrap_ci(
            [ds, db], lambda a, b: total(a) - total(b), n, seed, block, level
        ),
    }
    if len(trades) >= 2:
        unc["profit_factor_ci"] = bootstrap_ci(
            trades["profit_abs"].to_numpy(), profit_factor, n, seed, level
        )
        unc["expectancy_pct_ci"] = bootstrap_ci(
            trades["profit_ratio"].to_numpy(), lambda v: float(np.mean(v)), n, seed, level
        )
    return unc


# ====================================================================== freqtrade I/O
def ft(args: list[str], *, check: bool = True) -> str:
    """Run ``freqtrade`` and return combined output; the log tail is shown if it fails."""
    env = {
        **os.environ,
        "FREQTRADE__EXCHANGE__NAME": "okx",
        "PYTHONPATH": os.pathsep.join(
            [str(STRATEGY_DIR), str(ROOT / "quant"), os.environ.get("PYTHONPATH", "")]
        ),
    }
    res = subprocess.run(
        ["freqtrade", *args], capture_output=True, text=True, env=env, cwd=ROOT, check=False
    )
    text = (res.stdout or "") + (res.stderr or "")
    if check and res.returncode != 0:
        print("\n".join(text.splitlines()[-40:]), file=sys.stderr)
        raise RuntimeError(f"freqtrade {args[0]} failed with exit code {res.returncode}")
    return text


def common_args() -> list[str]:
    return [
        "-c", "quant/configs/base.json", "-c", "quant/configs/backtest.json",
        "--userdir", "user_data", "-i", "1h",
    ]  # fmt: skip


def timerange(start: str, end: str) -> str:
    return f"{start.replace('-', '')}-{end.replace('-', '')}"


def backtest_trades(
    strategy: str, strategy_path: str, tr: str, fee: float, label: str
) -> pd.DataFrame:
    from freqtrade.data.btanalysis import load_backtest_data

    outdir = USER_DATA / "bt" / label
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True, exist_ok=True)  # Freqtrade does not create the export directory
    ft(
        ["backtesting", *common_args(), "--strategy-path", strategy_path, "--strategy", strategy,
         "--timerange", tr, "--fee", str(fee), "--export", "trades",
         "--backtest-directory", str(outdir), "--cache", "none"]
    )  # fmt: skip
    return load_backtest_data(outdir, strategy)


def load_candles(proto: dict) -> dict[str, pd.DataFrame]:
    out = {}
    for pair in proto["pairs"]:
        path = USER_DATA / "data" / proto["exchange"] / f"{pair.replace('/', '_')}-1h.feather"
        out[pair] = pd.read_feather(path)
    return out


def strategy_module(strategy: str) -> str:
    for f in STRATEGY_DIR.glob("*.py"):
        if re.search(rf"^class {strategy}\(", f.read_text(), re.MULTILINE):
            return f.stem
    raise KeyError(strategy)


def make_variant(strategy: str, param: str, value, outdir: Path) -> str:
    """Write a subclass overriding one parameter; widen the warm-up if the parameter needs it."""
    name = f"{strategy}__{param}__{str(value).replace('.', 'p')}"
    startup = ""
    if any(k in param for k in PERIOD_LIKE):
        startup = (
            f"    startup_candle_count = max({strategy}.startup_candle_count, {int(3 * value)})\n"
        )
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{name}.py").write_text(
        f"from {strategy_module(strategy)} import {strategy}\n\n\n"
        f"class {name}({strategy}):\n    {param} = {value!r}\n{startup}"
    )
    return name


def variants_of(strategy: str, ranges: dict) -> list[tuple[str, object]]:
    return [(param, v) for param, (lo, hi) in ranges.items() for v in (lo, hi)]


def build_context(proto: dict, which: str, with_bias: bool = True) -> Context:
    per = proto["periods"][which]
    index = hourly_index(per["start"], per["end_exclusive"])
    candles = load_candles(proto)
    closes = close_matrix(candles, index)
    wallet = proto["initial_wallet"]
    bench, bench_pairs = {}, []
    for sc_name, scen in SCENARIOS.items():
        bench[sc_name], bench_pairs = buy_and_hold(candles, index, wallet, scen)
    btc, _ = buy_and_hold(candles, index, wallet, BASE, ["BTC/USDT"])
    bench["btc_base"] = btc
    bias = None
    path = PROTO_DIR / "bias_result.json"
    if with_bias and path.exists():
        bias = json.loads(path.read_text())
    reg = proto["regime"]
    regimes = daily_regimes(candles[reg["proxy_pair"]], reg["ema_period"], reg["adx_trend"])
    return Context(proto, candles, index, closes, regimes, bench, bench_pairs, bias)


def emit(tag: str, payload: str) -> None:
    print(f"{tag}_BEGIN")
    print(payload)
    print(f"{tag}_END", flush=True)


def guard() -> dict:
    errs = protocol_mod.consistency_errors() + protocol_mod.verify_manifest()
    if errs:
        print("PROTOCOL NOT FROZEN OR CHANGED:\n" + "\n".join(errs), file=sys.stderr)
        raise SystemExit(1)
    return protocol_mod.load_protocol()


# ====================================================================== stages
def stage_bias(proto: dict) -> int:
    strategies, pairs = proto["strategies"], proto["pairs"]
    tol = proto["bias"]["max_recursive_variance"]
    out_dir = USER_DATA / "bias"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    lookahead: dict[str, dict] = {}
    recursive: dict[str, dict] = {s: {} for s in strategies}
    for i, (start, end) in enumerate(proto["bias_periods"]):
        label, tr = f"{start}..{end}", timerange(start, end)
        csv_path = out_dir / f"lookahead_{i}.csv"
        text = ft(
            ["lookahead-analysis", *common_args(), "--strategy-path", "quant/strategies",
             "--strategy-list", *strategies, "--timerange", tr, "-p", *pairs,
             "--minimum-trade-amount", "10", "--targeted-trade-amount", "20",
             "--lookahead-analysis-exportfilename", str(csv_path)],
            check=False,
        )  # fmt: skip
        (out_dir / f"lookahead_{i}.log").write_text(text)
        lookahead[label] = bias_mod.parse_lookahead_csv(csv_path)
        for s in strategies:
            for pair in proto["bias"]["recursive_pairs"]:
                text = ft(
                    ["recursive-analysis", *common_args(), "--strategy-path", "quant/strategies",
                     "--strategy", s, "--timerange", tr, "-p", pair,
                     "--startup-candle", "199", "399", "599", "999"],
                    check=False,
                )  # fmt: skip
                (out_dir / f"recursive_{i}_{s}_{pair.replace('/', '_')}.log").write_text(text)
                ok, worst = bias_mod.recursive_ok(bias_mod.parse_recursive(text), tol)
                recursive[s][f"{label}|{pair}"] = (ok, worst)
        print(f"bias period {label} done", flush=True)
    summary = bias_mod.summarize_bias(
        strategies, lookahead, recursive, proto["bias"]["min_evaluated_periods_per_strategy"]
    )
    summary["protocol_version"] = proto["version"]
    emit("PHASE3_BIAS_JSON", json.dumps(summary))
    return 0


def run_variants(proto: dict, strategy: str, ctx: Context) -> list[dict]:
    per = proto["periods"]["evaluation"]
    tr = timerange(per["start"], per["end_exclusive"])
    vdir = USER_DATA / "variants"
    rows = []
    for param, value in variants_of(strategy, proto["robustness"][strategy]):
        name = make_variant(strategy, param, value, vdir)
        raw = backtest_trades(name, str(vdir), tr, BASE.fee, f"variant_{name}")
        costed = apply_costs(raw, BASE)
        eq = build_equity(costed, ctx.closes, proto["initial_wallet"], BASE)
        rows.append(
            {"param": param, "value": value, "net_return": float(eq.iloc[-1] / proto["initial_wallet"] - 1),
             "trades": len(costed)}
        )  # fmt: skip
        print(
            f"variant {name}: net {rows[-1]['net_return']:+.2%} ({rows[-1]['trades']} trades)",
            flush=True,
        )
    return rows


def stage_eval(proto: dict, which: str = "evaluation", only: list[str] | None = None) -> int:
    ctx = build_context(proto, which, with_bias=(which == "evaluation"))
    per = proto["periods"][which]
    tr = timerange(per["start"], per["end_exclusive"])
    names = only if only is not None else proto["strategies"]
    results: dict = {"protocol_version": proto["version"], "period": which, "range": per,
                     "bench_pairs": ctx.bench_pairs, "strategies": {}}  # fmt: skip
    results["benchmarks"] = {
        k: summarize(v, None, proto["initial_wallet"]) for k, v in ctx.bench.items()
    }

    for name in [*names, proto["reference_strategy"]]:
        raw = {
            sc: backtest_trades(name, "quant/strategies", tr, scen.fee, f"{which}_{name}_{sc}")
            for sc, scen in SCENARIOS.items()
        }
        is_ref = name == proto["reference_strategy"]
        variants = [] if (is_ref or which != "evaluation") else run_variants(proto, name, ctx)
        vr = [v["net_return"] for v in variants]
        res = assess_strategy(name, raw, vr, ctx, judge=not is_ref and which == "evaluation")
        res["variants"] = variants
        results["strategies"][name] = res
        print(f"{which}: {name} done", flush=True)

    if which == "holdout":
        h = proto["holdout_criteria"]
        for name, res in results["strategies"].items():
            if name == proto["reference_strategy"]:
                continue
            b = res["stats"]["base"]
            rows = [
                {"id": "H1", "value": b["net_return"], "threshold": "> 0", "passed": b["net_return"] > 0},
                {"id": "H2", "value": b["max_drawdown"], "threshold": "<= 0.20", "passed": b["max_drawdown"] <= 0.20},
                {"id": "H3", "value": b["profit_factor"], "threshold": ">= 1.0", "passed": bool(b["profit_factor"] >= 1.0)},
            ]  # fmt: skip
            res["holdout_criteria"] = rows
            res["holdout_passed"] = all(r["passed"] for r in rows)
        results["holdout_rule"] = h["rule"]

    from quantlab.report import render

    emit("PHASE3_RESULT_JSON", json.dumps(results, default=_json_default))
    emit("PHASE3_REPORT_MD", render(results, proto))
    return 0


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def stage_holdout(proto: dict) -> int:
    verdict_path = PROTO_DIR / "e_verdict.json"
    if (PROTO_DIR / "holdout_result.json").exists():
        print(
            "HOLDOUT ALREADY EVALUATED (holdout_result.json exists): refusing to run again",
            file=sys.stderr,
        )
        return 1
    if not verdict_path.exists():
        print(
            "e_verdict.json missing: evaluation results must be recorded before the holdout",
            file=sys.stderr,
        )
        return 1
    survivors = json.loads(verdict_path.read_text())["validated"]
    if not survivors:
        print("No strategy passed T1-T10 on the evaluation period: the holdout stays UNTOUCHED.")
        emit("PHASE3_RESULT_JSON", json.dumps({"holdout": "not run", "survivors": []}))
        return 0
    return stage_eval(proto, "holdout", survivors)


def main(argv: list[str] | None = None) -> int:
    cmd = (argv or sys.argv[1:] or [""])[0]
    if cmd not in ("bias", "eval", "holdout"):
        print("usage: python -m quantlab.phase3 bias|eval|holdout", file=sys.stderr)
        return 2
    proto = guard()
    return {"bias": stage_bias, "eval": stage_eval, "holdout": stage_holdout}[cmd](proto)


if __name__ == "__main__":
    raise SystemExit(main())
