"""Performance metrics computed from equity curves and trade lists (no Freqtrade dependency)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


DAYS_PER_YEAR = 365  # crypto trades 24/7


def with_start(equity: pd.Series, wallet: float) -> pd.Series:
    """Prepend the initial wallet one hour before the first row (drawdown/returns start there)."""
    first = equity.index[0] - pd.Timedelta("1h")
    return pd.concat([pd.Series([wallet], index=[first]), equity])


def net_return(equity: pd.Series, wallet: float) -> float:
    return float(equity.iloc[-1] / wallet - 1.0)


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough fall as a positive fraction of the peak (hourly mark-to-market)."""
    peak = equity.cummax()
    return float(((peak - equity) / peak).max())


def daily_returns(equity: pd.Series) -> pd.Series:
    daily = equity.resample("1D").last()
    return daily.pct_change().dropna()


def sharpe(daily: np.ndarray | pd.Series) -> float:
    r = np.asarray(daily, dtype=float)
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(r.mean() / sd * math.sqrt(DAYS_PER_YEAR)) if sd > 0 else float("nan")


def sortino(daily: np.ndarray | pd.Series) -> float:
    """Mean over downside deviation (target 0), annualised."""
    r = np.asarray(daily, dtype=float)
    downside = math.sqrt(float(np.mean(np.minimum(r, 0.0) ** 2))) if len(r) else 0.0
    return float(r.mean() / downside * math.sqrt(DAYS_PER_YEAR)) if downside > 0 else float("nan")


def profit_factor(profits: np.ndarray | pd.Series) -> float:
    p = np.asarray(profits, dtype=float)
    gains, losses = p[p > 0].sum(), -p[p < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return float(gains / losses)


def trade_stats(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    p, r = trades["profit_abs"], trades["profit_ratio"]
    wins, losses = p[p > 0], p[p < 0]
    return {
        "trades": n,
        "win_rate": float((p > 0).mean()),
        "profit_factor": profit_factor(p),
        "expectancy_pct": float(r.mean()),  # mean net return per trade
        "expectancy_abs": float(p.mean()),
        "avg_win_abs": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_abs": float(losses.mean()) if len(losses) else 0.0,
        "avg_duration_h": float(
            (pd.to_datetime(trades["close_date"]) - pd.to_datetime(trades["open_date"]))
            .dt.total_seconds()
            .mean()
            / 3600
        ),
    }


def monthly_returns(equity: pd.Series, wallet: float) -> pd.Series:
    """Calendar-month return of the equity curve (first month measured from the wallet)."""
    month_end = equity.resample("1ME").last()
    previous = month_end.shift(1)
    previous.iloc[0] = wallet
    out = month_end / previous - 1.0
    out.index = out.index.strftime("%Y-%m")
    return out


def exposure(trades: pd.DataFrame, index: pd.DatetimeIndex) -> dict:
    """Share of hours with at least one open position, and average positions open."""
    count = np.zeros(len(index))
    for t in trades.itertuples(index=False):
        p0 = int(index.searchsorted(pd.Timestamp(t.open_date)))
        p1 = int(index.searchsorted(pd.Timestamp(t.close_date)))
        count[p0:p1] += 1
    return {"time_in_market": float((count > 0).mean()), "avg_open_positions": float(count.mean())}


def exposure_profile(trades: pd.DataFrame, equity: pd.Series) -> dict:
    """Gross exposure = capital in open positions at cost / mark-to-market equity, hourly."""
    index = equity.index
    cost = np.zeros(len(index) + 1)
    for t in trades.itertuples(index=False):
        p0 = int(index.searchsorted(pd.Timestamp(t.open_date)))
        p1 = int(index.searchsorted(pd.Timestamp(t.close_date)))
        cost[p0] += float(t.open_value)
        cost[p1] -= float(t.open_value)
    gross = np.cumsum(cost)[: len(index)]
    ratio = gross / np.where(equity.to_numpy() > 0, equity.to_numpy(), np.nan)
    ratio = ratio[np.isfinite(ratio)]
    if ratio.size == 0:
        return {"avg_gross_exposure": 0.0, "peak_gross_exposure": 0.0, "p95_gross_exposure": 0.0}
    return {
        "avg_gross_exposure": float(ratio.mean()),
        "peak_gross_exposure": float(ratio.max()),
        "p95_gross_exposure": float(np.quantile(ratio, 0.95)),
    }


def summarize(equity: pd.Series, trades: pd.DataFrame | None, wallet: float) -> dict:
    full = with_start(equity, wallet)
    d = daily_returns(full)
    out = {
        "net_return": net_return(equity, wallet),
        "max_drawdown": max_drawdown(full),
        "sharpe": sharpe(d),
        "sortino": sortino(d),
        "days": len(d),
    }
    if trades is not None:
        out.update(trade_stats(trades))
        out.update(exposure(trades, equity.index))
    return out
