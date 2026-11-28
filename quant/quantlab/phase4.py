"""
Phase 4 research runner: R1 risk overlay on TrendEmaCross / MomentumRoc versus the R0 reference.

    python -m quantlab.phase4 research     # smoke + R1 bias + R1 and 6 ablations x 2 strategies

Research data only (evaluation period); the holdout is never loaded. Everything it runs is fixed by
``protocol/protocol_v3.json`` (verified against ``frozen_manifest_v3.json`` first). Ablations are
descriptive: the report lists them, it never picks one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys

import pandas as pd

from quantlab import protocol as protocol_mod
from quantlab.costs import BASE, STRESS, apply_costs_consistent, apply_costs_recosted
from quantlab.equity import build_equity, buy_and_hold, rebalanced_buy_and_hold
from quantlab.metrics import exposure_profile, summarize
from quantlab.phase3 import (
    PROTO_DIR,
    USER_DATA,
    Context,
    _json_default,
    assess_strategy,
    backtest_trades,
    build_context,
    emit,
    run_bias,
    timerange,
)


R1_DIR = "quant/strategies_r1"
ABLATION_FLAGS = protocol_mod.ABLATIONS


# ====================================================================== pure helpers
def benchmark_set(ctx: Context, wallet: float) -> dict[str, pd.Series]:
    """B1-B5 of protocol v3 (membership fixed before any R1 result), base costs."""
    pairs = ctx.bench_pairs
    c, i = ctx.candles, ctx.index
    return {
        "B1 equal-weight all 8": buy_and_hold(c, i, wallet, BASE, pairs)[0],
        "B2 equal-weight ex-SOL": buy_and_hold(
            c, i, wallet, BASE, [p for p in pairs if p != "SOL/USDT"]
        )[0],
        "B3 BTC+ETH": buy_and_hold(c, i, wallet, BASE, ["BTC/USDT", "ETH/USDT"])[0],
        "B4 BTC": buy_and_hold(c, i, wallet, BASE, ["BTC/USDT"])[0],
        "B5 equal-weight monthly rebalanced": rebalanced_buy_and_hold(c, i, wallet, BASE, pairs),
    }


def bench_threshold(stats: dict[str, dict]) -> dict:
    """T3 = highest Sortino, T4 = lowest drawdown among the predefined benchmarks."""
    return {
        "sortino": max(v["sortino"] for v in stats.values()),
        "max_drawdown": min(v["max_drawdown"] for v in stats.values()),
    }


def annualized(net_return: float, days: float) -> float:
    if days <= 0 or net_return <= -1:
        return -1.0 if net_return <= -1 else float("nan")
    return float((1 + net_return) ** (365.0 / days) - 1)


def parse_halts(text: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r"RISK_HALT .*", text)]


def ablation_source(base_class: str, base_module: str, flag: str) -> tuple[str, str]:
    """Source of a subclass of an R1 strategy with exactly one component switched off."""
    name = f"{base_class}__{flag}_off"
    src = (
        "import dataclasses\n\n"
        "from quant_risk import RiskConfig\n"
        f"from {base_module} import {base_class}\n\n\n"
        f"class {name}({base_class}):\n"
        f"    risk_cfg = dataclasses.replace(RiskConfig(), {flag}=False)\n"
    )
    return name, src


def condensed(res: dict, halts: int) -> dict:
    b = res["stats"]["base"]
    return {
        "net_return": b["net_return"],
        "max_drawdown": b["max_drawdown"],
        "sortino": b["sortino"],
        "profit_factor": b["profit_factor"],
        "trades": b["trades"],
        "time_in_market": b.get("time_in_market"),
        "stress_net_return": res["stats"]["stress"]["net_return"],
        "halt_events": halts,
    }


def mark_t9_not_evaluated(res: dict) -> None:
    """Parameters are frozen in Phase 4: T9 is reported as not evaluated, never as pass or fail."""
    for r in res.get("criteria", []):
        if r["id"] == "T9":
            r["passed"], r["value"], r["note"] = None, None, "not evaluated (parameters frozen)"
    failed = [r["id"] for r in res.get("criteria", []) if r["passed"] is False]
    res["verdict"] = {
        "validated_on_evaluation": False,  # research data: diagnostics only, never validation
        "failed": failed,
        "all_evaluated_criteria_pass": not failed,
        "note": "diagnostic on research data; T9 not evaluated",
    }


# ====================================================================== freqtrade runs
def run_config(
    proto: dict, ctx: Context, cls: str, path: str, label: str, tr: str
) -> tuple[dict, dict, pd.DataFrame, pd.Series]:
    """One backtest at base fee -> corrected base costs, recosted stress, full assessment."""
    wallet = proto["initial_wallet"]
    stats_dir = USER_DATA / "risk_stats" / label
    shutil.rmtree(stats_dir, ignore_errors=True)
    os.environ["RISK_STATS_DIR"] = str(stats_dir)
    raw = backtest_trades(cls, path, tr, BASE.fee, f"p4_{label}")
    base = apply_costs_consistent(raw, BASE, wallet)
    pre = {"base": base, "stress": apply_costs_recosted(base, STRESS)}
    res = assess_strategy(cls, {}, None, ctx, judge=True, precosted=pre)
    mark_t9_not_evaluated(res)
    eq = build_equity(base, ctx.closes, wallet, BASE)
    res["annualized_return"] = {
        k: annualized(res["stats"][k]["net_return"], res["stats"][k]["days"])
        for k in ("base", "stress")
    }
    res["gross_exposure"] = exposure_profile(base, eq)
    res["trades_per_pair"] = base["pair"].value_counts().to_dict() if len(base) else {}
    stats = {}
    for f in stats_dir.glob("*.json"):
        stats = json.loads(f.read_text())
    res["overlay"] = stats
    return res, stats, base, eq


def smoke(proto: dict, ctx: Context) -> None:
    """Fail fast: one month of the R1 strategy must start, trade and write overlay statistics."""
    start, end = "2021-03-01", "2021-04-01"
    _, stats, base, _ = run_config(
        proto, ctx, "TrendEmaCrossR1", R1_DIR, "smoke", timerange(start, end)
    )
    ok = bool(stats) and stats.get("accepted", 0) + sum(stats.get("denied", {}).values()) > 0
    print(
        f"SMOKE trades={len(base)} overlay={json.dumps(stats.get('denied', {}))} ok={ok}",
        flush=True,
    )
    if not ok:
        raise SystemExit("smoke test failed: the overlay made no decision (is it wired in?)")


def stage_research(proto: dict, v3: dict) -> int:
    wallet = proto["initial_wallet"]
    ctx = build_context(proto, "evaluation", with_bias=False)
    r0 = json.loads((PROTO_DIR / "r0_reference.json").read_text())
    per = proto["periods"]["evaluation"]
    tr = timerange(per["start"], per["end_exclusive"])

    smoke(proto, ctx)

    names = {s: v3["candidates"]["classes"][s] for s in v3["candidates"]["strategies"]}
    bias = run_bias(proto, list(names.values()), R1_DIR, "bias_r1")
    ctx.bias = bias

    bench = benchmark_set(ctx, wallet)
    bench_stats = {k: summarize(v, None, wallet) for k, v in bench.items()}
    ctx.bench_threshold = bench_threshold(bench_stats)
    out: dict = {
        "protocol_version": v3["version"],
        "period": per,
        "benchmarks": bench_stats,
        "bench_threshold": ctx.bench_threshold,
        "bias": bias,
        "r0": r0,
        "strategies": {},
        "backtests": 0,
    }
    vdir = USER_DATA / "variants_r1"
    shutil.rmtree(vdir, ignore_errors=True)
    vdir.mkdir(parents=True)
    modules = {"TrendEmaCrossR1": "trend_ema_cross_r1", "MomentumRocR1": "momentum_roc_r1"}

    for base_name, cls in names.items():
        res, stats, _, _ = run_config(proto, ctx, cls, R1_DIR, f"{cls}_R1", tr)
        out["backtests"] += 1
        entry = {"R1": res, "ablations": {}}
        halts = [e for e in stats.get("breaker_events", []) if e.get("type") == "halt"]
        entry["R1"]["halt_events"] = halts
        print(f"{cls} R1: net {res['stats']['base']['net_return']:+.2%} "
              f"dd {res['stats']['base']['max_drawdown']:.2%} trades {res['stats']['base']['trades']} "
              f"halts {len(halts)}", flush=True)  # fmt: skip
        for ablation_name, flag in ABLATION_FLAGS.items():
            vname, src = ablation_source(cls, modules[cls], flag)
            (vdir / f"{vname}.py").write_text(src)
            ares, astats, _, _ = run_config(proto, ctx, vname, str(vdir), f"{vname}", tr)
            out["backtests"] += 1
            ahalts = [e for e in astats.get("breaker_events", []) if e.get("type") == "halt"]
            entry["ablations"][ablation_name] = condensed(ares, len(ahalts))
            print(f"  {ablation_name}: net {ares['stats']['base']['net_return']:+.2%} "
                  f"dd {ares['stats']['base']['max_drawdown']:.2%}", flush=True)  # fmt: skip
        out["strategies"][base_name] = entry

    if out["backtests"] != v3["budget"]["backtests"]:
        raise SystemExit(f"ran {out['backtests']} backtests, budget is {v3['budget']['backtests']}")
    from quantlab.report4 import render

    (USER_DATA / "phase4_result.json").write_text(json.dumps(out, default=_json_default))
    md = render(out)
    (USER_DATA / "phase4_report.md").write_text(md)
    emit("PHASE4_RESULT_JSON", json.dumps(out, default=_json_default))
    emit("PHASE4_REPORT_MD", md)
    return 0


def guard_v3() -> tuple[dict, dict]:
    errs = (
        protocol_mod.consistency_errors()
        + protocol_mod.verify_manifest()
        + protocol_mod.consistency_errors_v3()
        + protocol_mod.verify_manifest_v3()
    )
    if errs:
        print("PROTOCOL V3 NOT FROZEN OR CHANGED:\n" + "\n".join(errs), file=sys.stderr)
        raise SystemExit(1)
    return protocol_mod.load_protocol(), json.loads(protocol_mod.PROTOCOL_V3_PATH.read_text())


def main(argv: list[str] | None = None) -> int:
    cmd = (argv or sys.argv[1:] or [""])[0]
    if cmd != "research":
        print("usage: python -m quantlab.phase4 research", file=sys.stderr)
        return 2
    proto, v3 = guard_v3()
    return stage_research(proto, v3)


if __name__ == "__main__":
    raise SystemExit(main())
