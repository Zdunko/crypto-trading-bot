"""
Validation layer: walk-forward windows, market regimes, uncertainty (bootstrap) and the
mechanical evaluation of the frozen pass/fail criteria (see ``quant/protocol/protocol.json``).

Nothing here optimises anything; every function is a pure measurement.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import pandas as pd

from quantlab.metrics import profit_factor


# ------------------------------------------------------------------ walk-forward windows
def calendar_windows(
    start: str, end_exclusive: str, months: int, min_months: int = 3
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Consecutive ``months``-long windows from ``start``; a shorter last window is kept only if
    it spans at least ``min_months`` (otherwise it is dropped and the omission is reportable)."""
    s, e = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end_exclusive, tz="UTC")
    out = []
    while s < e:
        w_end = min(s + pd.DateOffset(months=months), e)
        if w_end == s + pd.DateOffset(months=months) or w_end >= s + pd.DateOffset(
            months=min_months
        ):
            out.append((s, w_end))
        s = s + pd.DateOffset(months=months)
    return out


def window_stats(
    equity: pd.Series, windows: list[tuple[pd.Timestamp, pd.Timestamp]], wallet: float
) -> list[dict]:
    rows = []
    for w_start, w_end in windows:
        before = equity[equity.index < w_start]
        v0 = float(before.iloc[-1]) if len(before) else wallet
        inside = equity[(equity.index >= w_start) & (equity.index < w_end)]
        if inside.empty:
            continue
        v1 = float(inside.iloc[-1])
        rows.append(
            {
                "start": str(w_start.date()),
                "end": str(w_end.date()),
                "return": v1 / v0 - 1.0,
                "profit": v1 - v0,
            }
        )
    return rows


