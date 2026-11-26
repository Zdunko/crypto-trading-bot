"""S5-P3: why do 4.8 % of symbol-months disagree between daily volume and the sum of hourly volumes?

Descriptive, development window only, no returns. Reads the scratch raw store written by S4 (hash-pinned)
and the frozen S4 tables; writes s5_x1_investigation.json. Frozen S4 files are never modified.

    python x1_investigation.py RAW OUT_JSON
"""

import csv
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from quantlab import pit_universe as pu  # noqa: E402
from quantlab.pit_fetch import Store  # noqa: E402

DAY = pu.DAY
RAW = Path(sys.argv[1])
D = Path(__file__).resolve().parents[3] / "dataset"


def day_stats(args):
    sym, ym = args
    st = Store(RAW / "files")
    out = {}
    for itv in ("1d", "1h"):
        z, _ = st.paths(sym, itv, ym)
        rows = pu.read_rows(z.read_bytes())
        d = {}
        for r in rows:
            t = int(r[0])
            t = t // 1000 if len(str(t)) == 16 else t
            day = t - t % DAY
            e = d.setdefault(day, [0, 0.0, 0.0])
            e[0] += 1
            e[1] += float(r[5])
            e[2] += float(r[7])
        out[itv] = d
    return sym, ym, out


def main():
    files = list(csv.DictReader(gzip.open(D / "files.csv.gz", "rt", newline="")))
    ok = {(r["interval"], r["symbol"], r["month"]) for r in files if r["status"] == "ok"}
    jobs = sorted((s, m) for (i, s, m) in ok if i == "1d" and ("1h", s, m) in ok)
    with ProcessPoolExecutor(4) as ex:
        res = list(ex.map(day_stats, jobs, chunksize=64))
    cls_count, per_year, per_sym = Counter(), Counter(), Counter()
    tot_year = Counter()
    per_month = Counter()
    full_day_rel, signed = [], []
    inconsistent = []
    gap_days = full_days = 0
    alt = {
        "A": defaultdict(dict),
        "B": defaultdict(dict),
    }  # symbol -> day -> hourly-derived quote volume
    for sym, ym, o in res:
        dd, hh = o["1d"], o["1h"]
        tot_year[ym[:4]] += 1
        causes = set()
        for day, (n, v, q) in dd.items():
            h = hh.get(day)
            if h is None:
                causes.add("day_missing_in_hourly")
                continue
            nh, hv, hq = h
            full = nh == 24
            gap_days += not full
            full_days += full
            rel = (hv - v) / max(abs(v), 1e-300) if v else (0.0 if hv == 0 else 1.0)
            if abs(rel) > 1e-6:
                if not full:
                    causes.add(
                        "explained_by_hourly_gaps" if hv < v else "hourly_gap_but_hourly_greater"
                    )
                else:
                    causes.add("full_day_hourly_greater" if rel > 0 else "full_day_hourly_smaller")
                    full_day_rel.append(rel)
            if full:
                alt["A"][sym][day] = hq
            alt["B"][sym][day] = hq
        if set(hh) - set(dd):
            causes.add("day_missing_in_daily")
        if causes:
            prio = ["full_day_hourly_greater", "full_day_hourly_smaller", "hourly_gap_but_hourly_greater",
                    "day_missing_in_hourly", "day_missing_in_daily", "explained_by_hourly_gaps"]  # fmt: skip
            c = next(p for p in prio if p in causes)
            cls_count[c] += 1
            per_year[ym[:4]] += 1
            per_month[ym] += 1
            per_sym[sym] += 1
            inconsistent.append((sym, ym, c, sorted(causes)))
    q = lambda a, p: sorted(a)[int(p * (len(a) - 1))] if a else None  # noqa: E731
    sig = [r for r in full_day_rel]
    # ---- impact on eligibility: replace daily quote volume by hourly-derived volume (never touches S4 files)
    series, _ = None, None
    from quantlab.pit_run import series_from  # noqa: E402

    scans = []
    for sym, ym, _o in res:
        pass
    store = Store(RAW / "files")
    listing = json.loads((RAW / "listing.json").read_text())
    base = {}
    for s in sorted(listing):
        c = []
        for m in listing[s]:
            rec = store.cached(s, "1d", m)
            if rec is None or rec.status != "ok":
                continue
            sc = pu.scan_file(rec, store.paths(s, "1d", m)[0].read_bytes())
            if sc.status == "ok":
                c += sc.candles
        base[s] = sorted(set(c))
    classes = pu.load_classification(D / "asset_classification.json")
    dates = pu.month_starts()
    frozen = set()
    for r in csv.DictReader(gzip.open(D / "membership.csv.gz", "rt")):
        frozen.add((r["date"], r["threshold"], r["epoch_id"]))
    impact = {}
    changed = Counter()
    for name, mode in (("A_clean_hourly_days_only", "A"), ("B_all_hourly_days_incl_gaps", "B")):
        sub = {}
        for s, cs in base.items():
            a = alt[mode].get(s, {})
            sub[s] = [(t, p, a.get(t, qv)) for t, p, qv in cs]
            changed[name] += sum(
                1 for t, _p, qv in cs if t in a and abs(a[t] - qv) > 1e-6 * max(qv, 1.0)
            )
        mem = {(r[0], r[1], r[2]) for r in pu.membership(sub, classes, dates)}
        added, removed = mem - frozen, frozen - mem
        impact[name] = {"daily_quote_volumes_actually_replaced_by_a_different_value": changed[name],
                        "decisions_frozen": len(frozen), "added": len(added), "removed": len(removed),
                        "share_changed": (len(added) + len(removed)) / len(frozen),
                        "max_count_change_by_date": max(
                            abs(sum(1 for x in mem if x[:2] == (d, t)) - sum(1 for x in frozen if x[:2] == (d, t)))
                            for d in dates for t in ("1M", "5M"))}  # fmt: skip
    rep = {
        "months_compared": len(res),
        "months_inconsistent": len(inconsistent),
        "class_counts": dict(cls_count),
        "class_sum_equals_total": sum(cls_count.values()) == len(inconsistent),
        "by_month": dict(sorted(per_month.items())),
        "by_year": {y: [per_year[y], tot_year[y]] for y in sorted(tot_year)},
        "top_symbols": per_sym.most_common(10),
        "symbols_with_any": len(per_sym),
        "day_totals": {"days_with_24_hourly_candles": full_days, "days_with_hourly_gaps": gap_days},
        "full_day_relative_difference": {
            "n": len(sig),
            "median": statistics.median(sig) if sig else None,
            "p05": q(sig, 0.05),
            "p95": q(sig, 0.95),
            "min": min(sig) if sig else None,
            "max": max(sig) if sig else None,
            "share_hourly_greater": sum(1 for x in sig if x > 0) / len(sig) if sig else None,
        },  # fmt: skip
        "eligibility_impact": impact,
    }
    Path(sys.argv[2]).write_text(json.dumps(rep, indent=1, sort_keys=True))
    print(
        json.dumps(
            {
                k: rep[k]
                for k in (
                    "months_inconsistent",
                    "class_counts",
                    "class_sum_equals_total",
                    "day_totals",
                    "full_day_relative_difference",
                    "eligibility_impact",
                )
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
