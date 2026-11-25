"""Builds the Family A evaluation report and SVG charts from the CI result JSON (no new computation)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quantlab.charts import drawdown, line_chart  # noqa: E402

HERE = Path(__file__).resolve().parent
d = json.loads((HERE / "evaluation_result.json").read_text())
V = d["variants"]
B = d["benchmarks"]


def pct(x, k=1):
    return "n/a" if x is None else f"{x * 100:.{k}f} %"


def num(x, k=2):
    return "n/a" if x is None or x != x else ("inf" if x == float("inf") else f"{x:.{k}f}")


ser = d["series_daily"]
eq = {k: ser[k] for k in ("A1", "A0", "V0", "A1_stress")} | {k: ser[k] for k in ser if k.startswith("B")}
(HERE / "equity_curves.svg").write_text(line_chart(eq, "Equity (USDT, log scale), evaluation period 2021-01..2025-06", "equity", log=True, dashed=("A1_stress",)))
(HERE / "drawdowns.svg").write_text(line_chart({k: drawdown(v) for k, v in eq.items()}, "Drawdown from peak (daily closes)", "drawdown", dashed=("A1_stress",)))
(HERE / "exposure.svg").write_text(line_chart(d["exposure_daily"], "Gross exposure (positions / equity)", "exposure", dashed=("A1_stress",)))

L = ["# Family A - market evaluation report (research data 2021-01-01..2025-07-01, holdout untouched)", "",
     "Source: CI run 45679466940, commit 7058aa4 (protocol v5 + amendment A1). One run, nothing repeated, no parameter changed.",
     "NOT validation: research data, survivor-biased 8-pair universe, 43 trials in the ledger.", "",
     "## Side by side (base costs, breaker ON for A1/A0/V0)", "",
     "| | net | annualised | max DD | Sharpe | Sortino | PF | episodes | time in market | avg / peak exposure |", "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
for n in ("A1", "A0", "V0", "A1_stress"):
    v, s = V[n], V[n]["stats"]
    L.append(f"| {n}{' (2x costs)' if n.endswith('stress') else ''} | {pct(s['net_return'])} | {pct(v['annualised_return'])} | {pct(s['max_drawdown'])} | {num(s['sharpe'])} | {num(s['sortino'])} | {num(s['profit_factor'])} | {s['trades']} | {pct(s.get('time_in_market'))} | {pct(v['exposure_avg'])} / {pct(v['exposure_peak'])} |")  # fmt: skip
for k, s in B.items():
    L.append(f"| {k} | {pct(s['net_return'])} | n/a | {pct(s['max_drawdown'])} | {num(s['sharpe'])} | {num(s['sortino'])} | n/a | n/a | n/a | passive, no breaker or cap |")
L += ["", f"T3/T4 benchmark thresholds (rule fixed in protocol v3): Sortino >= {num(d['bench_threshold']['sortino'])}, drawdown <= min(20 %, {pct(d['bench_threshold']['max_drawdown'])}).", "",
      "Benchmark disclosure: B1-B5 use the same fee and slippage rates but NO participation cap and NO circuit breaker. Definitions unchanged.", "",
      "![equity](equity_curves.svg)", "", "![drawdown](drawdowns.svg)", "", "![exposure](exposure.svg)", "",
      "## T1-T10 matrix (pass / FAIL / not evaluated)", "", "| id | criterion | threshold | A1 | A0 | V0 |", "|---|---|---|---|---|---|"]  # fmt: skip
rows = {r["id"]: r for r in V["A1"]["criteria"]}
for cid, r in rows.items():
    cells = []
    for n in ("A1", "A0", "V0"):
        x = next(q for q in V[n]["criteria"] if q["id"] == cid)
        val = x["value"]
        shown = "" if val is None else (num(val, 3) if isinstance(val, (int, float)) else ("ok" if isinstance(val, dict) and x["passed"] else str(val)[:28]))
        cells.append(("not evaluated" if x["passed"] is None else ("pass" if x["passed"] else "FAIL")) + (f" ({shown})" if shown else ""))
    L.append(f"| {cid} | {r['desc']} | {r['threshold']} | " + " | ".join(cells) + " |")
L += ["", "T6 was evaluated for A1 only (the only stress run); T9 for none (no parameter sweep). T10 = causality checks (below).", "",
      "## Statistics (rules fixed in protocol_v4_stats.json)", "", "| | annualised Sharpe | 95 % block-bootstrap CI | DSR (N=43) | p(Sharpe>0) | detectable Sharpe (power 0.8) | verdict |", "|---|---|---|---|---|---|---|"]  # fmt: skip
for n in ("A1", "A0", "V0", "A1_stress"):
    c, ci = V[n]["credibility"], V[n]["sharpe_ci95"]
    L.append(f"| {n} | {num(c['sharpe_annualised'])} | [{num(ci[0])}, {num(ci[1])}] | {num(c['dsr'], 3)} | {num(c['p_value_sharpe_gt_0'], 3)} | {num(c['mde_sharpe_annualised'])} | {c['verdict']} |")
h = d["hypotheses"]
L += ["", f"H1 (A1 Sharpe > 0) p = {num(h['H1_p'], 3)}; H2 (A1 > B1, paired block bootstrap) p = {num(h['H2_p_A1_vs_B1'], 3)}; Holm rejections: {h['holm_reject']}.",
      f"PBO (CSCV, 16 splits, A1/A0/V0) = {num(d['pbo_cscv']['pbo'], 3)} (threshold <= 0.25).", "",
      "## Circuit breaker impact (from the ON runs; no OFF counterfactual was run)", "",
      "| | halt time | equity at halt | drawdown at halt | share of period traded | days flat after liquidation | liquidation fills | candles to flat | liquidation P&L | entries blocked |", "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
for n in ("A1", "A0", "V0", "A1_stress"):
    b = V[n]["breaker"]
    hl = b["halts"][0] if b["halts"] else None
    lq = b.get("liquidation", {})
    L.append(f"| {n} | {hl['time'][:16] if hl else 'none'} | {num(hl['equity'], 0) if hl else 'n/a'} | {pct(hl['drawdown']) if hl else 'n/a'} | {pct(b['period_traded_share'])} | {num(b.get('days_flat_after_halt'), 0)} | {lq.get('fills', 0)} | {lq.get('candles_to_flat', 0)} | {num(lq.get('net_pnl'), 2)} | {b['entries_blocked']} |")  # fmt: skip
L += ["", "Liquidation fills (A1): " + "; ".join(f"{x['time'][:16]} {x['pair']} {x['amount']:.4f} @ {x['price']:.2f} P&L {x['pnl']:.2f}" for x in V["A1"]["breaker"]["liquidation"]["by_fill"]), "",
      "## Performance by market regime (BTC daily regime, previous completed day)", "", "| | regime | days | total return in those days | episodes opened | PF of episodes |", "|---|---|---|---|---|---|"]  # fmt: skip
for n in ("A1", "A0", "V0"):
    for r in ("bull", "bear", "sideways"):
        rd, rt = V[n]["regime_daily"][r], V[n]["regimes_trades"].get(r, {})
        L.append(f"| {n} | {r} | {rd['days']} | {pct(rd['total_return'])} | {rt.get('trades', 0)} | {num(rt.get('profit_factor'))} |")
L += ["", "## Costs and stress sensitivity", "", "| | gross P&L at reference prices | net P&L | total fees+slippage | traded notional |", "|---|---|---|---|---|"]  # fmt: skip
for n in ("A1", "A0", "V0", "A1_stress"):
    c = V[n]["costs"]
    L.append(f"| {n} | {num(c.get('gross_profit_at_reference'), 1)} | {num(c.get('net_profit'), 1)} | {num(c['total_cost'], 1)} | {num(c.get('traded_notional'), 0)} |")
a, s = V["A1"]["stats"], V["A1_stress"]["stats"]
L += ["", f"A1 at 2x costs: net {pct(s['net_return'])} vs {pct(a['net_return'])} at base costs (difference {pct(s['net_return'] - a['net_return'])}). Costs are negligible next to the effect of the halt.", "",
      "## Windows (nine 6-month windows, return) and concentration", "", "| | " + " | ".join(w["start"][:7] for w in V["A1"]["windows"]) + " |", "|---|" + "---|" * len(V["A1"]["windows"])]  # fmt: skip
for n in ("A1", "A0", "V0"):
    L.append(f"| {n} | " + " | ".join(pct(w["return"]) for w in V[n]["windows"]) + " |")
for n in ("A1", "A0", "V0"):
    L.append(f"\n{n} profit share by pair: " + ", ".join(f"{k} {pct(x, 0)}" for k, x in sorted(V[n]["pair_profit_share"].items(), key=lambda kv: -kv[1])))
L += ["", "## Causality checks (T10 for an engine strategy)", ""]
for n, c in d["causality"].items():
    L.append(f"- {n}: clean = {c['clean']}; checks: " + ", ".join(f"{k.replace('_', ' ')}: {'clean' if not v else v}" for k, v in c["checks"].items()))
(HERE / "evaluation_report.md").write_text("\n".join(L) + "\n")
print("report and charts written")
