"""
Trade-level causality checks for stateful strategies (replaces lookahead-analysis for them).

``freqtrade lookahead-analysis`` re-runs a truncated window with a FRESH state; for a strategy whose
decisions legitimately depend on state (equity, cooldowns, breaker peak) that differs without any
leakage. Two checks decide instead, both exact and both run on the Stage 0 engine:

* **mutation** - replace every candle at/after ``k`` by random values: every order the strategy
  emitted up to and including candle ``k`` and every trade closed before ``k`` must be identical
  (decisions at ``k`` may use candles ``< k`` only).
* **restart** - stop a run at ``k``, restart from the saved :class:`EngineState`: orders and equity
  after ``k`` must equal the uninterrupted run (state is explicit and complete).

A deliberately leaky strategy must fail the mutation check (negative control in the tests).
``lookahead-analysis`` stays mandatory for the stateless signal layer of any Freqtrade strategy.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from quantlab.execution import EngineState, ExecConfig, PriceData, Result, Strategy, run


def mutate_future(
    candles: dict[str, pd.DataFrame], k: int, seed: int = 5
) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    out = {}
    for pair, df in candles.items():
        d = df.copy()
        for col in ("open", "high", "low", "close"):
            d.loc[k:, col] = d.loc[k:, col].to_numpy() * rng.uniform(0.5, 1.5, len(d) - k)
        out[pair] = d
    return out


def mutation_mismatches(
    make: Callable[[PriceData], Strategy],
    candles: dict[str, pd.DataFrame],
    index: pd.DatetimeIndex,
    cfg: ExecConfig,
    k: int,
) -> list[str]:
    """Empty list = causal at ``k``. Otherwise the kinds of difference found."""
    d1, d2 = PriceData(candles, index), PriceData(mutate_future(candles, k), index)
    a, b = run(make(d1), d1, cfg), run(make(d2), d2, cfg)
    problems = []
    if [o for o in a.orders if o["i"] <= k] != [o for o in b.orders if o["i"] <= k]:
        problems.append("orders up to k differ")
    ta = a.trades[a.trades["close_date"] < index[k]].reset_index(drop=True)
    tb = b.trades[b.trades["close_date"] < index[k]].reset_index(drop=True)
    if not ta.equals(tb):
        problems.append("trades closed before k differ")
    return problems


def restart_mismatches(
    make: Callable[[], Strategy],
    carry: Callable[[Strategy, Result], None],
    data: PriceData,
    cfg: ExecConfig,
    k: int,
) -> list[str]:
    """Restart at ``k`` from the saved state; ``carry`` copies strategy-internal memory (if any)."""
    full = run(make(), data, cfg)
    head = run(make(), data, cfg, end=k)
    strat = make()
    carry(strat, head)
    tail = run(strat, data, cfg, start=k, state=head.state)
    problems = []
    if tail.orders != [o for o in full.orders if o["i"] >= k]:
        problems.append("orders after k differ")
    if not np.allclose(tail.equity.to_numpy(), full.equity.iloc[k:].to_numpy(), rtol=0, atol=1e-9):
        problems.append("equity after k differs")
    return problems


def mutate_from_time(
    candles: dict[str, pd.DataFrame],
    t0: pd.Timestamp,
    seed: int = 5,
    prices: bool = True,
    volume: bool = True,
) -> dict[str, pd.DataFrame]:
    """Randomise prices and/or volumes of every candle at or after ``t0`` (time based, any alignment)."""
    rng = np.random.default_rng(seed)
    out = {}
    for pair, df in candles.items():
        d = df.copy()
        late = (pd.to_datetime(d["date"], utc=True) >= t0).to_numpy()
        n = int(late.sum())
        if prices:
            for col in ("open", "high", "low", "close"):
                d.loc[late, col] = d.loc[late, col].to_numpy() * rng.uniform(0.5, 1.5, n)
        if volume and "volume" in d:
            d.loc[late, "volume"] = d.loc[late, "volume"].to_numpy() * rng.uniform(0.1, 10.0, n)
        out[pair] = d
    return out


def _closed_up_to(trades: pd.DataFrame, last: pd.Timestamp) -> pd.DataFrame:
    """Fills closed up to ``last``; an empty trade list (no columns) is a valid, comparable result."""
    if trades.empty or "close_date" not in trades:
        return pd.DataFrame()
    return trades[trades["close_date"] <= last].reset_index(drop=True)


def mutation_mismatches_at(
    make: Callable[[PriceData], Strategy],
    candles: dict[str, pd.DataFrame],
    index: pd.DatetimeIndex,
    cfg: ExecConfig,
    t0: pd.Timestamp,
    start: int = 0,
    prices: bool = True,
    volume: bool = True,
) -> list[str]:
    """
    Causality at time ``t0`` (candle k): mutate prices and/or volumes from ``t0`` on. Orders emitted
    up to and including candle k, fills up to and including candle k and equity through candle k - 1
    must be identical (candle k's own prices may legitimately differ, its volume must not matter).
    With ``prices=False`` equity through candle k must match as well.
    """
    k = int(index.searchsorted(t0))
    d1 = PriceData(candles, index)
    d2 = PriceData(mutate_from_time(candles, t0, prices=prices, volume=volume), index)
    a, b = run(make(d1), d1, cfg, start=start), run(make(d2), d2, cfg, start=start)
    problems = []
    if [o for o in a.orders if o["i"] <= k] != [o for o in b.orders if o["i"] <= k]:
        problems.append("orders up to candle k differ")
    last = (
        t0 if not prices else t0 - pd.Timedelta(1, "ns")
    )  # price mutation changes candle k itself
    ta, tb = _closed_up_to(a.trades, last), _closed_up_to(b.trades, last)
    if not ta.equals(tb):
        problems.append("fills up to candle k differ")
    upto = a.equity.index <= (t0 if not prices else t0 - pd.Timedelta(1, "ns"))
    if not np.allclose(a.equity[upto].to_numpy(), b.equity[upto].to_numpy(), rtol=0, atol=1e-9):
        problems.append("equity before candle k differs")
    return problems


def restart_mismatches_at(
    make: Callable[[], Strategy], data: PriceData, cfg: ExecConfig, start: int, k: int
) -> list[str]:
    """Restart check for a strategy without private memory, starting the run at ``start``."""
    full = run(make(), data, cfg, start=start)
    head = run(make(), data, cfg, start=start, end=k)
    tail = run(make(), data, cfg, start=k, state=head.state)
    problems = []
    if tail.orders != [o for o in full.orders if o["i"] >= k]:
        problems.append("orders after k differ")
    if not np.allclose(
        tail.equity.to_numpy(), full.equity.loc[tail.equity.index].to_numpy(), rtol=0, atol=1e-9
    ):
        problems.append("equity after k differs")
    return problems


__all__ = [
    "EngineState",
    "mutate_from_time",
    "mutate_future",
    "mutation_mismatches",
    "mutation_mismatches_at",
    "restart_mismatches",
    "restart_mismatches_at",
]
