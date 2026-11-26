"""S6 benchmark infrastructure (original plan S4 plus the owner's S6 list).

Engine-based benchmarks are ordinary :class:`~quantlab.execution.Strategy` objects run through the SAME
Stage 0 engine and ``ExecConfig`` (fees, slippage, liquidity cap, minimum notional, valuation) as any
strategy, so strategy and benchmark are always costed alike. All decisions use completed candles only
(``History``), fail closed on missing data, and are deterministic. Legacy benchmarks B1-B5 (protocol v3,
``quantlab.equity``) are NOT redefined here: the registry points at them unchanged. Daily-resolution
benchmarks (``interval 1d``). Pure functions on returns provide the matched comparators, the random-timing
null and the comparison statistics. No market data is used by this module itself.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quantlab import metrics
from quantlab.execution import History, Order, PortfolioView, Result, Strategy
from quantlab.stats import holm, moments


DAYS = 365
STATS: dict[str, float] = {
    "bootstrap_n": 2000,
    "bootstrap_block_days": 10,
    "bootstrap_seed": 20261125,
    "alpha": 0.05,
}
UniverseFn = Callable[[pd.Timestamp], "set[str] | list[str]"]


def _fresh(hist: History, pair: str, max_stale: int) -> bool:
    """A pair is usable only if it printed a candle within the last ``max_stale`` candles."""
    if pair not in hist.pairs:
        return False
    c = hist.closes(pair, max_stale)
    return len(c) > 0 and not bool(np.isnan(c).all())


def _rebalance(
    view: PortfolioView, members: list[str], exposure: float, min_notional: float
) -> list[Order]:
    """Orders that move the book to ``exposure`` x equity, equal-weighted over ``members``."""
    orders: list[Order] = []
    held = view.positions
    for p in sorted(held):
        if p not in members:
            orders.append(Order(p, "sell", fraction=1.0, reason="benchmark_out"))
    n = len(members)
    if n == 0 or exposure <= 0 or view.equity <= 0:
        return orders + [
            Order(p, "sell", fraction=1.0, reason="benchmark_flat")
            for p in sorted(held)
            if p in members
        ]
    target = exposure * view.equity / n
    for p in members:
        cur = held.get(p, (0.0, 0.0))[1]
        diff = target - cur
        if diff > min_notional:
            orders.append(Order(p, "buy", notional=diff, reason="benchmark_in"))
        elif -diff > min_notional and cur > 0:
            orders.append(Order(p, "sell", fraction=min(1.0, -diff / cur), reason="benchmark_trim"))
    return orders


class Cash(Strategy):
    """Never trades: equity stays at the wallet (no interest assumed)."""

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        return []


class BuyHold(Strategy):
    """Equal-weight buy-and-hold of fixed pairs, bought once at the first candle with data, never rebalanced."""

    def __init__(self, pairs: list[str], max_stale: int = 3):
        self.pairs, self.max_stale, self.done = sorted(pairs), max_stale, False

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        if self.done:
            return []
        ok = [p for p in self.pairs if _fresh(hist, p, self.max_stale)]
        if not ok:
            return []
        self.done = True
        return [Order(p, "buy", notional=view.cash / len(ok), reason="buy_hold") for p in ok]


class PitEqualWeight(Strategy):
    """Equal weight of the point-in-time universe, rebalanced at the first candle of each month.
    Members that stop printing candles are not (re)bought; positions stuck without candles stay and are reported."""

    def __init__(self, universe_fn: UniverseFn, max_stale: int = 3, min_notional: float = 5.0):
        self.universe_fn, self.max_stale, self.min_notional = universe_fn, max_stale, min_notional
        self._last: tuple[int, int] | None = None

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        key = (t.year, t.month)
        if key == self._last:
            return []
        members = sorted(p for p in self.universe_fn(t) if _fresh(hist, p, self.max_stale))
        if not members and not view.positions:
            return []  # nothing usable yet: try again on the next candle
        self._last = key
        return _rebalance(view, members, 1.0, self.min_notional)


class SimpleTrend(Strategy):
    """Fixed-convention trend benchmark: hold, equal weight, the universe members whose last completed
    close is above their ``window``-day simple average (a window with any missing close is NOT 'on')."""

    def __init__(
        self,
        universe_fn: UniverseFn,
        window: int = 100,
        max_stale: int = 3,
        min_notional: float = 5.0,
    ):
        self.universe_fn, self.window, self.max_stale, self.min_notional = (
            universe_fn,
            window,
            max_stale,
            min_notional,
        )
        self._on: list[str] | None = None

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        on = []
        for p in sorted(self.universe_fn(t)):
            if not _fresh(hist, p, self.max_stale):
                continue
            c = hist.closes(p, self.window)
            if len(c) == self.window and not np.isnan(c).any() and c[-1] > c.mean():
                on.append(p)
        if on == self._on:
            return []
        self._on = on
        return _rebalance(view, on, 1.0, self.min_notional)


class VolTargeted(Strategy):
    """Ex-ante volatility-targeted equal-weight benchmark: exposure = min(1, sigma_target / trailing vol) where
    the trailing vol is that of the equal-weight proxy of the usable members over ``vol_window`` completed days
    (annualised, 365). Unknown vol = no exposure. Rebalances when exposure moves by more than ``band`` or the
    month changes. Parameters are the frozen Family A conventions (0.4 / 30 / 0.05), none tuned."""

    def __init__(self, universe_fn: UniverseFn, sigma_target: float = 0.4, vol_window: int = 30,
                 band: float = 0.05, max_stale: int = 3, min_notional: float = 5.0):  # fmt: skip
        self.universe_fn, self.sigma, self.win, self.band = (
            universe_fn,
            sigma_target,
            vol_window,
            band,
        )
        self.max_stale, self.min_notional = max_stale, min_notional
        self._f: float | None = None
        self._month: tuple[int, int] | None = None

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        members = sorted(p for p in self.universe_fn(t) if _fresh(hist, p, self.max_stale))
        f = 0.0
        if members:
            rets = []
            for p in members:
                c = hist.closes(p, self.win + 1)
                if len(c) == self.win + 1 and not np.isnan(c).any():
                    rets.append(c[1:] / c[:-1] - 1.0)
            if rets:
                proxy = np.mean(rets, axis=0)
                sd = float(np.std(proxy, ddof=1)) * math.sqrt(DAYS)
                f = min(1.0, self.sigma / sd) if sd > 0 else 1.0
        key = (t.year, t.month)
        if self._f is not None and key == self._month and abs(f - self._f) <= self.band:
            return []
        self._f, self._month = f, key
        return _rebalance(view, members, f, self.min_notional)


class ScheduledExposure(Strategy):
    """Equal-weight members held at a given exposure path (rest in cash): the exposure-matched benchmark when
    the path is a strategy's own exposure, the volatility-matched / cash-mix benchmark when it is constant.
    A missing schedule value means zero exposure (fail closed)."""

    def __init__(self, universe_fn: UniverseFn, schedule: pd.Series, band: float = 0.05,
                 max_stale: int = 3, min_notional: float = 5.0):  # fmt: skip
        self.universe_fn, self.schedule, self.band = universe_fn, schedule, band
        self.max_stale, self.min_notional = max_stale, min_notional
        self._f: float | None = None
        self._month: tuple[int, int] | None = None

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        raw = self.schedule.get(t, 0.0)
        f = float(raw) if math.isfinite(float(raw)) else 0.0
        f = min(max(f, 0.0), 1.0)
        members = sorted(p for p in self.universe_fn(t) if _fresh(hist, p, self.max_stale))
        key = (t.year, t.month)
        if self._f is not None and key == self._month and abs(f - self._f) <= self.band:
            return []
        self._f, self._month = f, key
        return _rebalance(view, members, f, self.min_notional)


def exposure_schedule(result: Result) -> pd.Series:
    """A strategy's gross exposure known at each candle open (the previous close's value)."""
    if result.exposure is None:
        raise ValueError("result carries no exposure series")
    return result.exposure.shift(1).fillna(0.0)


# ---------------------------------------------------------------------------- matched comparators
def daily_returns(equity: pd.Series, wallet: float) -> pd.Series:
    return metrics.daily_returns(metrics.with_start(equity, wallet))


def volatility_scale(
    strategy_returns: pd.Series, benchmark_returns: pd.Series, cap: float = 1.0
) -> float:
    """Static scale that gives the benchmark the strategy's realised volatility (no leverage: capped at 1)."""
    sb = float(np.std(np.asarray(benchmark_returns), ddof=1))
    ss = float(np.std(np.asarray(strategy_returns), ddof=1))
    if not (sb > 0 and math.isfinite(sb) and math.isfinite(ss)):
        return 0.0
    return min(cap, ss / sb)


