"""Markdown rendering of the Phase 4 result (pure function, unit-tested offline)."""

from __future__ import annotations

import math


def _pct(x, d=1):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{d}f} %"


def _num(x, d=2):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{d}f}"


def _ann(net, days):
    if net is None or days is None or days <= 0 or net <= -1:
        return None
    return (1 + net) ** (365.0 / days) - 1


def _monthly_summary(m: dict) -> str:
    if not m:
        return "n/a"
    v = list(m.values())
    pos = sum(1 for x in v if x > 0)
    return f"{pos}/{len(v)} positive; best {_pct(max(v))}, worst {_pct(min(v))}"


def _row(label, r0, r1, fmt):
    return f"| {label} | {fmt(r0)} | {fmt(r1)} |"


def strategy_section(name: str, entry: dict, r0: dict, thr: dict) -> list[str]:
    r1 = entry["R1"]
    b1, s1 = r1["stats"]["base"], r1["stats"]["stress"]
    b0, s0 = r0["stats"]["base"], r0["stats"]["stress"]
    ge = r1.get("gross_exposure", {})
    lines = [f"### {name}: R0 (no overlay) vs R1 (overlay)", "",
             "| metric (base costs unless stated) | R0 | R1 |", "|---|---|---|"]  # fmt: skip
    lines += [
        _row("net return", b0["net_return"], b1["net_return"], _pct),
        _row("annualised return", _ann(b0["net_return"], b0.get("days")), r1["annualized_return"]["base"], _pct),
        _row("max drawdown (MTM, hourly)", b0["max_drawdown"], b1["max_drawdown"], _pct),
        _row("Sharpe", b0["sharpe"], b1["sharpe"], _num),
        _row("Sortino", b0["sortino"], b1["sortino"], _num),
        _row("profit factor", b0["profit_factor"], b1["profit_factor"], _num),
        _row("trades", b0["trades"], b1["trades"], lambda x: str(int(x))),
        _row("win rate", b0.get("win_rate"), b1.get("win_rate"), _pct),
        _row("time in market", b0.get("time_in_market"), b1.get("time_in_market"), _pct),
        _row("avg open positions", b0.get("avg_open_positions"), b1.get("avg_open_positions"), _num),
        f"| avg / peak gross exposure | n/a | {_pct(ge.get('avg_gross_exposure'))} / {_pct(ge.get('peak_gross_exposure'))} |",
        _row("stress net return (fee 0.2 % + slippage 0.1 %)", s0["net_return"], s1["net_return"], _pct),
        _row("stress profit factor", s0["profit_factor"], s1["profit_factor"], _num),
        f"| monthly returns | {_monthly_summary(r0.get('monthly', {}))} | {_monthly_summary(r1.get('monthly', {}))} |",
        f"| max pair share of profit | {_pct(max(r0['pair_profit_share'].values()) if r0.get('pair_profit_share') else None)} "
        f"| {_pct(max(r1['pair_profit_share'].values()) if r1.get('pair_profit_share') else None)} |",
        "",
    ]  # fmt: skip
    lines += ["Regimes (profit factor / trades):", "", "| regime | R0 | R1 |", "|---|---|---|"]
    for reg in ("bull", "bear", "sideways"):
        a, b = r0["regimes"].get(reg, {}), r1["regimes"].get(reg, {})
        lines.append(
            f"| {reg} | {_num(a.get('profit_factor'))} / {a.get('trades', 0)} "
            f"| {_num(b.get('profit_factor'))} / {b.get('trades', 0)} |"
        )
    lines += ["", "R1 window returns (nine 6-month windows):", ""]
    lines += [
        "| " + " | ".join(w["start"][:7] for w in r1["windows"]) + " |",
        "|" + "---|" * len(r1["windows"]),
        "| " + " | ".join(_pct(w["return"]) for w in r1["windows"]) + " |",
        "",
    ]
    lines += [f"R1 criteria vs thresholds (diagnostic, T3 = {_num(thr['sortino'])} Sortino, "
              f"T4 benchmark drawdown = {_pct(thr['max_drawdown'])}):", "",
              "| id | criterion | value | threshold | passed |", "|---|---|---|---|---|"]  # fmt: skip
    for c in r1["criteria"]:
        val = c["value"]
        shown = (
            _num(val, 3)
            if isinstance(val, (int, float)) and not isinstance(val, bool)
            else str(val)
        )
        ok = "not evaluated" if c["passed"] is None else ("yes" if c["passed"] else "NO")
        lines.append(
            f"| {c['id']} | {c['criterion'] if 'criterion' in c else c.get('name', '')} | {shown} | {c['threshold']} | {ok} |"
        )
    halts = r1.get("halt_events", [])
    lines += ["", f"Circuit-breaker halts in R1: {len(halts)} " + (str(halts) if halts else ""), ""]
    deny = r1.get("overlay", {}).get("denied", {})
    lines += [
        f"Entry decisions in R1: accepted {r1.get('overlay', {}).get('accepted', 'n/a')}, denied {deny}",
        "",
    ]
    lines += ["Ablations (descriptive only; not used to select anything):", "",
              "| configuration | net | max DD | Sortino | PF | trades | time in market | stress net | halts |",
              "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    full = {"R1 (all components)": {
        "net_return": b1["net_return"], "max_drawdown": b1["max_drawdown"], "sortino": b1["sortino"],
        "profit_factor": b1["profit_factor"], "trades": b1["trades"], "time_in_market": b1.get("time_in_market"),
        "stress_net_return": s1["net_return"], "halt_events": len(halts)}}  # fmt: skip
    full.update(entry["ablations"])
    for k, v in full.items():
        lines.append(
            f"| {k} | {_pct(v['net_return'])} | {_pct(v['max_drawdown'])} | {_num(v['sortino'])} | "
            f"{_num(v['profit_factor'])} | {v['trades']} | {_pct(v['time_in_market'])} | "
            f"{_pct(v['stress_net_return'])} | {v['halt_events']} |"
        )
    lines.append("")
    return lines


