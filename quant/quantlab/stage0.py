"""
Stage 0 real-data infrastructure check (CI): no strategy, no profitability result.

Verifies on the frozen dataset (evaluation period only; the holdout is never loaded) that the new
engine (1) reproduces the legacy equal-weight benchmark, (2) is deterministic, (3) handles the real
candle gaps. Output: one JSON block between markers.

    python -m quantlab.stage0
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from quantlab.costs import BASE
from quantlab.equity import buy_and_hold
from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run
from quantlab.phase3 import emit, guard, load_candles


class BuyAtStart(Strategy):
    def __init__(self, pairs: list[str], wallet: float):
        self.pairs, self.wallet = pairs, wallet

    def on_candle(self, t, hist, view):
        if len(hist.times) == 0:
            return [Order(p, "buy", notional=self.wallet / len(self.pairs)) for p in self.pairs]
        return []


def check(proto: dict) -> dict:
    per = proto["periods"]["evaluation"]
    index = pd.date_range(per["start"], per["end_exclusive"], freq="1h", inclusive="left", tz="UTC")
    cutoff = pd.Timestamp(per["end_exclusive"], tz="UTC")
    candles = {
        p: df[pd.to_datetime(df["date"], utc=True) < cutoff]
        for p, df in load_candles(proto).items()
    }
    wallet = float(proto["initial_wallet"])
    legacy, chosen = buy_and_hold(candles, index, wallet, BASE)
    data = PriceData({p: candles[p] for p in chosen}, index)
    cfg = ExecConfig(costs=BASE, wallet=wallet, breaker=False)
    a = run(BuyAtStart(chosen, wallet), data, cfg)
    b = run(BuyAtStart(chosen, wallet), data, cfg)
    rel = np.abs(a.equity.to_numpy() - legacy.to_numpy()) / legacy.to_numpy()
    gaps = {p: int(np.isnan(data.open[:, data.col[p]]).sum()) for p in chosen}
    return {
        "period": per,
        "pairs": chosen,
        "max_rel_diff_vs_legacy_benchmark": float(rel.max()),
        "final_equity_engine": float(a.equity.iloc[-1]),
        "final_equity_legacy": float(legacy.iloc[-1]),
        "deterministic": a.hash == b.hash,
        "hash": a.hash,
        "missing_candles_per_pair": gaps,
        "rejected_orders": a.rejects,
    }


def main() -> int:
    proto = guard()
    out = check(proto)
    emit("STAGE0_JSON", json.dumps(out))
    ok = out["deterministic"] and out["max_rel_diff_vs_legacy_benchmark"] < 2e-6
    print("STAGE0", "OK" if ok else "FAILED", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
