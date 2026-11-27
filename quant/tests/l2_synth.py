"""Synthetic hourly market + matching daily L1 panel for the L2 tests (no market data)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from quantlab import l1_max3 as l1
from quantlab.execution import PriceData


Q = Path(__file__).resolve().parents[1]
SPEC = json.loads((Q / "protocol/m4_l2_preregistration.json").read_text(encoding="utf-8"))
L1SPEC = json.loads((Q / "protocol/h1_l1_preregistration.json").read_text(encoding="utf-8"))
START_DAILY = pd.Timestamp("2020-11-01", tz="UTC")
START_HOURLY = pd.Timestamp("2021-01-01", tz="UTC")


def market(
    n_days_hourly=120,
    n_assets=30,
    seed=1,
    vol=0.004,
    ends=None,
    lam_premium=0.0,
    volume=1e9,
    volume_override=None,
    flat=False,
):
    """Returns (daily Panel, hourly PriceData, symbols). ``ends`` = {symbol index: hour index at which prints stop}."""
    n_hours = 24 * n_days_hourly
    pre_hours = 24 * (pd.Timestamp("2021-01-01", tz="UTC") - START_DAILY).days
    total = pre_hours + n_hours
    idx = pd.date_range(START_DAILY, periods=total, freq="1h", tz="UTC")
    rng = np.random.default_rng(seed)
    lam = rng.uniform(0, 1, n_assets)
    closes = np.empty((total, n_assets))
    for j in range(n_assets):
        r = rng.normal(0, vol, total)
        v = rng.random(total)
        pj = 0.0005 * (0.2 + 2 * lam[j])
        r += (v < pj) * 0.12 - ((v >= pj) & (v < 2 * pj)) * 0.12
        r -= lam_premium * (lam[j] - 0.5) * 0.0004
        closes[:, j] = 100 * np.exp(np.cumsum(r)) if not flat else 100.0
    opens = np.vstack([np.full((1, n_assets), 100.0), closes[:-1]])
    symbols = [f"S{j:02d}USDT" for j in range(n_assets)]
    for j, h in (ends or {}).items():
        closes[h:, j] = np.nan
        opens[h:, j] = np.nan
    # daily candles from the hourly ones
    n_daily = total // 24
    do = opens.reshape(n_daily, 24, n_assets)[:, 0, :]
    dc = closes.reshape(n_daily, 24, n_assets)[:, -1, :]
    with np.errstate(invalid="ignore"):
        dc = np.where(np.isfinite(closes.reshape(n_daily, 24, n_assets)).all(axis=1), dc, np.nan)
    dates = pd.date_range(START_DAILY, periods=n_daily, freq="1D", tz="UTC")
    member = np.isfinite(dc) & np.isfinite(do)
    panel = l1.Panel(dates, symbols, do, dc, member, np.zeros((n_daily, n_assets), dtype=int))
    # hourly price data from 2021-01-01
    cand = {}
    for j, s in enumerate(symbols):
        df = pd.DataFrame({"date": idx, "open": opens[:, j], "high": np.fmax(opens[:, j], closes[:, j]), "low": np.fmin(opens[:, j], closes[:, j]),
                           "close": closes[:, j], "volume": volume_override.get(j, volume) if volume_override else volume})  # fmt: skip
        df = df[df["date"] >= START_HOURLY].dropna(subset=["open"])
        cand[f"{s[:-4]}/USDT"] = df
    hidx = pd.date_range(START_HOURLY, periods=n_hours, freq="1h", tz="UTC")
    return panel, PriceData(cand, hidx), symbols


def spec_for(panel: l1.Panel, last_rebalance: str = "2021-04-28") -> dict:
    s = json.loads(json.dumps(SPEC))
    s["portfolio"]["last_rebalance_day"] = last_rebalance
    s["evaluation"]["hourly_as_of"] = (
        str((panel.dates[-1] + pd.Timedelta(days=1)).date()) + " 00:00"
    )
    s["statistics"]["daily_hac_lag"] = 5
    s["evaluation"]["regime"]["reference_symbol"] = "S00USDT"
    return s
