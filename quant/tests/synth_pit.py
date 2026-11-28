"""Synthetic S4-style dataset builder for the loader / guard tests (fake archive, no network)."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

from fake_s3 import FakeS3

from quantlab import data_audit as da
from quantlab import pit_fetch as pf
from quantlab import pit_run
from quantlab.pit_loader import _norm_sha


DAY, HOUR = 86_400_000, 3_600_000


def csv_zip(rows) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", "\n".join(",".join(str(c) for c in r) for r in rows) + "\n")
    return b.getvalue()


def row(ts, close=1.0, vol=1.0):
    return [ts, close, close * 1.1, close * 0.9, close, vol, ts + 1, vol * close, 5, 0, 0, 0]


def month_rows(ym, step, n=None, vol=1.0):
    lo, hi = da.month_bounds_ms(ym)
    n = (hi - lo) // step if n is None else n
    return [row(lo + i * step, 1.0, vol) for i in range(n)]


def archive(variant: str = "base"):
    """AAA live all period; BBB ends 2020-12-20; ADAUP leveraged; variants add defects/gaps."""
    spec = {
        "AAAUSDT": (["2020-10", "2020-11", "2020-12", "2021-01"], None, 5e6),
        "BBBUSDT": (["2020-10", "2020-11", "2020-12"], 20, 2e6),  # 20 days in the last month
        "ADAUPUSDT": (["2020-10", "2020-11", "2020-12", "2021-01"], None, 9e6),
    }
    if variant == "gap":  # AAA misses 2020-11 entirely (a hole inside its history)
        spec["AAAUSDT"] = (["2020-10", "2020-12", "2021-01"], None, 5e6)
    objs, listing = {}, {}
    for sym, (months, last_days, level) in spec.items():
        listing[sym] = months
        for m in months:
            for itv, step in (("1d", DAY), ("1h", HOUR)):
                n = None
                if last_days is not None and m == months[-1]:
                    n = last_days * (24 if itv == "1h" else 1)
                rows = month_rows(m, step, n, vol=level / (24 if itv == "1h" else 1))
                if variant == "quarantine" and sym == "AAAUSDT" and m == "2020-11" and itv == "1d":
                    rows[3][5] = -5.0  # negative volume -> quarantined
                objs[f"{pf.KLINES}{sym}/{itv}/{sym}-{itv}-{m}.zip"] = csv_zip(rows)
    return objs, listing


def build(tmp: Path, variant: str = "base"):
    objs, listing = archive(variant)
    raw = tmp / f"raw_{variant}"
    raw.mkdir(parents=True)
    (raw / "listing.json").write_text(json.dumps(listing), encoding="utf-8")
    cls = {
        "symbols": {
            "AAAUSDT": {"class": "asset"},
            "BBBUSDT": {"class": "asset"},
            "ADAUPUSDT": {"class": "leveraged_token"},
        }
    }
    cpath = tmp / f"classes_{variant}.json"
    cpath.write_text(json.dumps(cls), encoding="utf-8")
    client = pf.Client(FakeS3(objs), pf.RateLimiter(1e6), retries=1, backoff=0)
    store = pf.Store(raw / "files")
    for itv in ("1d", "1h"):
        for s in listing:
            for m in listing[s]:
                pf.fetch_file(client, store, s, itv, m)
    out = tmp / f"dataset_{variant}"
    man = pit_run.build(raw, out, classification=cpath)
    shutil.copy(raw / "listing.json", out / "dev_window_listing.json")
    shutil.copy(cpath, out / "asset_classification.json")
    freeze = {
        "dataset_hash": man["dataset_hash"],
        "files": {p.name: _norm_sha(p.read_bytes()) for p in sorted(out.iterdir()) if p.is_file()},
    }
    return out, raw / "files", freeze
