"""
Explicit trading-cost model: exchange fee and slippage are separate, applied exactly once.

* ``fee`` is the exchange taker fee per side. It is the ONLY cost Freqtrade applies
  (``--fee``); the trades Freqtrade returns carry it in ``fee_open`` / ``fee_close``.
* ``slippage`` is the adverse price move per side that a market order suffers versus the
  candle price Freqtrade assumes. It is applied afterwards, in :func:`apply_costs`, to the
  fill rates. ``stop_extra`` is additional slippage on stop-loss exits (stops execute as market
  orders in fast markets).

Double-counting guard: :func:`apply_costs` refuses trades whose recorded fee differs from the
scenario fee, so a config with a lumped fee (fee + slippage in ``--fee``) cannot be combined
with this slippage layer by accident.

Assumption (not measured): slippage is independent of order size because orders are tiny
relative to BTC/ETH/SOL/... 1h volume; it is NOT fed back into Freqtrade's position sizing
(second-order effect, documented in the protocol).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


STOP_REASONS = frozenset({"stop_loss", "trailing_stop_loss", "stoploss_on_exchange"})
REQUIRED = ["pair", "amount", "open_rate", "close_rate", "fee_open", "fee_close", "exit_reason"]


@dataclass(frozen=True)
class CostScenario:
    name: str
    fee: float
    slippage: float
    stop_extra: float

    @property
    def per_side(self) -> float:
        """Total cost per side for a normal (non-stop) fill."""
        return self.fee + self.slippage

    @property
    def per_side_stop(self) -> float:
        return self.fee + self.slippage + self.stop_extra


BASE = CostScenario("base", fee=0.001, slippage=0.0005, stop_extra=0.0005)
STRESS = CostScenario("stress", fee=0.002, slippage=0.001, stop_extra=0.001)
SCENARIOS = {s.name: s for s in (BASE, STRESS)}


def apply_costs(trades: pd.DataFrame, scenario: CostScenario) -> pd.DataFrame:
    """Return trades with slippage applied and profit recomputed from rates (never trusted)."""
    missing = [c for c in REQUIRED if c not in trades.columns]
    if missing:
        raise ValueError(f"trades lack columns {missing}")
    for col in ("fee_open", "fee_close"):
        if not np.allclose(trades[col].to_numpy(dtype=float), scenario.fee, rtol=0, atol=1e-12):
            raise ValueError(
                f"{col} in trades != scenario fee {scenario.fee}: refusing to add slippage on top "
                "of a different fee (double-counting guard)"
            )
    out = trades.copy()
    is_stop = out["exit_reason"].isin(STOP_REASONS).to_numpy()
    s_open = scenario.slippage
    s_close = scenario.slippage + np.where(is_stop, scenario.stop_extra, 0.0)
    out["open_rate_eff"] = out["open_rate"] * (1 + s_open)
    out["close_rate_eff"] = out["close_rate"] * (1 - s_close)
    out["open_value"] = out["amount"] * out["open_rate_eff"] * (1 + out["fee_open"])
    close_value = out["amount"] * out["close_rate_eff"] * (1 - out["fee_close"])
    out["profit_abs"] = close_value - out["open_value"]
    out["profit_ratio"] = close_value / out["open_value"] - 1
    return out
