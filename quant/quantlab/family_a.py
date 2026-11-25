"""
Family A: trend-filtered, volatility-scaled crypto basket versus cash (long-only spot, no leverage).

Specification: ``protocol/protocol_v5_family_a.json`` (parameters fixed a priori from convention or a
risk budget, never tuned on market data). Implemented on the Stage 0 engine so costs, equity, the
circuit breaker and causality checks are the ones already validated.

Decision rule (once per UTC day, at the 00:00 candle, using COMPLETED days only):
    score_i  = share of the trend filters satisfied: close > SMA(w) of daily closes, w in (50, 100, 200);
               a filter without enough history counts as NOT satisfied (fail closed)
    sigma_i  = annualised standard deviation of the last 30 daily log returns (NaN -> weight 0)
    target_i = (1/N) * score_i * min(1, sigma_target / sigma_i) * risk_multiplier
Variants (descriptive trials): A1 = trend + volatility scaling, A0 = trend only, V0 = volatility
scaling only (score fixed at 1). Rebalance an asset only when its weight moves by more than ``band``
(or the target is zero), by buying more or selling a fraction at the next open. Halted breaker:
no orders from the strategy (the engine cancels pending buys and liquidates).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quantlab.costs import BASE
from quantlab.execution import (
    ExecConfig,
    History,
    Order,
    PortfolioView,
    PriceData,
    Result,
    Strategy,
    run,
)


@dataclass(frozen=True)
class FamilyAConfig:
    trend_windows: tuple[int, ...] = (50, 100, 200)
    vol_window: int = 30
    sigma_target: float = 0.40
    band: float = 0.05
    periods_per_year: int = 365
    trend: bool = True  # False -> V0
    vol_scale: bool = True  # False -> A0


VARIANTS = {
    "A1": FamilyAConfig(),
    "A0": FamilyAConfig(vol_scale=False),
    "V0": FamilyAConfig(trend=False),
}


def exec_config(**over) -> ExecConfig:
    """Evaluation execution assumptions: breaker ON, flatten on halt, liquidity cap, base costs."""
    base = {
        "costs": BASE, "wallet": 1000.0, "min_notional": 5.0, "breaker": True,
        "halt_action": "flatten", "dd_reduce": 0.15, "dd_halt": 0.20, "max_participation": 0.10,
    }  # fmt: skip
    return ExecConfig(**{**base, **over})


def daily_closes(times: pd.DatetimeIndex, closes: np.ndarray) -> pd.Series:
    """Last available close of every UTC day present in the data (NaN hours are ignored)."""
    s = pd.Series(closes, index=times).dropna()
    return s.resample("1D").last().dropna()


def score_and_vol(daily: pd.Series, cfg: FamilyAConfig) -> tuple[float, float]:
    """(trend score in [0, 1], annualised volatility or NaN) from completed daily closes."""
    if cfg.trend:
        hits = 0
        for w in cfg.trend_windows:
            if len(daily) >= w and daily.iloc[-1] > daily.iloc[-w:].mean():
                hits += 1
        score = hits / len(cfg.trend_windows)
    else:
        score = 1.0
    if len(daily) > cfg.vol_window:
        rets = np.log(daily.iloc[-(cfg.vol_window + 1) :]).diff().dropna()
        sigma = float(rets.std(ddof=1) * np.sqrt(cfg.periods_per_year))
    else:
        sigma = float("nan")
    return score, sigma


def target_weight(score: float, sigma: float, n_assets: int, cfg: FamilyAConfig) -> float:
    """Unscaled by the breaker. Zero if volatility is unknown (fail closed) or score is zero."""
    if not np.isfinite(sigma) or sigma <= 0 or score <= 0:
        return 0.0
    scale = min(1.0, cfg.sigma_target / sigma) if cfg.vol_scale else 1.0
    return score * scale / n_assets


class FamilyAStrategy(Strategy):
    def __init__(self, cfg: FamilyAConfig = FamilyAConfig(), n_assets: int | None = None):
        self.cfg, self.n_assets = cfg, n_assets

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        if t != t.floor("1D") or view.halted or view.equity <= 0:
            return []
        n = self.n_assets or len(hist.pairs)
        lookback = (max(self.cfg.trend_windows) + self.cfg.vol_window + 5) * 24
        times = hist.times[-lookback:]
        orders: list[Order] = []
        for pair in hist.pairs:
            daily = daily_closes(times, hist.closes(pair, lookback))
            score, sigma = score_and_vol(daily, self.cfg)
            target = target_weight(score, sigma, n, self.cfg) * view.risk_multiplier
            qty_val = view.positions.get(pair, (0.0, 0.0))[1]
            current = qty_val / view.equity
            if target == 0.0 and current > 0:
                orders.append(Order(pair, "sell", fraction=1.0, reason="trend_exit"))
            elif target - current > self.cfg.band:
                orders.append(
                    Order(
                        pair,
                        "buy",
                        notional=(target - current) * view.equity,
                        add=True,
                        reason="rebalance_up",
                    )
                )
            elif current - target > self.cfg.band and current > 0:
                orders.append(
                    Order(
                        pair, "sell", fraction=(current - target) / current, reason="rebalance_down"
                    )
                )
        return orders


def episodes(trades: pd.DataFrame) -> pd.DataFrame:
    """One row per position episode (entry to flat). T1 counts these, not partial rebalances."""
    if trades.empty:
        return trades
    g = trades.groupby(["pair", "open_date"], sort=True)
    return g.agg(close_date=("close_date", "max"), profit_abs=("profit_abs", "sum"),
                 cost=("open_value", "sum"), fills=("profit_abs", "size")).reset_index()  # fmt: skip


def run_family_a(
    candles: dict[str, pd.DataFrame],
    start: str,
    end_exclusive: str,
    variant: str = "A1",
    cfg_exec: ExecConfig | None = None,
) -> Result:
    """Run a variant from ``start`` (candles before it are history/warm-up only)."""
    first = min(pd.to_datetime(df["date"], utc=True).min() for df in candles.values())
    index = pd.date_range(
        first.floor("1D"), pd.Timestamp(end_exclusive, tz="UTC"), freq="1h", inclusive="left"
    )
    data = PriceData(candles, index)
    i0 = int(index.searchsorted(pd.Timestamp(start, tz="UTC")))
    i1 = len(index)
    return run(
        FamilyAStrategy(VARIANTS[variant], len(candles)),
        data,
        cfg_exec or exec_config(),
        start=i0,
        end=i1,
    )
