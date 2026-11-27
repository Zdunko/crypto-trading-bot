"""M3 data acquisition (one-off, not part of the registered evaluation): fetch the pinned 1d monthly klines needed
by the registered panel, in parallel threads under ONE shared global rate limit, through the existing guarded client
(holdout months are refused by ``pit_fetch``). The panel definition is copied from ``l1_run.cmd_fetch``.

    python docs/phase4c/m3_scripts/fetch_1d_parallel.py STORE_DIR [rate]"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

QUANT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(QUANT))

from quantlab import l1_max3 as m  # noqa: E402
from quantlab import l1_run  # noqa: E402
from quantlab import pit_fetch as pf  # noqa: E402
from quantlab import pit_loader as pl  # noqa: E402


def main(store_dir: str, rate: float = 25.0) -> int:
    spec = json.loads(m.PREREG.read_text(encoding="utf-8"))
    l1_run.guard(spec)
    ds = pl.PitDataset.open(l1_run.DATASET, store_dir)
    ev, un = spec["evaluation"], spec["universe"]
    months = [f"{y}-{mo:02d}" for y in range(2020, 2026) for mo in range(1, 13)]
    months = [x for x in months if ev["panel_first_candle_open"][:7] <= x <= ev["last_candle_open"][:7]]
    symbols = {ev["regime"]["reference_symbol"]}
    for mo in months:
        if mo >= "2021-01":
            symbols |= set(ds.universe_at(pd.Timestamp(mo + "-01", tz="UTC"), un["threshold"], un["max_stale_days"]))
    jobs = [(s, mo) for s in sorted(symbols) for mo in months if mo in ds.listing.get(s, [])]
    client = pf.Client(pf.HttpTransport(), pf.RateLimiter(rate), log_path=Path(store_dir) / "request_log.tsv")
    store = pf.Store(store_dir)
    bad = []

    def one(job):
        try:
            rec = pf.fetch_file(client, store, job[0], "1d", job[1])
            return rec.status
        except Exception as e:  # recorded, never swallowed silently
            bad.append((job, repr(e)))
            return "error"

    with ThreadPoolExecutor(16) as ex:
        statuses = list(ex.map(one, jobs))
    from collections import Counter

    print(json.dumps({"jobs": len(jobs), "symbols": len(symbols), "statuses": dict(Counter(statuses)), "errors": bad[:5], "peak_requests_per_second": client.limiter.peak_per_second()}))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 25.0))
