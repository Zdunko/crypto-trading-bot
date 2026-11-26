"""S5 infrastructure: a Strategy wrapper that restricts NEW buys to point-in-time tradable assets.

Policy (documented, tested): buys of pairs that are not members of the universe at the decision time,
or whose last completed daily candle is stale, or for which the loader raises any error, are blocked
with a logged reason (fail closed). Sells and stop updates always pass; positions already held are
never force-sold by the guard (that is the risk layer's job). Pure function of (dataset, time, orders).
"""

from __future__ import annotations

import pandas as pd

from quantlab.execution import History, Order, PortfolioView, Strategy
from quantlab.pit_loader import PitDataset, PitError, symbol_of


class UniverseGuard(Strategy):
    def __init__(
        self, inner: Strategy, dataset: PitDataset, threshold: str = "1M", max_stale_days: int = 3
    ):
        self.inner, self.ds = inner, dataset
        self.threshold, self.max_stale_days = threshold, max_stale_days
        self.blocked: list[dict] = []
        self._cache: dict[tuple[str, pd.Timestamp], tuple[bool, str]] = {}

    def _allowed(self, pair: str, t: pd.Timestamp) -> tuple[bool, str]:
        key = (
            pair,
            t.normalize(),
        )  # membership is monthly, staleness is daily: decide once per day
        if key not in self._cache:
            try:
                self._cache[key] = self.ds.tradable(
                    symbol_of(pair), t, self.threshold, self.max_stale_days
                )
            except PitError as e:
                self._cache[key] = (False, f"loader_error:{type(e).__name__}")
        return self._cache[key]

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        out: list[Order] = []
        for o in self.inner.on_candle(t, hist, view):
            if o.side != "buy":
                out.append(o)
                continue
            ok, why = self._allowed(o.pair, t)
            if ok:
                out.append(o)
            else:
                self.blocked.append({"t": str(t), "pair": o.pair, "reason": why})
        return out
