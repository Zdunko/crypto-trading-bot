"""S4: build the deterministic dataset tables from fetched raw files and validate causality.

``build`` writes quant/dataset/{manifest.json, files.csv.gz, epochs.csv.gz, membership.csv.gz,
quality_summary.json} (deterministic) and provenance_run.json (non-deterministic run facts).
``validate`` produces causality / perturbation / archive-stability evidence on the real data.
Development window only; no returns or strategy are computed anywhere.
"""

from __future__ import annotations

import gzip
import json
import random
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from quantlab import pit_universe as pu
from quantlab.pit_fetch import DEV_END, FileRecord, Store


QUANT = Path(__file__).resolve().parents[1]
CRITERIA = QUANT / "docs/phase4c/s4_criteria.json"
CLASSIFICATION = QUANT / "dataset/asset_classification.json"
S3_PINS = QUANT / "docs/phase4c/s3_pin_manifest.tsv.gz"
CODE_FILES = ["pit_fetch.py", "pit_universe.py", "pit_run.py", "pit_build.py", "data_audit.py"]
SEED = 20261126


def gz(path: Path, text: str) -> None:
    with path.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as g:
        g.write(text.encode())


def norm_sha(p: Path) -> str:
    return pu.sha(p.read_bytes().replace(b"\r\n", b"\n"))


def _scan(args):
    rec, path = args
    rec = FileRecord(**rec)
    data = Path(path).read_bytes() if rec.status != "absent" and Path(path).exists() else None
    return pu.scan_file(rec, data)


def load_scans(
    raw: Path, listing: dict[str, list[str]], allow_incomplete: bool = False
) -> list[pu.FileScan]:
    store = Store(raw / "files")
    jobs: list = []
    missing: list[pu.FileScan] = []
    for itv in ("1d", "1h"):
        for s in sorted(listing):
            for m in listing[s]:
                rec = store.cached(s, itv, m)
                if rec is None:
                    if not allow_incomplete:
                        raise SystemExit(f"fetch incomplete (fail closed): {s} {itv} {m}")
                    missing.append(pu.FileScan(s, itv, m, "quarantined", ["fetch_failed"]))
                    continue
                jobs.append((rec.__dict__, str(store.paths(s, itv, m)[0])))
    with ProcessPoolExecutor(4) as ex:
        scans = list(ex.map(_scan, jobs, chunksize=64))
    for sc in scans:
        if sc.interval == "1h" and sc.status == "absent":
            sc.reasons = ["absent_expected"]  # the daily file of the same month exists
    return scans + missing


def series_from(scans: list[pu.FileScan]) -> dict[str, list[tuple[int, float, float]]]:
    out: dict[str, list] = {}
    for sc in scans:
        if sc.interval == "1d" and sc.status == "ok":
            out.setdefault(sc.symbol, []).extend(sc.candles)
    return {s: sorted(set(c)) for s, c in sorted(out.items())}


def files_csv(scans: list[pu.FileScan], recs: dict) -> str:
    rows = []
    for sc in sorted(scans, key=lambda x: (x.interval, x.symbol, x.month)):
        r = recs[(sc.symbol, sc.interval, sc.month)]
        rows.append(
            [
                sc.interval,
                sc.symbol,
                sc.month,
                sc.status,
                "|".join(sc.reasons),
                sc.rows,
                sc.missing,
                json.dumps(sc.warnings, sort_keys=True, separators=(",", ":")),
                r.sha256,
                r.published_sha256,
                r.size,
            ]
        )
    hdr = ["interval", "symbol", "month", "status", "reasons", "rows", "missing_inside_span",
           "warnings", "sha256", "published_sha256", "size"]  # fmt: skip
    return pu.csv_text(hdr, rows)


