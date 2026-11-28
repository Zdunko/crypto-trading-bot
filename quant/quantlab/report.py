"""Markdown rendering of Phase 3 results (plain tables, readable on a phone)."""

from __future__ import annotations

import math


LIMITATIONS = """## Limitations

- Candle-based backtest: entries/exits at candle open prices, stops filled at the stop price; real fills differ. Slippage is an assumption, not measured, and is not fed back into position sizing.
- Survivorship bias: the 8 pairs were chosen in 2026 and all still trade; delisted coins are absent, so results are optimistic by an unknown amount.
- Few independent regimes (about 4 years, one cycle); crypto pairs are highly correlated, so the effective sample is smaller than the trade count suggests. Bootstrap intervals assume the resampled blocks are representative and are therefore optimistic.
- Several strategies were tested; passing a threshold by chance is possible. No multiple-testing correction is applied beyond the pre-registered, strict thresholds."""

TABLE_HEAD = (
    "| Strategy | Net return | Max DD | Sharpe | Sortino | PF | Win rate | Expectancy/trade "
    "| Trades | In market | Stress (net / PF) | Verdict |"
)


def _p(x, d=1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{d}f}%"


def _net(x) -> str:
    """Net return; below -100 % is impossible for long-only spot and flagged as an artefact."""
    if isinstance(x, float) and x < -1.0:
        return "-100% (ruin; post-hoc slippage artefact)"
    return _p(x)


