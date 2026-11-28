"""M4 / L2 runner: guarded single replay of the registered economic-viability evaluation plus the registered
verification diagnostics.

    python -m quantlab.l2_run guard
    python -m quantlab.l2_run run  --store DIR --out FILE      # the single registered replay
    python -m quantlab.l2_run repro --store DIR                # engine hashes only (cross-process reproducibility)

All rules are in ``protocol/m4_l2_preregistration.json`` and ``quantlab.l2_portfolio``; nothing is tuned here."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quantlab import l1_max3 as l1
from quantlab import l2_portfolio as l2
from quantlab.execution import PriceData


QUANT = Path(__file__).resolve().parents[1]
APPROVALS = QUANT / "protocol/run_approvals.json"
BUDGET = QUANT / "protocol/research_budget.json"
FAMILY_ID = "h1_lottery_max3"
DATASET = QUANT / "dataset"


class GuardError(Exception):
    pass


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def guard(spec: dict, budget_path: Path | None = None, approvals_path: Path | None = None) -> str:
    """Budget: N unchanged, the family exists, its single L1 market run is consumed and its one approved diagnostic
    replay (protocol V2 section 8) is available; approval: an owner entry for THIS exact specification hash."""
    b = json.loads((budget_path or BUDGET).read_text(encoding="utf-8"))
    st = b["state"]
    fam = next((f for f in st["further_families"] if f["id"] == FAMILY_ID), None)
    if fam is None or st["total_n"] != 45 or fam["configurations"] != 2:
        raise GuardError("family not registered with N = 45 and two configurations")
    if fam.get("diagnostic_replays_used", 0) >= b["caps"].get(
        "max_diagnostic_replays_per_family", 1
    ):
        raise GuardError("the approved diagnostic replay of this family is already used")
    h = spec_hash(spec)
    appr = json.loads((approvals_path or APPROVALS).read_text(encoding="utf-8")).get(
        "approvals", []
    )
    if not any(
        a.get("family_id") == FAMILY_ID and a.get("approved_by") == "owner" and a.get("spec_hash") == h
        and a.get("scope", "").startswith("L2") and len(a.get("text_sha256", "")) == 64
        for a in appr
    ):  # fmt: skip
        raise GuardError("no owner approval (scope L2) for this exact specification hash")
    return h


# ------------------------------------------------------------------------------------------ data
def load_hourly(ds, panel: l1.Panel, spec: dict) -> PriceData:
    ev = spec["evaluation"]
    first = pd.Timestamp(ev["hourly_first_candle_open"], tz="UTC")
    as_of = pd.Timestamp(
        ev["hourly_as_of"], tz="UTC"
    )  # candles completed at as_of; the loader refuses the holdout
    idx = pd.date_range(first, as_of - pd.Timedelta(hours=1), freq="1h", tz="UTC")
    cand: dict[str, pd.DataFrame] = {}
    for s in panel.symbols:
        df = ds.candles(s, "1h", as_of, start=first, allow_gaps=True)
        if len(df):
            cand[l2.pair_of(s)] = df[["date", "open", "high", "low", "close", "volume"]]
    return PriceData(cand, idx)


def load_qvol(ds, panel: l1.Panel, spec: dict) -> np.ndarray:
    ev = spec["evaluation"]
    first, last = panel.dates[0], panel.dates[-1]
    out = np.full(panel.open.shape, np.nan)
    for j, s in enumerate(panel.symbols):
        df = ds.candles(s, "1d", last + pd.Timedelta(days=1), start=first, allow_gaps=True)
        pos = panel.dates.get_indexer(df["date"])
        ok = pos >= 0
        out[pos[ok], j] = df["quote_volume"].to_numpy()[ok]
    _ = ev
    return out


# ------------------------------------------------------------------------------------------ evaluation
def daily_returns(eq_hourly: pd.Series, wallet: float) -> np.ndarray:
    return l2.daily_equity(eq_hourly, wallet).pct_change().dropna().to_numpy()


def passive(panel: l1.Panel, spec: dict, costs, kind: str) -> dict:
    """Daily accounting over the same days as the strategy: the series starts on the day BEFORE the first rebalance day
    (flat), the first trade is at the open of the first rebalance day."""
    p = spec["portfolio"]
    i0 = int(panel.dates.searchsorted(pd.Timestamp(p["first_rebalance_day"], tz="UTC"))) - 1
    i1 = int(panel.dates.searchsorted(pd.Timestamp(p["last_rebalance_day"], tz="UTC"))) + 1
    o, c = panel.open[i0:i1], panel.close[i0:i1]
    dates = panel.dates[i0:i1]
    weights: dict[int, np.ndarray] = {}
    if kind == "btc_buy_hold":
        w = np.zeros(o.shape[1])
        w[panel.symbols.index(spec["evaluation"]["regime"]["reference_symbol"])] = 1.0
        weights[1] = w
    else:  # equal weight over the point-in-time members, rebalanced on the first day of every month
        for k, d in enumerate(dates):
            if k >= 1 and (k == 1 or d.day == 1):
                ok = panel.member[i0 + k] & np.isfinite(o[k]) & (o[k] > 0)
                if ok.any():
                    weights[k] = ok / ok.sum()
    eq = l2.passive_equity(o, c, weights, costs, p["wallet"])
    de = pd.Series(
        np.concatenate([[p["wallet"]], eq]), index=[dates[0] - pd.Timedelta(days=1), *dates]
    )
    r = de.pct_change().dropna().to_numpy()
    years = (len(de) - 1) / l2.DAYS_PER_YEAR
    sd = float(r.std(ddof=1))
    dd = float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)))
    peak = np.maximum.accumulate(de.to_numpy())
    mdd = float(np.max(1.0 - de.to_numpy() / peak))
    end = float(de.iloc[-1])
    cagr = (end / p["wallet"]) ** (1 / years) - 1
    return {"final_equity": end, "net_return": end / p["wallet"] - 1, "cagr": cagr, "sharpe": float(r.mean() / sd * np.sqrt(365)),
            "sortino": float(r.mean() / dd * np.sqrt(365)), "max_drawdown": mdd, "calmar": float(cagr / mdd) if mdd > 0 else 0.0,
            "daily_returns": r.tolist(), "years": years}  # fmt: skip


def evaluate_config(
    data: PriceData, panel: l1.Panel, spec: dict, h: int, feed, schedules: dict, bench: dict
) -> tuple[dict, dict]:
    p = spec["portfolio"]
    wallet = p["wallet"]
    cfg_out: dict = {}
    hashes: dict = {}
    rets: dict = {}
    for cname, costs in l2.COSTS.items():
        for tag, sched, with_risk in (
            ("strategy", schedules["maxs"], True),
            ("low_volatility", schedules["lowvol"], True),
            ("strategy_no_risk", schedules["maxs"], False),
        ):
            out = l2.run_active(data, sched, spec, costs, with_risk, feed if with_risk else None)
            m = l2.metrics(out.equity, wallet)
            de = l2.daily_equity(out.equity, wallet)
            ex = l2.execution_stats(out, costs, float(de.mean()), m["years"])
            rec = {"metrics": m, "execution": ex, "fill_ratio": ex["fill_ratio"]}
            if with_risk:
                rec["capital_protection"] = l2.capital_protection(
                    out, wallet, spec["risk"]["drawdown_limit"]
                )
            cfg_out.setdefault(cname, {})[tag] = rec
            hashes[f"h{h}|{cname}|{tag}"] = out.hash
            rets[(cname, tag)] = daily_returns(out.equity, wallet)
    lag = spec["statistics"]["daily_hac_lag"]
    res: dict = {}
    for cname in l2.COSTS:
        s_rec = cfg_out[cname].pop("strategy")
        res[cname] = {
            **s_rec,
            "low_volatility": cfg_out[cname]["low_volatility"],
            "no_risk_diagnostic": cfg_out[cname]["strategy_no_risk"],
        }
    r_s, r_l = rets[("normal", "strategy")], rets[("normal", "low_volatility")]
    n = min(
        len(r_s), len(r_l)
    )  # both series start on the day before the first rebalance day and end on the same day
    res["incremental_vs_low_volatility"] = l2.paired_test(r_s[:n], r_l[:n], lag)
    res["alpha_vs_low_volatility"] = l2.alpha_regression(r_s[:n], r_l[:n], lag)
    btc = np.array(bench["btc_buy_hold"]["normal"]["daily_returns"])
    m_ = min(len(r_s), len(btc))
    res["alpha_vs_btc"] = l2.alpha_regression(r_s[:m_], btc[:m_], lag)
    rm, w = l2.risk_matched_returns(r_s[:m_], btc[:m_])
    eq_rm = wallet * np.cumprod(1 + rm)
    peak = np.maximum.accumulate(eq_rm)
    sd, dd = float(rm.std(ddof=1)), float(np.sqrt(np.mean(np.minimum(rm, 0) ** 2)))
    res["risk_matched_btc_cash_ex_post"] = {"btc_weight": w, "net_return": float(eq_rm[-1] / wallet - 1),
        "sharpe": float(rm.mean() / sd * np.sqrt(365)), "sortino": float(rm.mean() / dd * np.sqrt(365)),
        "max_drawdown": float(np.max(1 - eq_rm / peak)), "non_tradable_label": "ex post, never gates"}  # fmt: skip
    res["benchmarks"] = {
        k: {kk: vv for kk, vv in v["normal"].items() if kk != "daily_returns"}
        for k, v in bench.items()
    }
    res["benchmarks_double_costs"] = {
        k: {kk: vv for kk, vv in v["double"].items() if kk != "daily_returns"}
        for k, v in bench.items()
    }
    res["benchmarks"]["cash"] = {
        "net_return": 0.0,
        "sortino": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "cagr": 0.0,
    }
    return res, hashes


def run_replay(
    ds, panel: l1.Panel, spec: dict, data: PriceData, feed, with_diagnostics: bool = True
) -> dict:
    sg = spec["signal"]
    maxs = l1.max3(panel.close, panel.epoch_start, sg["window_days"], sg["top_k"])
    vols = l2.vol_scores(panel, spec)
    bench = {
        k: {c: passive(panel, spec, costs, k) for c, costs in l2.COSTS.items()}
        for k in ("btc_buy_hold", "equal_weight")
    }
    per_config: dict = {}
    hashes: dict = {}
    for cfg in spec["configurations"]:
        h = cfg["horizon_days"]
        schedules = {
            "maxs": l2.target_schedule(panel, spec, h, maxs),
            "lowvol": l2.target_schedule(panel, spec, h, vols),
        }
        res, hs = evaluate_config(data, panel, spec, h, feed, schedules, bench)
        res["schedule_facts"] = {"rebalances": len(schedules["maxs"]), "mean_target_size": float(np.mean([len(v) for v in schedules["maxs"].values() if v] or [0])),
                                 "empty_rebalances": int(sum(1 for v in schedules["maxs"].values() if not v))}  # fmt: skip
        per_config[cfg["id"]] = res
        hashes.update(hs)
    return {"per_config": per_config, "engine_hashes": hashes}


def final_doc(spec: dict, core: dict) -> dict:
    decision = l2.decide_config(spec, core["per_config"])
    return {
        "configurations": core["per_config"],
        "decision": decision,
        "engine_hashes": core["engine_hashes"],
    }


def canonical(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=float)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["guard", "run", "repro"])
    ap.add_argument("--store")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    spec = json.loads(l2.PREREG.read_text(encoding="utf-8"))
    if a.cmd == "guard":
        print("guard ok, spec hash", guard(spec))
        return 0
    from quantlab import l2_diagnostics as dg
    from quantlab import pit_loader as pl

    h = guard(spec)
    l1spec = json.loads(l1.PREREG.read_text(encoding="utf-8"))
    ds = pl.PitDataset.open(DATASET, a.store)
    panel = l1.load_panel(ds, l1spec)
    data = load_hourly(ds, panel, spec)
    pairs = {l2.pair_of(s) for s in panel.symbols}
    feed = l2.final_epoch_feed(DATASET, pairs, spec)
    core = run_replay(ds, panel, spec, data, feed)
    if a.cmd == "repro":
        print(hashlib.sha256(canonical(core["engine_hashes"]).encode()).hexdigest())
        return 0
    doc = final_doc(spec, core)
    doc["spec_sha256"], doc["dataset_hash"] = h, ds.manifest["dataset_hash"]
    doc["code_sha256"] = {f: hashlib.sha256(Path(QUANT / f).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                          for f in ("quantlab/l2_portfolio.py", "quantlab/l2_run.py", "quantlab/l2_diagnostics.py", "quantlab/l1_max3.py")}  # fmt: skip
    doc["verification"] = dg.run_diagnostics(ds, panel, spec, l1spec, load_qvol(ds, panel, spec))
    again = run_replay(ds, panel, spec, data, feed)
    doc["reproducibility"] = {"engine_hashes_second_run_identical": again["engine_hashes"] == core["engine_hashes"],
                              "engine_hashes_sha256": hashlib.sha256(canonical(core["engine_hashes"]).encode()).hexdigest()}  # fmt: skip
    import subprocess

    sub = subprocess.run(
        [sys.executable, "-m", "quantlab.l2_run", "repro", "--store", a.store],
        capture_output=True,
        text=True,
        cwd=QUANT,
        check=False,
    )
    sub_hash = (
        sub.stdout.strip().splitlines()[-1] if sub.returncode == 0 and sub.stdout.strip() else None
    )
    doc["reproducibility"]["separate_process_engine_hashes_sha256"] = sub_hash
    doc["reproducibility"]["separate_process_identical"] = (
        sub_hash == doc["reproducibility"]["engine_hashes_sha256"]
    )
    Path(a.out).write_text(
        json.dumps(doc, indent=1, sort_keys=True, default=float) + "\n", encoding="utf-8"
    )
    for cid, d in doc["decision"].items():
        print(cid, d["decision"], d["failed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