def x1_consistency(scans: list[pu.FileScan], daily_vol: dict) -> dict:
    hourly = {(s.symbol, s.month): s for s in scans if s.interval == "1h" and s.status == "ok"}
    ok = bad = 0
    first_ok = first_bad = 0
    seen = set()
    for (sym, m), h in sorted(hourly.items()):
        d = daily_vol.get((sym, m))
        if d is None:
            continue
        match = all(
            abs(h.day_volume.get(t, 0.0) - v) <= 1e-6 * max(abs(v), 1.0) for t, v in d.items()
        ) and set(h.day_volume) == set(d)
        ok += match
        bad += not match
        if sym not in seen:
            seen.add(sym)
            first_ok += (min(h.day_volume) == min(d)) if h.day_volume and d else 0
            first_bad += not ((min(h.day_volume) == min(d)) if h.day_volume and d else 1)
    n = ok + bad
    return {"months_compared": n, "volume_consistent": ok, "volume_inconsistent": bad,
            "share_consistent": ok / n if n else None,
            "first_candle_day_agrees": first_ok, "first_candle_day_differs": first_bad}  # fmt: skip


def build(
    raw: Path, out: Path, classification: Path = CLASSIFICATION, allow_incomplete: bool = False
) -> dict:
    listing = json.loads((raw / "listing.json").read_text(encoding="utf-8"))
    store = Store(raw / "files")
    blank = FileRecord("", "", "", "absent")
    recs = {
        (s, itv, m): store.cached(s, itv, m) or blank
        for itv in ("1d", "1h")
        for s in listing
        for m in listing[s]
    }
    scans = load_scans(raw, listing, allow_incomplete)
    classes = pu.load_classification(classification)
    chk = pu.classification_check(classes, sorted(listing))
    if chk["unreviewed"]:
        raise SystemExit(f"classification_unreviewed (fail closed): {chk['unreviewed']}")
    series = series_from(scans)
    dates = pu.month_starts()
    members = pu.membership(series, classes, dates)
    epochs = pu.epochs_table(series)
    daily_vol = {
        (s.symbol, s.month): s.day_volume for s in scans if s.interval == "1d" and s.status == "ok"
    }
    files_text = files_csv(scans, recs)
    epochs_text = pu.csv_text(
        ["symbol", "k", "start_ms", "start_reason", "end_ms", "candles"],
        [[e.symbol, e.k, e.start, e.start_reason, e.end, e.n] for e in epochs],
    )
    member_text = pu.csv_text(["date", "threshold", "epoch_id", "days_since_last_candle"], members)
    class_sha = pu.sha(classification.read_bytes().replace(b"\r\n", b"\n"))
    params = {
        "window_days": pu.WINDOW_DAYS, "min_days": pu.MIN_DAYS, "thresholds": pu.THRESHOLDS,
        "gap_months": pu.GAP_MONTHS, "jump": pu.JUMP, "dev_end_exclusive": DEV_END,
        "dates": [dates[0], dates[-1]], "quote": "USDT",
    }  # fmt: skip
    parts = {
        "files": pu.sha(files_text), "epochs": pu.sha(epochs_text),
        "membership": pu.sha(member_text), "classification": class_sha,
    }  # fmt: skip
    reasons = Counter(r for sc in scans for r in sc.reasons)
    status = Counter((sc.interval, sc.status) for sc in scans)
    ev = Counter(e.start_reason for e in epochs if e.k > 0)
    manifest = {
        "id": "S4-dataset-manifest",
        "source": "Binance Vision spot monthly klines (c) Binance, CC BY-NC-SA 4.0, attribution Binance Vision; non-commercial research only",
        "window": "months 2017-08 .. 2025-06",
        "params": params, "parts": parts, "dataset_hash": pu.dataset_hash(parts, params),
        "code_sha256": {f: norm_sha(Path(__file__).parent / f) for f in CODE_FILES},
        "criteria_sha256": norm_sha(CRITERIA),
        "listing_sha256": pu.sha(pu.canon(listing)),
        "counts": {"symbols": len(listing), "files": len(scans), "epochs": len(epochs),
                   "membership_rows": len(members),
                   "status": {f"{k[0]}:{k[1]}": v for k, v in sorted(status.items())}},
        "reason_counts": dict(sorted(reasons.items())),
        "identity_events": dict(sorted(ev.items())),
    }  # fmt: skip
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8"
    )
    gz(out / "files.csv.gz", files_text)
    gz(out / "epochs.csv.gz", epochs_text)
    gz(out / "membership.csv.gz", member_text)
    depth = {}
    for tn in pu.THRESHOLDS:
        depth[tn] = {d: sum(1 for r in members if r[0] == d and r[1] == tn) for d in dates}
    summary = {
        "depth_by_date": depth, "x1": x1_consistency(scans, daily_vol),
        "classification_suspect_assets": chk["suspect_asset"],
        "warning_counts": dict(Counter(k for sc in scans for k in sc.warnings)),
        "warning_files": dict(Counter(k for sc in scans for k in sc.warnings)),
    }  # fmt: skip
    (out / "quality_summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8"
    )
    print("dataset_hash", manifest["dataset_hash"])
    return manifest


