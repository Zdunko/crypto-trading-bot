"""S3 audit fetcher (scratch only, NOT a dataset builder).

Downloads dev-period (< 2025-07) monthly klines + .CHECKSUM for the S1 symbol list into a scratch
directory and writes a pin manifest. It refuses any month >= 2025-07 (holdout) by construction.

    python fetch.py <raw_dir> 1d all
    python fetch.py <raw_dir> 1h sample <sample.json>
Data (c) Binance, CC BY-NC-SA 4.0 (attribution: Binance Vision). Raw files are never committed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/spot/monthly/klines"
DEV_END = "2025-07"  # exclusive, YYYY-MM
S1_CSV = Path(__file__).resolve().parents[1] / "s1_binance_usdt_coverage.csv"


def months(a: str, b: str) -> list[str]:
    y, m = map(int, a.split("-"))
    y2, m2 = map(int, b.split("-"))
    out = []
    while (y, m) <= (y2, m2):
        out.append(f"{y}-{m:02d}")
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def guard(ym: str) -> None:
    if ym >= DEV_END:
        raise SystemExit(f"HOLDOUT GUARD: refusing to request month {ym} (>= {DEV_END})")


def universe() -> dict[str, list[str]]:
    out = {}
    for r in csv.DictReader(S1_CSV.open(encoding="utf-8", newline="")):
        b = min(r["last_month"], "2025-06")
        if r["first_month"] <= b:
            out[r["symbol"]] = months(r["first_month"], b)
    return out


def curl(url: str) -> tuple[int, bytes]:
    for k in range(4):
        p = subprocess.run(
            ["curl", "-s", "-m", "60", "-w", "\n%{http_code}", url], capture_output=True
        )
        body, _, code = p.stdout.rpartition(b"\n")
        if p.returncode == 0 and code in (b"200", b"404"):
            return int(code), body
        time.sleep(1 + k)
    return 0, b""


def one(job: tuple[str, str, str], raw: Path) -> dict:
    sym, itv, ym = job
    guard(ym)
    d = raw / itv
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{sym}-{itv}-{ym}.zip"
    meta = d / f"{sym}-{itv}-{ym}.json"
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    url = f"{BASE}/{sym}/{itv}/{sym}-{itv}-{ym}.zip"
    c, z = curl(url)
    rec = {"symbol": sym, "interval": itv, "month": ym, "http": c}
    if c == 200:
        cc, ck = curl(url + ".CHECKSUM")
        got = hashlib.sha256(z).hexdigest()
        want = ck.decode(errors="replace").split()[0] if cc == 200 and ck.strip() else None
        f.write_bytes(z)
        rec.update(sha256=got, published_sha256=want, size=len(z), checksum_ok=(got == want))
    meta.write_text(json.dumps(rec, sort_keys=True))
    return rec


def main() -> int:
    raw, itv, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    uni = universe()
    if mode == "all":
        jobs = [(s, itv, m) for s, ms in uni.items() for m in ms]
    else:
        jobs = [tuple(j) for j in json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))]
    t = time.time()
    with ThreadPoolExecutor(32) as ex:
        res = list(ex.map(lambda j: one(j, raw), jobs))
    res.sort(key=lambda r: (r["symbol"], r["month"]))
    ok = sum(1 for r in res if r["http"] == 200)
    print(f"{len(jobs)} jobs, {ok} present, {len(jobs) - ok} absent, {time.time() - t:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