def max_drawdown_of_mix(returns: np.ndarray, k: float) -> float:
    eq = np.cumprod(1.0 + k * returns)
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    return float(np.max((peak - eq) / peak)) if len(eq) else 0.0


def solve_cash_mix(
    returns: pd.Series | np.ndarray, target_mdd: float = 0.20, iters: int = 60
) -> float:
    """Largest static benchmark share k in [0, 1] whose daily-rebalanced mix with cash has max drawdown <=
    target (bisection; deterministic). An honest 'no skill' reference for the T4 limit; ex-post by construction."""
    r = np.asarray(returns, dtype=float)
    if max_drawdown_of_mix(r, 1.0) <= target_mdd:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        if max_drawdown_of_mix(r, mid) <= target_mdd:
            lo = mid
        else:
            hi = mid
    return lo


def random_timing_null(returns: pd.Series | np.ndarray, exposure: pd.Series | np.ndarray, n: int = 2000,
                       seed: int = 20261125, block: int = 10, stat: str = "sharpe") -> dict:  # fmt: skip
    """Does the timing of the exposure add value beyond its level? The observed statistic of
    exposure x return is compared with circularly block-shifted/permuted exposure schedules (same level,
    same autocorrelation structure within blocks). One-sided p = (1 + #{null >= observed}) / (n + 1)."""
    r = np.asarray(returns, dtype=float)
    e = np.asarray(exposure, dtype=float)
    if len(r) != len(e) or len(r) < 2 * block:
        raise ValueError("returns and exposure must have equal length >= 2 blocks")

    def s(x: np.ndarray) -> float:
        if stat == "total_return":
            return float(np.prod(1.0 + x) - 1.0)
        sd = float(np.std(x, ddof=1))
        return float(np.mean(x) / sd * math.sqrt(DAYS)) if sd > 0 else 0.0

    obs = s(e * r)
    rng = np.random.default_rng(seed)
    nb = len(e) // block
    blocks = [e[i * block : (i + 1) * block] for i in range(nb)]
    tail = e[nb * block :]
    null = np.empty(n)
    for k in range(n):
        order = rng.permutation(nb)
        perm = np.concatenate([blocks[i] for i in order] + [tail])
        null[k] = s(perm * r)
    return {"observed": obs, "null_mean": float(null.mean()), "null_sd": float(null.std(ddof=1)),
            "p_one_sided": float((1 + np.sum(null >= obs)) / (n + 1)), "n": n, "seed": seed, "block": block}  # fmt: skip