# ---------------------------------------------------------------------------- validation
def _rows_at(members, d: str):
    return sorted((r[1], r[2], r[3]) for r in members if r[0] == d)


def perturb(series, t_ms: int, mode: str, rnd: random.Random):
    """Adversarially change every candle NOT completed at T (open + 1 day > T)."""
    out = {}
    for s, c in series.items():
        keep = [x for x in c if x[0] + pu.DAY <= t_ms]
        fut = [x for x in c if x[0] + pu.DAY > t_ms]
        if mode == "volume_x1000":
            fut = [(t, p, q * 1000) for t, p, q in fut]
        elif mode == "volume_zero":
            fut = [(t, p, 0.0) for t, p, q in fut]
        elif mode == "price_x1000":
            fut = [(t, p * 1000, q) for t, p, q in fut]
        elif mode == "delete":
            fut = []
        elif mode == "duplicate":
            fut = fut + fut[: len(fut) // 2]
        elif mode == "random":
            fut = [
                (t, p * rnd.choice([0.001, 1, 1000]), q * rnd.choice([0, 1, 1000]))
                for t, p, q in fut
            ]
        out[s] = keep + fut
    return out


def validate(raw: Path, out: Path) -> dict:
    listing = json.loads((raw / "listing.json").read_text(encoding="utf-8"))
    scans = [s for s in load_scans(raw, listing) if s.interval == "1d"]
    series = series_from(scans)
    classes = pu.load_classification(CLASSIFICATION)
    members = [
        (a, b, c, int(d))
        for a, b, c, d in (
            r.split(",")
            for r in gzip.open(out / "membership.csv.gz", "rt", encoding="utf-8")
            .read()
            .splitlines()[1:]
        )
    ]
    dates = [d for d in pu.month_starts("2019-01", "2025-06")]
    rnd = random.Random(SEED)
    res: dict = {"seed": SEED}
    # I1: epoch tables on truncated data == full-data table at each cutoff
    full = pu.epochs_table(series)
    cuts = rnd.sample(dates, 8)
    i1 = []
    for d in cuts:
        t = pu.ms_of(d)
        part = pu.epochs_table({s: pu.truncate(c, t) for s, c in series.items()})
        i1.append({"cutoff": d, "equal": pu.epoch_keys(full, t) == pu.epoch_keys(part, t)})
    res["I1"] = i1
    # I2: prefix invariance of membership
    i2 = []
    for d in rnd.sample(dates, 12):
        t = pu.ms_of(d)
        tr = {s: pu.truncate(c, t) for s, c in series.items()}
        got = sorted((r[1], r[2], r[3]) for r in pu.membership(tr, classes, [d]))
        i2.append({"date": d, "equal": got == _rows_at(members, d), "n": len(got)})
    res["I2"] = i2
    # U1: adversarial replacement of everything not completed at T
    u1 = []
    modes = ["volume_x1000", "volume_zero", "price_x1000", "delete", "duplicate", "random"]
    for d in rnd.sample(dates, 20):
        t = pu.ms_of(d)
        exp = _rows_at(members, d)
        eq = {}
        for m in modes:
            got = sorted(
                (r[1], r[2], r[3]) for r in pu.membership(perturb(series, t, m, rnd), classes, [d])
            )
            eq[m] = got == exp
        u1.append({"date": d, "equal_by_mode": eq})
    res["U1"] = u1
    # B2: nothing at or after the cutoff exists in the series
    last = max(c[-1][0] for c in series.values() if c)
    res["B2"] = {"max_candle_open_ms": last, "all_before_cutoff": last < pu.ms_of(DEV_END)}
    # U2/S2 survivorship
    cutoff_ms = pu.ms_of("2025-06")
    ended = {e.eid for e in full if e.end < cutoff_ms}
    ever = {r[2] for r in members if r[1] == "1M"}
    res["U2"] = {"epochs_ended_before_2025_06": len(ended), "members_ever_1M": len(ever),
                 "ended_members_ever_1M": len(ever & ended)}  # fmt: skip
    coh = {}
    for d in ("2021-01", "2022-01", "2023-01", "2024-01", "2025-01"):
        cohort = [r[2] for r in members if r[0] == d and r[1] == "1M"]
        coh[d] = {
            "members": len(cohort),
            "ended_before_2025_06": len([x for x in cohort if x in ended]),
        }
    res["S2"] = coh
    # U3 depth
    d1 = {
        d: sum(1 for r in members if r[0] == d and r[1] == "1M")
        for d in pu.month_starts("2021-01", "2025-06")
    }
    res["U3"] = {"min": min(d1.values()), "at": min(d1, key=lambda k: d1[k])}
    # B1: request logs
    bad_urls, n_urls = [], 0
    for f in sorted(raw.glob("requests*.log")):
        for line in f.read_text(encoding="utf-8").splitlines():
            u = line.split("\t")[-1]
            n_urls += 1
            if any(f"{y}-{m}" >= DEV_END for y, m in re.findall(r"-(\d{4})-(\d{2})(?!\d)", u)):
                bad_urls.append(u)
    res["B1"] = {"requests_audited": n_urls, "holdout_urls": bad_urls[:5], "count": len(bad_urls)}
    # F3: peak requests in any 1-second window, recomputed from the append-only log of all runs
    stamps = sorted(
        float(ln.split("\t")[0])
        for f in raw.glob("requests*.log")
        for ln in f.read_text(encoding="utf-8").splitlines()
        if "\t" in ln
    )
    peak, j = 0, 0
    for i, t in enumerate(stamps):
        while stamps[j] <= t - 1.0 + 1e-9:
            j += 1
        peak = max(peak, i - j + 1)
    fr = json.loads((raw / "fetch_report.json").read_text(encoding="utf-8"))
    res["F3"] = {
        "requests_logged": len(stamps),
        "configured_rate": fr["configured_rate"],
        "peak_in_any_1s_window": peak,
        "final_run_peak": fr["peak_requests_per_second"],
        "jobs": fr["jobs"],
    }
    res["F1_failures"] = len(fr["failures"])
    # R1 archive stability against the S3 pins
    s3 = {}
    for ln in gzip.open(S3_PINS, "rt", encoding="utf-8").read().splitlines():
        p = ln.split("\t")
        if p[0] == "1d" and p[3] == "200":
            s3[(p[1], p[2])] = p[4]
    files = gzip.open(out / "files.csv.gz", "rt", encoding="utf-8").read().splitlines()[1:]
    cur = {}
    for ln in files:
        p = ln.split(",")
        if p[0] == "1d":
            cur[(p[1], p[2])] = p[8]
    same = sum(1 for k, v in s3.items() if cur.get(k) == v)
    res["R1_stability"] = {"s3_pinned": len(s3), "identical_sha": same, "share": same / len(s3) if s3 else None,
                           "missing_now": sum(1 for k in s3 if k not in cur)}  # fmt: skip
    (out / "validation.json").write_text(
        json.dumps(res, indent=1, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in res.items() if k not in ("I1", "I2", "U1")}))
    print("I1", all(x["equal"] for x in i1), "I2", all(x["equal"] for x in i2),
          "U1", all(all(x["equal_by_mode"].values()) for x in u1))  # fmt: skip
    return res


def main(cmd: str, raw: Path, out: Path | None) -> int:
    out = out or QUANT / "dataset"
    if cmd == "build":
        build(raw, out)
    else:
        validate(raw, out)
    return 0
