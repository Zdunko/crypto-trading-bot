"""Run the registered H1 L1 evaluation (M3). Guarded: it refuses to run unless the family is registered in the
research budget, the owner approval for the exact specification hash exists and no market run was consumed.

    python -m quantlab.l1_run guard                      # check the registration only
    python -m quantlab.l1_run fetch  --store DIR         # fetch the pinned 1d files (research source, rate limited)
    python -m quantlab.l1_run run    --store DIR --out F # the single registered evaluation

Everything else (formulas, rules, thresholds) is in ``l1_max3`` and the frozen registration."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from quantlab import budget
from quantlab import l1_max3 as m


QUANT = Path(__file__).resolve().parents[1]
APPROVALS = QUANT / "protocol/run_approvals.json"
FAMILY_ID = "h1_lottery_max3"
DATASET = QUANT / "dataset"
BONFERRONI_N = 45


class GuardError(Exception):
    pass


def guard(spec: dict) -> str:
    b = json.loads(budget.BUDGET.read_text(encoding="utf-8"))
    ok, why = budget.can_start_run(b, FAMILY_ID)
    if not ok:
        raise GuardError(f"budget: {why}")
    h = m.spec_sha256(spec)
    appr = json.loads(APPROVALS.read_text(encoding="utf-8")).get("approvals", [])
    if not any(
        a.get("family_id") == FAMILY_ID and a.get("approved_by") == "owner" and a.get("spec_hash") == h
        and isinstance(a.get("text_sha256"), str) and len(a["text_sha256"]) == 64
        for a in appr
    ):  # fmt: skip
        raise GuardError("no owner approval for this exact specification hash")
    return h


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=True, default=float)


def run_evaluation(panel: m.Panel, spec: dict) -> dict:
    """Pure function of the panel and the frozen spec: both configurations, Holm, disguise, checks, decision."""
    results = {}
    for cfg in spec["configurations"]:
        results[cfg["id"]] = m.evaluate(
            panel, spec, cfg["horizon_days"], seed_offset=cfg["horizon_days"]
        )
    ev = spec["evaluation"]
    sg = spec["signal"]
    sig = m.max3(panel.close, panel.epoch_start, sg["window_days"], sg["top_k"])
    first = int(panel.dates.searchsorted(m.pd.Timestamp(ev["first_signal_date"], tz="UTC")))
    dis = m.disguise(
        sig,
        panel.close,
        panel.member,
        first,
        spec["statistics"]["min_assets_per_day"],
        spec["disguise"]["bound"],
    )
    # causality: the signal computed on data truncated at a date equals the full-panel signal up to that date
    prefix_ok, prefix = True, {}
    for d in spec["causality_and_reproducibility_checks"]["prefix_invariance_dates"]:
        i = int(panel.dates.searchsorted(m.pd.Timestamp(d, tz="UTC")))
        part = m.max3(
            panel.close[: i + 1], panel.epoch_start[: i + 1], sg["window_days"], sg["top_k"]
        )
        same = bool(np.array_equal(part, sig[: i + 1], equal_nan=True))
        prefix[d] = same
        prefix_ok &= same
    dec = m.decide(spec, results, dis, prefix_ok)
    ps = [results[c["id"]]["p_one_sided_raw"] for c in spec["configurations"]]
    sens = {c["id"]: {"p_raw": p, "bonferroni_program_wide_alpha": 0.05 / BONFERRONI_N, "would_pass_program_wide": p <= 0.05 / BONFERRONI_N}
            for c, p in zip(spec["configurations"], ps, strict=True)}  # fmt: skip
    panel_facts = {
        "n_days_panel": len(panel.dates), "n_symbols_loaded": len(panel.symbols),
        "first_date": str(panel.dates[0].date()), "last_date": str(panel.dates[-1].date()),
        "symbols_ever_member": int(panel.member.any(axis=0).sum()),
    }  # fmt: skip
    return {"configurations": results, "decision": dec, "disguise": dis, "prefix_invariance": prefix,
            "program_wide_sensitivity_not_gating": sens, "panel": panel_facts}  # fmt: skip


def result_hash(doc: dict) -> str:
    return hashlib.sha256(canonical(doc).encode()).hexdigest()


def cmd_fetch(spec: dict, store_dir: str, rate: float) -> int:
    from quantlab import pit_fetch as pf
    from quantlab import pit_loader as pl

    ds = pl.PitDataset.open(DATASET, store_dir)
    ev, un = spec["evaluation"], spec["universe"]
    first_month = ev["panel_first_candle_open"][:7]
    last_month = ev["last_candle_open"][:7]
    months = sorted({f"{y}-{mo:02d}" for y in range(2020, 2026) for mo in range(1, 13)})
    months = [x for x in months if first_month <= x <= last_month]
    symbols: set[str] = {ev["regime"]["reference_symbol"]}
    for mo in months:
        if mo >= "2021-01":
            symbols |= set(
                ds.universe_at(
                    m.pd.Timestamp(mo + "-01", tz="UTC"), un["threshold"], un["max_stale_days"]
                )
            )
    client = pf.Client(pf.HttpTransport(), pf.RateLimiter(rate))
    store = pf.Store(store_dir)
    jobs = [(s, mo) for s in sorted(symbols) for mo in months if mo in ds.listing.get(s, [])]
    done = 0
    for s, mo in jobs:
        pf.fetch_file(client, store, s, "1d", mo)
        done += 1
    print(f"fetched/verified {done} daily files for {len(symbols)} symbols")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["guard", "fetch", "run", "repro"])
    ap.add_argument("--store")
    ap.add_argument("--out")
    ap.add_argument("--rate", type=float, default=20.0)
    a = ap.parse_args(argv)
    spec = json.loads(m.PREREG.read_text(encoding="utf-8"))
    if a.cmd == "guard":
        print("guard ok, spec hash", guard(spec))
        return 0
    if a.cmd == "fetch":
        guard(spec)
        return cmd_fetch(spec, a.store, a.rate)
    from quantlab import pit_loader as pl

    h = guard(spec)
    ds = pl.PitDataset.open(DATASET, a.store)
    panel = m.load_panel(ds, spec)
    doc = run_evaluation(panel, spec)
    doc["spec_sha256"] = h
    doc["dataset_hash"] = ds.manifest["dataset_hash"]
    doc["code_sha256"] = hashlib.sha256(
        Path(m.__file__).read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    again = run_evaluation(panel, spec)
    again["spec_sha256"], again["dataset_hash"], again["code_sha256"] = (
        h,
        doc["dataset_hash"],
        doc["code_sha256"],
    )
    doc["reproducibility"] = {
        "second_run_in_process_identical": result_hash(doc) == result_hash(again),
        "result_sha256": result_hash(doc),
    }
    if a.cmd == "repro":
        print(doc["reproducibility"]["result_sha256"])
        return 0
    sub = subprocess.run(
        [sys.executable, "-m", "quantlab.l1_run", "repro", "--store", a.store],
        capture_output=True,
        text=True,
        cwd=QUANT,
        check=False,
    )
    sub_hash = (
        sub.stdout.strip().splitlines()[-1] if sub.returncode == 0 and sub.stdout.strip() else None
    )
    doc["reproducibility"]["separate_process_sha256"] = sub_hash
    doc["reproducibility"]["separate_process_identical"] = (
        sub_hash == doc["reproducibility"]["result_sha256"]
    )
    ok = (
        doc["reproducibility"]["second_run_in_process_identical"]
        and doc["reproducibility"]["separate_process_identical"]
    )
    doc["decision"]["reproducibility_and_causality_checks_ok"] = bool(
        ok and all(doc["prefix_invariance"].values())
    )
    doc["decision"]["L1_PASS"] = bool(
        any(c["passes"] for c in doc["decision"]["configurations"].values())
        and doc["decision"]["disguise_passes"]
        and doc["decision"]["reproducibility_and_causality_checks_ok"]
    )
    doc["decision"]["decision"] = (
        "L1 PASS"
        if doc["decision"]["L1_PASS"]
        else "NO-GO: H1 is terminated (no variants, windows, horizons or filters)"
    )
    Path(a.out).write_text(
        json.dumps(doc, indent=1, sort_keys=True, default=float) + "\n", encoding="utf-8"
    )
    print(doc["decision"]["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