def render(out: dict) -> str:
    r0 = out["r0"]
    lines = [
        "# Phase 4 - R1 risk-overlay research report (research data, diagnostics only)", "",
        f"Protocol v{out['protocol_version']}; period {out['period']['start']} -> {out['period']['end_exclusive']} "
        f"(holdout untouched); backtests run: {out['backtests']}.", "",
        "NOT validation: all data here is research data. No configuration was selected or tuned on these results.", "",
        "## Benchmark set (T3 = highest Sortino, T4 = lowest drawdown, 20 % binding)", "",
        "| benchmark | net | max DD | Sharpe | Sortino |", "|---|---|---|---|---|",
    ]  # fmt: skip
    for k, v in out["benchmarks"].items():
        lines.append(
            f"| {k} | {_pct(v['net_return'])} | {_pct(v['max_drawdown'])} | {_num(v['sharpe'])} | {_num(v['sortino'])} |"
        )
    t = out["bench_threshold"]
    lines += [
        "",
        f"Thresholds used: Sortino >= {_num(t['sortino'])}, drawdown <= min(20 %, {_pct(t['max_drawdown'])}).",
        "",
    ]
    lines += ["## Bias checks (lookahead + recursive, R1 strategies)", ""]
    for k, v in out["bias"]["strategies"].items():
        lines.append(
            f"- {k}: clean={v['clean']}; lookahead evaluated {v['lookahead_evaluated']}, biased {v['lookahead_biased']}; "
            f"recursive checks {v['recursive_checks']}, failed {len(v['recursive_failed'])}"
        )
    lines.append("")
    for name, entry in out["strategies"].items():
        lines += strategy_section(name, entry, r0["strategies"][name], t)
    return "\n".join(lines) + "\n"