# ---------------------------------------------------------------------------- performance and comparison
@dataclass
class Perf:
    values: dict

    def __getitem__(self, k: str) -> float:
        return self.values[k]


def turnover_and_costs(
    result: Result, fee: float, slippage: float, years: float, mean_equity: float
) -> dict:
    """Estimated from fills the engine exposes: buys = closed trades' open value + still-open positions' cost;
    sells = closed trades' proceeds. Cost = traded notional x (fee + slippage) (an estimate, labelled as such)."""
    t = result.trades
    buys = float(t["open_value"].sum()) if len(t) else 0.0
    sells = float((t["open_value"] + t["profit_abs"]).sum()) if len(t) else 0.0
    buys += sum(p.open_value for p in result.state.positions.values())
    traded = buys + sells
    return {"traded_notional": traded, "turnover_per_year": traded / mean_equity / years if years > 0 and mean_equity > 0 else float("nan"),
            "estimated_cost": traded * (fee + slippage)}  # fmt: skip


def performance(
    result: Result, wallet: float, fee: float = 0.001, slippage: float = 0.0005
) -> dict:
    eq = result.equity.dropna()
    if eq.empty:
        raise ValueError("empty equity")
    r = daily_returns(eq, wallet)
    days = max((eq.index[-1] - eq.index[0]).days + 1, 1)
    years = days / DAYS
    net = float(eq.iloc[-1] / wallet - 1.0)
    cagr = float((eq.iloc[-1] / wallet) ** (1 / years) - 1.0) if eq.iloc[-1] > 0 else -1.0
    mdd = metrics.max_drawdown(metrics.with_start(eq, wallet))
    arr = np.asarray(r, dtype=float)
    k = max(1, math.ceil(0.05 * len(arr)))
    sk, ku = (moments(arr)[1], moments(arr)[2]) if len(arr) > 3 else (float("nan"), float("nan"))
    out = {
        "net_return": net, "cagr": cagr, "max_drawdown": mdd,
        "sharpe": metrics.sharpe(arr), "sortino": metrics.sortino(arr),
        "calmar": cagr / mdd if mdd > 0 else float("nan"),
        "exposure_mean": float(result.exposure.mean()) if result.exposure is not None else float("nan"),
        "cvar_5pct_daily": float(np.sort(arr)[:k].mean()), "worst_day": float(arr.min()),
        "skew": sk, "kurtosis": ku, "days": days,
    }  # fmt: skip
    out.update(turnover_and_costs(result, fee, slippage, years, float(eq.mean())))
    return out