# ------------------------------------------------------------------ regimes
def daily_regimes(candles_1h: pd.DataFrame, ema_period: int = 200, adx_trend: float = 25.0):
    """
    Market regime per UTC day from BTC/USDT hourly candles: resample to daily, then the shared
    ``quant_common.market_regime`` (ADX(14) >= adx_trend and close vs EMA). The label of day D
    is only known after D closes, so it is applied to trades from D+1 on.
    """
    from quant_common import market_regime  # strategies directory must be on PYTHONPATH

    df = candles_1h.assign(date=pd.to_datetime(candles_1h["date"], utc=True)).set_index("date")
    daily = (
        df.resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    labels = market_regime(daily.reset_index(drop=True), ema_period=ema_period, adx_trend=adx_trend)
    return pd.Series(labels.to_numpy(), index=daily.index.as_unit("ns"))


def trade_regimes(trades: pd.DataFrame, labels: pd.Series) -> pd.Series:
    """Regime of the last COMPLETED day before each trade's entry (no look-ahead)."""
    opened = pd.to_datetime(trades["open_date"], utc=True).dt.as_unit("ns")
    prev_day = opened.dt.floor("1D") - pd.Timedelta("1D")
    return prev_day.map(labels).fillna("unknown").reset_index(drop=True)


def regime_stats(trades: pd.DataFrame, labels: pd.Series) -> dict[str, dict]:
    regimes = trade_regimes(trades, labels)
    out = {}
    for name in ("bull", "bear", "sideways", "unknown"):
        sel = trades.reset_index(drop=True)[regimes == name]
        out[name] = {
            "trades": len(sel),
            "profit_factor": profit_factor(sel["profit_abs"]) if len(sel) else float("nan"),
            "expectancy_pct": float(sel["profit_ratio"].mean()) if len(sel) else float("nan"),
        }
    return out


def pair_profit_shares(trades: pd.DataFrame) -> dict[str, float]:
    """Each pair's share of total net profit (only meaningful when the total is positive)."""
    total = float(trades["profit_abs"].sum())
    if total <= 0:
        return {}
    return {p: float(v / total) for p, v in trades.groupby("pair")["profit_abs"].sum().items()}


# ------------------------------------------------------------------ uncertainty
def bootstrap_ci(
    values: np.ndarray, stat: Callable[[np.ndarray], float], n: int, seed: int, level: float = 0.95
) -> tuple[float, float]:
    """Percentile CI of ``stat`` under i.i.d. resampling of trades (optimistic: trades overlap)."""
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    stats = np.array([stat(v[rng.integers(0, len(v), len(v))]) for _ in range(n)])
    lo, hi = np.nanpercentile(stats, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def block_bootstrap_ci(
    arrays: list[np.ndarray],
    stat: Callable[..., float],
    n: int,
    seed: int,
    block: int,
    level: float = 0.95,
) -> tuple[float, float]:
    """
    Circular block bootstrap of aligned daily-return arrays (same indices drawn for all arrays,
    so paired statistics such as a Sortino difference keep their dependence). ``block`` days
    preserve autocorrelation/volatility clustering within blocks.
    """
    arrs = [np.asarray(a, dtype=float) for a in arrays]
    t = len(arrs[0])
    if t < 2 * block:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    nb = math.ceil(t / block)
    starts = rng.integers(0, t, size=(n, nb))
    idx = ((starts[:, :, None] + np.arange(block)) % t).reshape(n, -1)[:, :t]
    stats = np.array([stat(*[a[i] for a in arrs]) for i in idx])
    lo, hi = np.nanpercentile(stats, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


# ------------------------------------------------------------------ criteria
def _ok(x: float, op: str, thr: float) -> bool:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return False  # undefined never passes
    return {">=": x >= thr, ">": x > thr, "<=": x <= thr}[op]


def evaluate_criteria(m: dict, crit: dict) -> list[dict]:
    """
    Apply T1-T10 to the measurements ``m`` using thresholds ``crit`` from the frozen protocol.

    ``m`` keys: base{trades,net_return,max_drawdown,sortino,profit_factor}, pair_share_max,
    bench{sortino,max_drawdown}, stress{net_return,profit_factor}, windows[{return,profit}],
    regimes{name:{trades,profit_factor}}, variants[net_return...], bias_clean (bool | None).
    """
    b, bench, st = m["base"], m["bench"], m["stress"]
    rows: list[dict] = []

    def add(cid, desc, value, thr, passed):
        rows.append(
            {"id": cid, "desc": desc, "value": value, "threshold": thr, "passed": bool(passed)}
        )

    c = crit
    add(
        "T1a",
        "closed trades",
        b["trades"],
        f">= {c['T1']['min_trades']}",
        _ok(b["trades"], ">=", c["T1"]["min_trades"]),
    )
    share = m.get("pair_share_max")
    add(
        "T1b",
        "max single-pair share of net profit",
        share,
        f"<= {c['T1']['max_pair_profit_share']}",
        share is not None and share <= c["T1"]["max_pair_profit_share"],
    )
    add("T2", "net return after base costs", b["net_return"], "> 0", _ok(b["net_return"], ">", 0.0))
    add(
        "T3",
        "Sortino vs benchmark",
        b["sortino"],
        f">= {bench['sortino']:.3f}",
        _ok(b["sortino"], ">=", bench["sortino"]),
    )
    dd_limit = min(c["T4"]["max_drawdown"], bench["max_drawdown"])
    add(
        "T4",
        "max drawdown",
        b["max_drawdown"],
        f"<= {dd_limit:.3f} (min of {c['T4']['max_drawdown']}, benchmark)",
        _ok(b["max_drawdown"], "<=", dd_limit),
    )
    add(
        "T5",
        "profit factor",
        b["profit_factor"],
        f">= {c['T5']['min_profit_factor']}",
        _ok(b["profit_factor"], ">=", c["T5"]["min_profit_factor"]),
    )
    add(
        "T6",
        "stress: net return and profit factor",
        [st["net_return"], st["profit_factor"]],
        f"> 0 and >= {c['T6']['min_profit_factor']}",
        _ok(st["net_return"], ">", 0.0)
        and _ok(st["profit_factor"], ">=", c["T6"]["min_profit_factor"]),
    )

    w = m["windows"]
    pos = sum(1 for x in w if x["return"] > 0)
    frac = pos / len(w) if w else float("nan")
    total = sum(x["profit"] for x in w)
    top = max((x["profit"] for x in w), default=0.0)
    conc = top / total if total > 0 else float("nan")
    add(
        "T7a",
        "share of windows with positive return",
        frac,
        f">= {c['T7']['min_positive_window_share']}",
        _ok(frac, ">=", c["T7"]["min_positive_window_share"]),
    )
    add(
        "T7b",
        "largest window share of total profit",
        conc,
        f"<= {c['T7']['max_window_profit_share']}",
        _ok(conc, "<=", c["T7"]["max_window_profit_share"]),
    )

    bad = {
        k: v["profit_factor"]
        for k, v in m["regimes"].items()
        if k != "unknown"
        and v["trades"] >= c["T8"]["min_regime_trades"]
        and not _ok(v["profit_factor"], ">=", c["T8"]["min_profit_factor"])
    }
    add(
        "T8",
        "profit factor per regime with enough trades",
        bad or "all ok",
        f">= {c['T8']['min_profit_factor']} where trades >= {c['T8']['min_regime_trades']}",
        not bad,
    )

    v = m["variants"]
    share_pos = sum(1 for x in v if x > 0) / len(v) if v else float("nan")
    add(
        "T9",
        "share of parameter variants with net return > 0",
        share_pos,
        f">= {c['T9']['min_positive_variant_share']}",
        _ok(share_pos, ">=", c["T9"]["min_positive_variant_share"]),
    )
    add(
        "T10",
        "bias checks clean (lookahead + recursive)",
        m.get("bias_clean"),
        "True",
        m.get("bias_clean") is True,
    )
    return rows


def verdict(rows: list[dict]) -> dict:
    failed = [r["id"] for r in rows if not r["passed"]]
    return {"validated_on_evaluation": not failed, "failed": failed}
