"""M4 data acquisition (one-off, not part of the registered evaluation): fetch the pinned 1h monthly klines for the symbols of
the registered daily panel (months 2021-01 .. 2025-06 only; ``pit_fetch`` refuses holdout months), in parallel threads under ONE
shared global rate limit, resumable (cached, hash-checked files are skipped).

    python docs/phase4c/m4_scripts/fetch_1h_parallel.py STORE_DIR [rate]"""

import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

QUANT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(QUANT))

from quantlab import l2_portfolio as l2  # noqa: E402
from quantlab import l2_run  # noqa: E402
from quantlab import pit_fetch as pf  # noqa: E402
from quantlab import pit_loader as pl  # noqa: E402


def main(store_dir: str, rate: float = 25.0) -> int:
    spec = json.loads(l2.PREREG.read_text(encoding="utf-8"))
    l2_run.guard(spec)
    ds = pl.PitDataset.open(l2_run.DATASET, store_dir)
    symbols = sorted(
        p.name for p in (Path(store_dir) / "1d").iterdir() if p.is_dir()
    )  # the symbols of the daily panel
    months = [f"{y}-{mo:02d}" for y in range(2021, 2026) for mo in range(1, 13)]
    months = [x for x in months if x <= "2025-06"]
    jobs = [(s, mo) for s in symbols for mo in months if mo in ds.listing.get(s, [])]
    client = pf.Client(
        pf.HttpTransport(), pf.RateLimiter(rate), log_path=Path(store_dir) / "request_log_1h.tsv"
    )
    store = pf.Store(store_dir)
    bad = []

    def one(job):
        try:
            return pf.fetch_file(client, store, job[0], "1h", job[1]).status
        except Exception as e:  # recorded, never swallowed silently
            bad.append((job, repr(e)))
            return "error"

    with ThreadPoolExecutor(16) as ex:
        statuses = list(ex.map(one, jobs))
    print(
        json.dumps(
            {
                "jobs": len(jobs),
                "symbols": len(symbols),
                "statuses": dict(Counter(statuses)),
                "errors": bad[:5],
                "peak_requests_per_second": client.limiter.peak_per_second(),
            }
        )
    )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 25.0))
