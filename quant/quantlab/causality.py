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


__all__ = ["EngineState", "mutate_future", "mutation_mismatches", "restart_mismatches"]
