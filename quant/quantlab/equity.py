"""Mark-to-market equity curves for strategy trades and for the buy-and-hold benchmark."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantlab.costs import CostScenario


def hourly_index(start: str, end_exclusive: str) -> pd.DatetimeIndex:
    return pd.date_range(start, end_exclusive, freq="1h", inclusive="left", tz="UTC")


def close_matrix(candles: dict[str, pd.DataFrame], index: pd.DatetimeIndex) -> pd.DataFrame:
    """Close price per pair on ``index`` (forward-filled; NaN before a pair's first candle)."""
    cols = {}
    for pair, df in candles.items():
        s = df.assign(date=pd.to_datetime(df["date"], utc=True)).set_index("date")["close"]
        s.index = s.index.as_unit("ns")  # feather files may carry ms/us resolution
        cols[pair] = s.reindex(index).ffill()
    return pd.DataFrame(cols, index=index)


def build_equity(
    costed_trades: pd.DataFrame,
    closes: pd.DataFrame,
    wallet: float,
    scenario: CostScenario,
) -> pd.Series:
    """
    Equity on every hourly row of ``closes``: wallet + realised profit + open positions valued at
    liquidation value (candle close less one exit fee and slippage). A trade entered in candle T0
    and exited in candle T1 is open on rows [T0, T1) and realised from T1 on.
    """
    index = closes.index
    n = len(index)
    realised = np.zeros(n)
    unrealised = np.zeros(n)
    liq = 1.0 - scenario.fee - scenario.slippage
    for t in costed_trades.itertuples(index=False):
        p0 = int(index.searchsorted(pd.Timestamp(t.open_date)))
        p1 = int(index.searchsorted(pd.Timestamp(t.close_date)))
        p0, p1 = min(p0, n), min(p1, n)
        if p1 < n:
            realised[p1:] += t.profit_abs
        if p1 > p0:
            px = closes[t.pair].to_numpy()[p0:p1]
            unrealised[p0:p1] += t.amount * px * liq - t.open_value
    return pd.Series(wallet + realised + unrealised, index=index)


def buy_and_hold(
    candles: dict[str, pd.DataFrame],
    index: pd.DatetimeIndex,
    wallet: float,
    scenario: CostScenario,
    pairs: list[str] | None = None,
) -> tuple[pd.Series, list[str]]:
    """
    Equal-weight buy-and-hold: split ``wallet`` over the pairs that already trade at ``index[0]``,
    buy at that candle's open (paying fee and slippage), never rebalance. Valued at liquidation
    value, so the final value is net of the exit cost as well.
    """
    chosen = []
    opens = {}
    for pair in pairs or list(candles):
        df = candles[pair]
        dates = pd.to_datetime(df["date"], utc=True)
        row = df[dates == index[0]]
        if not row.empty:
            chosen.append(pair)
            opens[pair] = float(row["open"].iloc[0])
    if not chosen:
        raise ValueError("no pair has a candle at the start of the period")
    closes = close_matrix({p: candles[p] for p in chosen}, index)
    per_pair = wallet / len(chosen)
    value = np.zeros(len(index))
    for pair in chosen:
        amount = per_pair / (opens[pair] * (1 + scenario.slippage) * (1 + scenario.fee))
        value += amount * closes[pair].to_numpy() * (1 - scenario.slippage - scenario.fee)
    return pd.Series(value, index=index), chosen


def rebalanced_buy_and_hold(
    candles: dict[str, pd.DataFrame],
    index: pd.DatetimeIndex,
    wallet: float,
    scenario: CostScenario,
    pairs: list[str] | None = None,
) -> pd.Series:
    """
    Equal-weight benchmark rebalanced on the first hour of every month over the pairs already
    trading at that moment; each rebalance pays (fee + slippage) on the traded notional, and
    the final value is liquidation value. Used to show that the plain buy-and-hold benchmark
    is not an artefact of never rebalancing.
    """
    closes = close_matrix({p: candles[p] for p in (pairs or list(candles))}, index)
    cost = scenario.fee + scenario.slippage
    month = index.strftime("%Y-%m")
    holdings = pd.Series(0.0, index=closes.columns)  # units
    cash = wallet
    values = np.zeros(len(index))
    for i in range(len(index)):
        px = closes.iloc[i]
        live = px.notna()
        if i == 0 or month[i] != month[i - 1]:
            equity = cash + float((holdings * px.fillna(0.0)).sum())
            target = pd.Series(0.0, index=closes.columns)
            target[live] = equity / live.sum()
            trade_value = (target - holdings * px.fillna(0.0)).abs().sum()
            equity -= cost * trade_value
            holdings = (target / px).where(live, 0.0).fillna(0.0)
            holdings = holdings * (equity / max(float((holdings * px.fillna(0.0)).sum()), 1e-12))
            cash = 0.0
        values[i] = cash + float((holdings * px.fillna(0.0)).sum()) * (1.0 - cost)
    return pd.Series(values, index=index)