def _f(x, d=2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return "inf" if x == math.inf else f"{x:.{d}f}"


def _ci(ci, pct=False) -> str:
    if not ci or any(v is None or (isinstance(v, float) and math.isnan(v)) for v in ci):
        return "n/a"
    fmt = _p if pct else _f
    return f"[{fmt(ci[0])}, {fmt(ci[1])}]"


def _row(name: str, s: dict, stress: dict | None, verdict: str) -> str:
    st = f"{_net(stress['net_return'])} / {_f(stress.get('profit_factor'))}" if stress else "-"
    cells = [
        name, _net(s["net_return"]), _p(s["max_drawdown"]), _f(s["sharpe"]), _f(s["sortino"]),
        _f(s.get("profit_factor")), _p(s.get("win_rate")), _p(s.get("expectancy_pct"), 2),
        str(s.get("trades", "-")), _p(s.get("time_in_market"), 0), st, verdict,
    ]  # fmt: skip
    return "| " + " | ".join(cells) + " |"


def _verdict(res: dict) -> str:
    if "holdout_passed" in res:
        return "HOLDOUT PASS" if res["holdout_passed"] else "HOLDOUT FAIL"
    v = res.get("verdict")
    if v is None:
        return "reference"
    return "PASS" if v["validated_on_evaluation"] else "REJECTED (" + ", ".join(v["failed"]) + ")"


def _header(results: dict, proto: dict) -> list[str]:
    per, c = results["range"], proto["costs"]
    base, stress = c["base"], c["stress"]
    return [
        f"# Phase 3 results - {results['period']} period",
        "",
        f"- Protocol v{results['protocol_version']} (frozen), exchange `{proto['exchange']}`, 1h candles, {len(proto['pairs'])} pairs, dataset sha256 `{proto['data']['dataset_sha256']}`",
        f"- Period: {per['start']} -> {per['end_exclusive']} (exclusive); simulated wallet {proto['initial_wallet']} USDT, max {proto['max_open_trades']} open trades",
        f"- Costs per side: base fee {_p(base['fee'], 2)} + slippage {_p(base['slippage'], 2)} (+{_p(base['stop_extra'], 2)} on stop exits); stress fee {_p(stress['fee'], 2)} + slippage {_p(stress['slippage'], 2)} (+{_p(stress['stop_extra'], 2)} on stops)",
        f"- Benchmark pairs (listed at period start): {', '.join(results['bench_pairs'])}",
        "",
    ]


def _comparison(results: dict) -> list[str]:
    out = ["## 1. Comparison (base costs)", "", TABLE_HEAD, "|" + "---|" * 12]
    for name, res in results["strategies"].items():
        out.append(_row(name, res["stats"]["base"], res["stats"]["stress"], _verdict(res)))
    bm = results["benchmarks"]
    out.append(_row("Equal-weight buy&hold (benchmark)", bm["base"], bm["stress"], "benchmark"))
    out.append(_row("BTC buy&hold", bm["btc_base"], None, "reference"))
    return out


def _shown(v) -> str:
    if isinstance(v, list):
        return ", ".join(_f(x, 3) for x in v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return _f(v, 3)
    return str(v)


def _criteria(results: dict) -> list[str]:
    judged = {k: v for k, v in results["strategies"].items() if "criteria" in v}
    if not judged:
        return []
    names = list(judged)
    out = ["", "## 2. Criteria T1-T10 (frozen thresholds)", "", "| Criterion | " + " | ".join(names) + " |",
           "|---|" + "---|" * len(names)]  # fmt: skip
    for i, first in enumerate(judged[names[0]]["criteria"]):
        cells = []
        for n in names:
            r = judged[n]["criteria"][i]
            cells.append(("PASS " if r["passed"] else "FAIL ") + _shown(r["value"]))
        out.append(
            f"| {first['id']}: {first['desc']} ({first['threshold']}) | " + " | ".join(cells) + " |"
        )
    return out


def _uncertainty(results: dict) -> list[str]:
    out = ["", "## 3. Uncertainty (95% intervals; optimistic, see limitations)", "",
           "| Strategy | Annualised return | Sortino | Sharpe | Sortino minus benchmark | Annualised return minus benchmark | Profit factor | Expectancy/trade |",
           "|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for name, res in results["strategies"].items():
        u = res["uncertainty"]
        cells = [
            name, _ci(u["annualized_return_ci"], True), _ci(u["sortino_ci"]), _ci(u["sharpe_ci"]),
            _ci(u["sortino_diff_vs_benchmark_ci"]), _ci(u["annualized_diff_vs_benchmark_ci"], True),
            _ci(u.get("profit_factor_ci")), _ci(u.get("expectancy_pct_ci"), True),
        ]  # fmt: skip
        out.append("| " + " | ".join(cells) + " |")
    out += ["", next(iter(results["strategies"].values()))["uncertainty"]["method"]]
    return out


def _windows_regimes(results: dict) -> list[str]:
    out = ["", "## 4. Walk-forward windows (6 months, parameters fixed): return per window", ""]
    for name, res in results["strategies"].items():
        out.append(
            f"- **{name}**: "
            + "; ".join(f"{x['start'][:7]} {_p(x['return'])}" for x in res["windows"])
        )
    out += [
        "",
        "## 5. Market regimes (BTC/USDT daily; trades by entry regime): trades / profit factor",
        "",
    ]
    for name, res in results["strategies"].items():
        out.append(
            f"- **{name}**: "
            + "; ".join(
                f"{k} {v['trades']} / {_f(v['profit_factor'])}" for k, v in res["regimes"].items()
            )
        )
    return out


def _robustness(results: dict) -> list[str]:
    rows = {n: r["variants"] for n, r in results["strategies"].items() if r.get("variants")}
    if not rows:
        return []
    out = [
        "",
        "## 6. Parameter robustness (one parameter to each end of its range; base costs)",
        "",
    ]
    for name, v in rows.items():
        pos = sum(1 for x in v if x["net_return"] > 0)
        listing = "; ".join(f"{x['param']}={x['value']} {_net(x['net_return'])}" for x in v)
        out.append(f"- **{name}** ({pos}/{len(v)} positive): {listing}")
    return out


def _holdout(results: dict) -> list[str]:
    rows = [(n, r) for n, r in results["strategies"].items() if "holdout_criteria" in r]
    if not rows:
        return []
    out = ["", "## 7. Holdout criteria", ""]
    for n, r in rows:
        parts = [
            f"{c['id']} {'PASS' if c['passed'] else 'FAIL'} ({_f(c['value'], 3)} {c['threshold']})"
            for c in r["holdout_criteria"]
        ]
        out.append(f"- **{n}**: " + "; ".join(parts))
    return out


def render(results: dict, proto: dict) -> str:
    out = _header(results, proto) + _comparison(results) + _criteria(results)
    out += (
        _uncertainty(results) + _windows_regimes(results) + _robustness(results) + _holdout(results)
    )
    out += ["", "## Exit reasons (base costs)", ""]
    out += [f"- {n}: {r['by_exit_reason']}" for n, r in results["strategies"].items()]
    return "\n".join([*out, "", LIMITATIONS])