def _bootstrap_indices(n: int, block: int, draws: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    nb = math.ceil(n / block)
    starts = rng.integers(0, n, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(draws, -1)[:, :n]


def compare(
    a: pd.Series, b: pd.Series, n: int = 2000, block: int = 10, seed: int = 20261125
) -> dict:
    """Strategy ``a`` against benchmark ``b`` on aligned daily returns: active return, tracking error,
    information ratio, and a paired circular block bootstrap of the Sharpe difference (one-sided p that a <= b)."""
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    if len(j) < 2 * block:
        raise ValueError("too few aligned days for the block bootstrap")
    ra, rb = j["a"].to_numpy(), j["b"].to_numpy()
    act = ra - rb
    sd = float(np.std(act, ddof=1))
    idx = _bootstrap_indices(len(j), block, n, seed)

    def sh(x: np.ndarray) -> np.ndarray:
        s = x.std(axis=1, ddof=1)
        return np.where(s > 0, x.mean(axis=1) / np.where(s > 0, s, 1) * math.sqrt(DAYS), 0.0)

    diff = sh(ra[idx]) - sh(rb[idx])
    obs = metrics.sharpe(ra) - metrics.sharpe(rb)
    return {
        "days": len(j), "active_return_annual": float(act.mean() * DAYS), "tracking_error": sd * math.sqrt(DAYS),
        "information_ratio": float(act.mean() / sd * math.sqrt(DAYS)) if sd > 0 else float("nan"),
        "sharpe_diff": float(obs), "sharpe_diff_ci95": (float(np.quantile(diff, 0.025)), float(np.quantile(diff, 0.975))),
        "p_one_sided": float((1 + np.sum(diff <= 0)) / (n + 1)), "n": n, "block": block, "seed": seed,
    }  # fmt: skip


def compare_set(
    strategy_returns: pd.Series, benchmarks: dict[str, pd.Series], alpha: float = STATS["alpha"]
) -> dict:
    """All comparisons of one strategy against a registered benchmark set, with a Holm correction over the set
    (the multiple-testing family of benchmark comparisons is always reported together)."""
    names = sorted(benchmarks)
    rows = {k: compare(strategy_returns, benchmarks[k]) for k in names}
    rej = holm([rows[k]["p_one_sided"] for k in names], alpha)
    for k, r in zip(names, rej, strict=True):
        rows[k]["holm_rejects_null"] = bool(r)
    return rows


# ---------------------------------------------------------------------------- stuck positions
def stuck_positions(
    result: Result, last_candle: dict[str, pd.Timestamp], now: pd.Timestamp, max_age: pd.Timedelta
) -> list[dict]:
    """Held positions whose pair has not printed a candle for longer than ``max_age`` (valued at the last close
    by the engine, i.e. optimistically). ``last_candle`` maps pair -> time of its last non-missing candle."""
    out = []
    for pair, p in sorted(result.state.positions.items()):
        last = last_candle.get(pair)
        if last is None or now - last > max_age:
            out.append(
                {
                    "pair": pair,
                    "qty": p.qty,
                    "cost": p.open_value,
                    "last_candle": None if last is None else str(last),
                }
            )
    return out


class PitUniverse:
    """Universe callable backed by the frozen S4 dataset loader. Any loader error (holdout date, missing table,
    ...) yields an EMPTY universe (fail closed: nothing new is bought) and is recorded in ``errors``."""

    def __init__(self, dataset, threshold: str = "1M", max_stale_days: int = 3):
        self.ds, self.threshold, self.max_stale_days = dataset, threshold, max_stale_days
        self.errors: list[dict] = []

    def __call__(self, t: pd.Timestamp) -> set[str]:
        from quantlab.pit_loader import PitError, pair_of

        try:
            return {pair_of(s) for s in self.ds.universe_at(t, self.threshold, self.max_stale_days)}
        except PitError as e:
            self.errors.append({"t": str(t), "error": type(e).__name__})
            return set()
