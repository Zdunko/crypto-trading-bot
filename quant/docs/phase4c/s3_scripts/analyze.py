"""S3 audit analysis: deterministic, reads the scratch raw dir written by fetch.py, uses only
quantlab.data_audit. No returns, no strategy. Output: JSON of aggregates + gz pin manifest.

    python analyze.py <raw_dir> <out_json> <pin_manifest.tsv.gz> [fetch_seconds_1d]
    python analyze.py sample <raw_dir> <sample_out.json>      # select the hourly sample (seeded)
Data (c) Binance, CC BY-NC-SA 4.0 (attribution: Binance Vision).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import random
import re
import statistics
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))  # quant/
from quantlab import data_audit as da  # noqa: E402

CRIT = json.loads((HERE.parent / "s3_criteria.json").read_text())
S1_CSV = HERE.parent / "s1_binance_usdt_coverage.csv"
STABLE = {
    "USDC",
    "TUSD",
    "BUSD",
    "PAX",
    "USDP",
    "FDUSD",
    "DAI",
    "USDS",
    "AEUR",
    "EUR",
    "GBP",
    "TRY",
    "UST",
    "USTC",
    "SUSD",
    "USDSB",
    "VAI",  # codespell:ignore vai (stablecoin ticker)
    "EURI",
    "USD1",
    "XUSD",
    "BFUSD",
    "RLUSD",
    "PAXG",
}
LEV = re.compile(r"(UP|DOWN|BULL|BEAR)$")
DAY = da.MS["1d"]


def is_asset(sym: str) -> bool:
    b = sym[:-4]
    return b not in STABLE and not (LEV.search(b) and len(b) > 4)


def read_rows(zpath: Path) -> list[list[str]]:
    zf = zipfile.ZipFile(zpath)
    txt = zf.read(zf.namelist()[0]).decode()
    return [ln.split(",") for ln in txt.splitlines() if ln and not ln[0].isalpha()]


def metas(raw: Path, itv: str) -> list[dict]:
    out = [json.loads(p.read_text()) for p in sorted((raw / itv).glob("*.json"))]
    out.sort(key=lambda r: (r["symbol"], r["month"]))
    return out


def month_start_ms(ym: str) -> int:
    return da.month_bounds_ms(ym)[0]


def shift(ym: str, k: int) -> str:
    y, m = map(int, ym.split("-"))
    t = y * 12 + m - 1 + k
    return f"{t // 12}-{t % 12 + 1:02d}"


def month_range(a: str, b: str) -> list[str]:
    out, x = [], a
    while x <= b:
        out.append(x)
        x = shift(x, 1)
    return out


def select_sample(raw: Path, out: Path) -> None:
    rnd = random.Random(CRIT["sampling"]["seed"])
    per_year: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for r in metas(raw, "1d"):
        if r["http"] == 200 and is_asset(r["symbol"]):
            per_year[r["month"][:4]].append((r["symbol"], "1h", r["month"]))
    years = sorted(per_year)
    k = CRIT["sampling"]["hourly_sample_size"] // len(years)
    pick = []
    for y in years:
        pool = sorted(per_year[y])
        pick += rnd.sample(pool, min(k, len(pool)))
    out.write_text(json.dumps(sorted(pick), indent=0))
    print(f"sample {len(pick)} over {len(years)} years")


def analyze(raw: Path, fetch_seconds: float | None) -> tuple[dict, list[str]]:
    m1d = metas(raw, "1d")
    s1 = {r["symbol"]: r for r in csv.DictReader(S1_CSV.open())}
    present = defaultdict(list)
    reports, daily = {}, defaultdict(dict)
    quarantine, defect_counts = [], defaultdict(int)
    for r in m1d:
        if r["http"] != 200:
            continue
        sym, ym = r["symbol"], r["month"]
        present[sym].append(ym)
        rows = read_rows(raw / "1d" / f"{sym}-1d-{ym}.zip")
        rep = da.check_candles(rows, "1d", ym)
        reports[(sym, ym)] = rep
        for k, n in rep.findings.items():
            defect_counts[k] += 1
        if rep.quarantined:
            quarantine.append([sym, ym, rep.fatal])
            continue
        for x in rows:
            daily[sym][da.to_ms(int(x[0]))] = (float(x[4]), float(x[7]))
    n_files = len(reports)
    n_chk = sum(1 for r in m1d if r["http"] == 200 and r.get("checksum_ok"))
    # --- identity flags
    flags = {s: da.identity_flags(present[s], daily[s]) for s in present}
    flagged = sorted(s for s, f in flags.items() if f["flagged"])
    # --- PIT eligibility at month starts
    starts = month_range("2021-01", "2025-06")
    assets = sorted(s for s in present if is_asset(s))
    excl = set(flagged)
    elig = {}
    for t in starts:
        ms = month_start_ms(t)
        for thr_name, thr in (("1M", 1e6), ("5M", 5e6)):
            elig[(t, thr_name)] = [s for s in assets if da.pit_eligible(daily[s], ms, thr)]
    cnt = {t: {n: len(elig[(t, n)]) for n in ("1M", "5M")} for t in starts}
    cnt_x = {t: len([s for s in elig[(t, "1M")] if s not in excl]) for t in starts}
    cnt5_x = {t: len([s for s in elig[(t, "5M")] if s not in excl]) for t in starts}
    # --- survivorship
    dead = {s for s in present if s1.get(s, {}).get("last_month", "9") < "2026-10"}
    checked = {s for s in dead if present[s]}
    s2 = {}
    for t in ("2021-01", "2022-01", "2023-01", "2024-01", "2025-01"):
        e = elig[(t, "1M")]
        s2[t] = {"eligible": len(e), "delisted_by_2026_10": len([s for s in e if s in dead])}
    # --- regimes from BTC closes strictly before month start
    btc = daily["BTCUSDT"]
    reg_months = defaultdict(int)
    reg_by_month = {}
    for t in starts:
        ms = month_start_ms(t)
        cl = [btc[ms - d * DAY][0] for d in range(180, 0, -1) if (ms - d * DAY) in btc]
        lab = da.regime_label(cl) if len(cl) >= 150 else "unknown"
        reg_by_month[t] = lab
        if cnt_x[t] >= 30:
            reg_months[lab] += 1
    regimes = {k: reg_months.get(k, 0) for k in ("bull", "bear", "sideways")}
    # --- resources (1h): symbol-months to download for all 1M-eligible assets (union by month)
    hr = metas(raw, "1h") if (raw / "1h").exists() else []
    hr_ok = [r for r in hr if r["http"] == 200]
    mean_1h = statistics.mean(r["size"] for r in hr_ok) if hr_ok else float("nan")
    sm = sum(cnt_x[t] for t in starts)  # symbol-months across month starts (post-exclusion)
    gb = sm * mean_1h / 1e9
    reqs = 2 * sm
    rate = (2 * n_files / fetch_seconds) if fetch_seconds else float("nan")
    hours = reqs / rate / 3600 if fetch_seconds else float("nan")
    # --- hourly sample
    hq = []
    hfind = defaultdict(int)
    for r in hr_ok:
        rep = da.check_candles(
            read_rows(raw / "1h" / f"{r['symbol']}-1h-{r['month']}.zip"), "1h", r["month"]
        )
        for k in rep.findings:
            hfind[k] += 1
        if rep.quarantined:
            hq.append([r["symbol"], r["month"], rep.fatal])
    hn = len(hr_ok)
    h_chk = sum(1 for r in hr_ok if r.get("checksum_ok"))
    out = {
        "files_1d_present": n_files,
        "files_1d_absent_requested": len([r for r in m1d if r["http"] != 200]),
        "symbols_with_dev_data": len(present),
        "checksum_ok_1d": n_chk,
        "checksum_ok_1h": h_chk,
        "defect_file_counts_1d": dict(sorted(defect_counts.items())),
        "quarantined_1d": quarantine,
        "hourly_sample": {
            "n": hn,
            "defect_file_counts": dict(sorted(hfind.items())),
            "quarantined": hq,
            "mean_zip_bytes": mean_1h,
        },
        "identity_flagged": {
            s: {
                "coverage_breaks": flags[s]["coverage_breaks"],
                "price_jumps": [[t, round(r, 6)] for t, r in flags[s]["price_jumps"]],
            }
            for s in flagged
        },
        "identity_flagged_count": len(flagged),
        "eligible_counts_by_month_start": cnt,
        "eligible_counts_1M_after_exclusions": cnt_x,
        "eligible_counts_5M_after_exclusions": cnt5_x,
        "survivorship_cohorts_1M": s2,
        "dead_symbols_with_dev_data": len(checked),
        "dead_symbols": len(dead),
        "regime_by_month_start": reg_by_month,
        "regime_months_ge30_after_exclusions": regimes,
        "resource_estimate": {
            "symbol_months_1h": sm,
            "storage_gb": gb,
            "requests": reqs,
            "measured_request_rate_per_s": rate,
            "download_hours": hours,
        },
        "lev_regex_excluded_bases_with_dev_data": sorted(
            s[:-4] for s in present if not is_asset(s) and s[:-4] not in STABLE
        ),
    }
    m = {
        "L1_permitted": True,
        "L2_note": "paper/live trading with derived signals not permitted or not covered (Vision Dataset Terms 4.1-4.4)",
        "checksum_share": (n_chk + h_chk) / (n_files + hn) if (n_files + hn) else 0.0,
        "daily_quarantine_share": len(quarantine) / n_files,
        "hourly_wilson_upper": da.wilson_upper(len(hq), hn),
        "u1_min_eligible_1M": min(cnt[t]["1M"] for t in starts),
        "u2_share_ge30_5M": sum(1 for t in starts if cnt[t]["5M"] >= 30) / len(starts),
        "u3_min_eligible_1M_after_exclusions": min(cnt_x.values()),
        "s1_dead_retained_share": len(checked) / len(dead & set(present))
        if dead & set(present)
        else 1.0,
        "s2_dead_share_by_cohort": {
            t: v["delisted_by_2026_10"] / v["eligible"] if v["eligible"] else None
            for t, v in s2.items()
        },
        "r1_months_by_regime": regimes,
        "p1_identical": None,
        "c1_storage_gb": gb,
        "c1_download_hours": hours,
        "t1": {
            "years_with_ge30_1M_all_month_starts": sorted(
                {t[:4] for t in starts if cnt_x[t] >= 30}
            ),
            "regime_run_lengths": _runs(reg_by_month),
        },
        "exclusions_required": bool(flagged)
        or bool(quarantine)
        or any(cnt[t]["1M"] != cnt_x[t] for t in starts),
    }
    out["measurements"] = m
    pins = [
        f"{r['interval']}\t{r['symbol']}\t{r['month']}\t{r['http']}\t{r.get('sha256', '')}\t{r.get('size', '')}"
        for r in m1d + hr
    ]
    return out, pins


def _runs(lab: dict[str, str]) -> list[list]:
    out: list[list] = []
    for t in sorted(lab):
        if out and out[-1][0] == lab[t]:
            out[-1][1] += 1
        else:
            out.append([lab[t], 1])
    return out


def main() -> int:
    if sys.argv[1] == "sample":
        select_sample(Path(sys.argv[2]), Path(sys.argv[3]))
        return 0
    raw, outp, pinp = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    secs = float(sys.argv[4]) if len(sys.argv) > 4 else None
    res, pins = analyze(raw, secs)
    # P1: identical-output check is computed by comparing two independent runs of this script (see report)
    res["measurements"]["p1_identical"] = json.loads(sys.argv[5]) if len(sys.argv) > 5 else None
    gates = (
        da.evaluate_gates(CRIT, res["measurements"])
        if res["measurements"]["p1_identical"] is not None
        else None
    )
    res["gates"] = gates
    outp.write_text(json.dumps(res, indent=1, sort_keys=True, default=str))
    with gzip.GzipFile(filename="", fileobj=pinp.open("wb"), mode="wb", mtime=0) as g:
        g.write(("\n".join(pins) + "\n").encode())
    h = hashlib.sha256(
        json.dumps(
            {k: v for k, v in res.items() if k not in ("gates",)}, sort_keys=True, default=str
        ).encode()
    ).hexdigest()
    print("analysis_hash", h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
