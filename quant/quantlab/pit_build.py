"""S4 point-in-time dataset builder CLI.

    python -m quantlab.pit_build discover RAW        # USDT symbols and their dev-window 1d months
    python -m quantlab.pit_build fetch RAW           # 1d then 1h files: guarded, rate-limited, resumable
    python -m quantlab.pit_build build RAW OUT       # quality scan, epochs, membership, manifest
    python -m quantlab.pit_build validate RAW OUT    # causality / perturbation evidence on the real data

Development window only (months < 2025-07). Data (c) Binance, CC BY-NC-SA 4.0 (attribution
"Binance Vision"); non-commercial research use only. No returns or strategy are computed here.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from quantlab.pit_fetch import (
    KLINES,
    Client,
    FetchError,
    HttpTransport,
    RateLimiter,
    Store,
    fetch_file,
    list_symbol_months,
)


DEFAULT_RATE = 30.0
THREADS = 48


def make_client(rate: float, log_path: Path | None = None) -> Client:
    return Client(HttpTransport(), RateLimiter(rate), log_path=log_path)


def discover(raw: Path, client: Client) -> dict[str, list[str]]:
    d = raw / "listing"
    d.mkdir(parents=True, exist_ok=True)
    root = d / "_symbols.json"
    if root.exists():
        symbols = json.loads(root.read_text(encoding="utf-8"))
    else:
        dirs = client.list_dirs(KLINES)
        symbols = sorted(x[len(KLINES) :].rstrip("/") for x in dirs)
        symbols = [s for s in symbols if s.endswith("USDT")]
        root.write_text(json.dumps(symbols), encoding="utf-8")

    def one(sym: str) -> tuple[str, list[str]]:
        f = d / f"{sym}.json"
        if f.exists():
            return sym, json.loads(f.read_text(encoding="utf-8"))
        months = list_symbol_months(client, sym, "1d")
        f.write_text(json.dumps(months), encoding="utf-8")
        return sym, months

    with ThreadPoolExecutor(THREADS) as ex:
        out = dict(ex.map(one, symbols))
    return {s: m for s, m in out.items() if m}  # symbols without any dev-window file never enter


def fetch_all(raw: Path, client: Client, listing: dict[str, list[str]]) -> dict:
    store = Store(raw / "files")
    jobs = [(s, itv, m) for itv in ("1d", "1h") for s in sorted(listing) for m in listing[s]]
    failures: list[str] = []

    def one(j: tuple[str, str, str]) -> None:
        try:
            fetch_file(client, store, *j)
        except FetchError as e:
            failures.append(f"{j}: {e}")

    with ThreadPoolExecutor(THREADS) as ex:
        list(ex.map(one, jobs))
    return {
        "jobs": len(jobs),
        "failures": sorted(failures),
        "requests": len(client.requests),
        "configured_rate": client.limiter.rate,
        "peak_requests_per_second": client.limiter.peak_per_second(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["discover", "fetch", "build", "validate"])
    ap.add_argument("raw", type=Path)
    ap.add_argument("out", type=Path, nargs="?")
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE)
    a = ap.parse_args(argv)
    a.raw.mkdir(parents=True, exist_ok=True)
    client = make_client(a.rate, a.raw / "requests_append.log")
    if a.cmd in ("discover", "fetch"):
        listing = discover(a.raw, client)
        (a.raw / "listing.json").write_text(json.dumps(listing, sort_keys=True), encoding="utf-8")
        print(f"{len(listing)} symbols with dev-window files", flush=True)
        if a.cmd == "fetch":
            rep = fetch_all(a.raw, client, listing)
            rep["requests_log_sample"] = client.requests[:3]
            (a.raw / "fetch_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
            print(json.dumps({k: v for k, v in rep.items() if k != "failures"}), flush=True)
            return 1 if rep["failures"] else 0
        return 0
    from quantlab import pit_run  # build / validate (second module, imported lazily)

    return pit_run.main(a.cmd, a.raw, a.out)


if __name__ == "__main__":
    sys.exit(main())
