"""M4 / L2: economic viability of the H1 (MAX3) signal as a long-only spot portfolio with realistic execution.

Pure, deterministic functions so every rule is testable on synthetic data. The registered rules are in
``protocol/m4_l2_preregistration.json``; this module implements them and nothing else (no tuning, no search).

* signal and universe: ``l1_max3`` (frozen); the portfolio holds the top quintile of S = -MAX3 among valid members,
  equal weight, long only, rebalanced every h days (h = 7 and 28);
* execution: the frozen Stage 0 engine on hourly candles (next-open fills, fee + slippage, 10 % participation cap
  with partial fills, minimum notional), decisions one hour after the daily candle completes (latency), wrapped by
  Risk Management V3 (zero recovery) with the frozen engine circuit breaker;
* comparators: cash, BTC buy-and-hold, point-in-time equal weight, a risk-matched BTC/cash mix (ex post) and a
  low-volatility portfolio built exactly like the strategy from the volatility rank.
"""

from __future__ import annotations

import csv
import gzip
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from quantlab import l1_max3 as l1
from quantlab import risk_status as rs
from quantlab.costs import BASE, STRESS, CostScenario
from quantlab.execution import ExecConfig, Order, PortfolioView, PriceData, Strategy, run
from quantlab.risk_v2 import RiskStateMachine
from quantlab.risk_v3 import RiskManagedStrategyV3, RiskV3Config


QUANT = Path(__file__).resolve().parents[1]
PREREG = QUANT / "protocol/m4_l2_preregistration.json"
DAYS_PER_YEAR = 365
COSTS = {"normal": BASE, "double": STRESS}


# ------------------------------------------------------------------------------------------ targets
def rebalance_days(spec: dict, h: int) -> list[pd.Timestamp]:
    p = spec["portfolio"]
    d0 = pd.Timestamp(p["first_rebalance_day"], tz="UTC")
    last = pd.Timestamp(p["last_rebalance_day"], tz="UTC")
    out, d = [], d0
    while d <= last:
        out.append(d)
        d += pd.Timedelta(days=h)
    return out


def pair_of(symbol: str) -> str:
    return f"{symbol[:-4]}/USDT"


def target_schedule(
    panel: l1.Panel, spec: dict, h: int, score: np.ndarray
) -> dict[pd.Timestamp, list[str]]:
    """{rebalance day D: [pairs]}. At D (00:00 UTC) only daily candles of days <= D-1 are used (the signal day is D-1).
    Eligible = member of the month universe with a valid score; K = max(min_assets, ceil(quantile x n)); highest score first;
    ties broken by symbol name; fewer than min_assets eligible -> no position (cash)."""
    p = spec["portfolio"]
    out: dict[pd.Timestamp, list[str]] = {}
    sym = np.array(panel.symbols)
    for d in rebalance_days(spec, h):
        t = int(panel.dates.searchsorted(d - pd.Timedelta(days=1)))
        if t < 0 or t >= len(panel.dates) or panel.dates[t] != d - pd.Timedelta(days=1):
            out[d] = []
            continue
        ok = panel.member[t] & np.isfinite(score[t])
        idx = np.where(ok)[0]
        if len(idx) < p["min_assets"]:
            out[d] = []
            continue
        k = max(p["min_assets"], math.ceil(p["top_quantile"] * len(idx)))
        order = sorted(idx, key=lambda j: (-score[t, j], sym[j]))
        out[d] = [pair_of(str(sym[j])) for j in order[:k]]
    return out


def vol_scores(panel: l1.Panel, spec: dict) -> np.ndarray:
    """Low-volatility score = - realised volatility (std of 28 daily returns), valid only where MAX3 is valid, so the
    two portfolios share the same eligible set."""
    sg = spec["signal"]
    s = l1.max3(panel.close, panel.epoch_start, sg["window_days"], sg["top_k"])
    vol = l1.reference_signals(panel.close)["realised_vol_28d_informational"]
    out = -vol
    out[~np.isfinite(s)] = np.nan
    return out


# ------------------------------------------------------------------------------------------ strategy
class TargetPortfolio(Strategy):
    """Buys the target assets that are not held (equal notional = equity x risk multiplier / K); sells held assets that left
    the target. Survivors are neither topped up nor trimmed (no averaging). Acts only at the decision hour."""

    def __init__(
        self,
        schedule: dict[pd.Timestamp, list[str]],
        min_notional: float = 5.0,
        decision_hour: int = 1,
    ):
        self.schedule, self.min_notional, self.decision_hour = schedule, min_notional, decision_hour

    def on_candle(self, t: pd.Timestamp, hist, view: PortfolioView) -> list[Order]:
        if t.hour != self.decision_hour:
            return []
        tgt = self.schedule.get(t.normalize())
        if tgt is None:
            return []
        orders = [
            Order(p, "sell", fraction=1.0, reason="rebalance")
            for p in sorted(view.positions)
            if p not in tgt
        ]
        if not tgt:
            return orders
        value = view.equity * view.risk_multiplier / len(tgt)
        if value >= self.min_notional:
            orders += [
                Order(p, "buy", notional=value, reason="rebalance")
                for p in tgt
                if p not in view.positions
            ]
        return orders


# ------------------------------------------------------------------------------------------ execution
@dataclass
class RunOut:
    equity: pd.Series  # hourly, engine liquidation value
    exposure: pd.Series
    trades: pd.DataFrame
    orders: list[dict]
    rejects: list[dict]
    hash: str
    ticks: list[dict]
    machine_records: list[dict]
    writeoffs: dict
    breaker_events: list[dict]
    open_value_end: float = 0.0


def final_epoch_feed(ds_dir: Path, pairs: set[str], spec: dict):
    """G3 status source restricted to the FINAL epoch of each symbol (an identity break that continues is not a delisting)."""
    last: dict[str, dict] = {}
    with gzip.open(Path(ds_dir) / "epochs.csv.gz", "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pair = pair_of(r["symbol"])
            if pair in pairs and (pair not in last or int(r["k"]) > last[pair]["k"]):
                last[pair] = {
                    "k": int(r["k"]),
                    "symbol": pair,
                    "end": pd.Timestamp(int(r["end_ms"]), unit="ms", tz="UTC")
                    + pd.Timedelta(
                        days=1
                    ),  # end_ms = OPEN of the last daily candle: its end is one day later
                }
    cutoff = pd.Timestamp(spec["evaluation"]["epoch_cutoff"], tz="UTC")
    return rs.epoch_feed(
        list(last.values()), pd.Timedelta(hours=spec["risk"]["stale_horizon_hours"]), cutoff
    )


def run_active(
    data: PriceData, schedule: dict, spec: dict, costs: CostScenario, with_risk: bool, feed=None
) -> RunOut:
    ex, p = spec["execution"], spec["portfolio"]
    cfg = ExecConfig(costs=costs, wallet=p["wallet"], min_notional=ex["min_notional"], max_defer=ex["max_defer"],
                     max_participation=ex["max_participation"], breaker=with_risk)  # fmt: skip
    inner = TargetPortfolio(schedule, ex["min_notional"], ex["decision_hour_utc"])
    if not with_risk:
        r = run(inner, data, cfg)
        ov = float(sum(p_.open_value for p_ in r.state.positions.values()))
        return RunOut(
            r.equity,
            r.exposure,
            r.trades,
            r.orders,
            r.rejects,
            r.hash,
            [],
            [],
            {},
            r.breaker_events,
            ov,
        )
    v3 = RiskV3Config()
    machine = RiskStateMachine.new(v3.v2, p["wallet"])
    strat = RiskManagedStrategyV3(inner, machine, v3, feed, decision_every=pd.Timedelta(days=1),
                                  decision_offset=pd.Timedelta(hours=ex["decision_hour_utc"]))  # fmt: skip
    r = run(strat, data, cfg)
    ov = float(sum(p_.open_value for p_ in r.state.positions.values()))
    return RunOut(
        r.equity,
        r.exposure,
        r.trades,
        r.orders,
        r.rejects,
        r.hash,
        strat.ticks,
        machine.records,
        strat.writeoffs,
        r.breaker_events,
        ov,
    )


# ------------------------------------------------------------------------------------------ metrics
def daily_equity(eq: pd.Series, wallet: float) -> pd.Series:
    d = eq.resample("1D").last()
    return pd.concat([pd.Series([wallet], index=[d.index[0] - pd.Timedelta(days=1)]), d])


def metrics(eq_hourly: pd.Series, wallet: float) -> dict:
    """Net metrics from the engine's hourly liquidation-value equity (fees and slippage already inside)."""
    de = daily_equity(eq_hourly, wallet)
    r = de.pct_change().dropna().to_numpy()
    years = (len(de) - 1) / DAYS_PER_YEAR
    end = float(de.iloc[-1])
    cagr = (end / wallet) ** (1.0 / years) - 1.0 if end > 0 and years > 0 else -1.0
    peak = np.maximum.accumulate(eq_hourly.to_numpy())
    mdd = float(np.max(1.0 - eq_hourly.to_numpy() / peak)) if len(eq_hourly) else 0.0
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    dd = float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2))) if len(r) else 0.0
    return {
        "final_equity": end, "net_return": end / wallet - 1.0, "cagr": cagr, "years": years,
        "sharpe": float(r.mean() / sd * math.sqrt(DAYS_PER_YEAR)) if sd > 0 else 0.0,
        "sortino": float(r.mean() / dd * math.sqrt(DAYS_PER_YEAR)) if dd > 0 else 0.0,
        "max_drawdown": mdd, "calmar": float(cagr / mdd) if mdd > 0 else 0.0,
        "daily_volatility": sd,
    }  # fmt: skip


def execution_stats(out: RunOut, costs: CostScenario, mean_equity: float, years: float) -> dict:
    """Turnover and cost estimates from filled notional: all buys (closed trades + positions still open at the end) and
    the proceeds of closed trades; every fill pays ``fee + slippage`` on its notional (the engine's cost model)."""
    tr = out.trades
    buys = (float(tr["open_value"].sum()) if len(tr) else 0.0) + out.open_value_end
    sells = float((tr["open_value"] + tr["profit_abs"]).sum()) if len(tr) else 0.0
    traded = buys + sells
    intended = float(sum(o["notional"] for o in out.orders if o["side"] == "buy"))
    rej = (
        pd.Series([r["reason"] for r in out.rejects]).value_counts().to_dict()
        if out.rejects
        else {}
    )
    return {
        "closed_trades": len(tr), "orders_issued": len(out.orders), "rejects": {k: int(v) for k, v in rej.items()},
        "filled_buy_notional": buys, "sell_proceeds_closed_trades": sells, "traded_notional": traded,
        "intended_buy_notional": intended, "fill_ratio": float(buys / intended) if intended > 0 else 1.0,
        "annual_one_way_turnover": float(traded / 2.0 / mean_equity / years) if mean_equity > 0 and years > 0 else 0.0,
        "estimated_cost_usd": float(traded * costs.per_side),
        "estimated_cost_drag_per_year": float(traded * costs.per_side / mean_equity / years) if mean_equity > 0 and years > 0 else 0.0,
        "mean_exposure": float(out.exposure.mean()),
    }  # fmt: skip


def capital_protection(out: RunOut, wallet: float, limit: float) -> dict:
    states = pd.Series([t["state"] for t in out.ticks]) if out.ticks else pd.Series(dtype=str)
    first_sd = next((r for r in out.machine_records if r["to"] == "SHUTDOWN"), None)
    lk = np.array([t["lk"] for t in out.ticks]) if out.ticks else np.array([])
    cons = np.array([t["cons"] for t in out.ticks]) if out.ticks else np.array([])
    return {
        "final_state": str(states.iloc[-1]) if len(states) else None,
        "hours_in_state": {k: int(v) for k, v in states.value_counts().items()},
        "transitions": [{"t": r["t"], "from": r["from"], "to": r["to"], "cause": r["cause"]} for r in out.machine_records],
        "shutdown": first_sd is not None, "first_shutdown_time": first_sd["t"] if first_sd else None,
        "write_offs": {k: float(v["realized_loss"]) for k, v in out.writeoffs.items()},
        "engine_breaker_events": [e for e in out.breaker_events if e.get("type") == "halt"][:5],
        "max_drawdown_last_known": float(l1_dd(lk)) if len(lk) else None,
        "max_drawdown_conservative": float(l1_dd(cons)) if len(cons) else None, "drawdown_limit": limit,
    }  # fmt: skip


def l1_dd(eq: np.ndarray) -> float:
    peak = np.maximum.accumulate(eq)
    return float(np.max((peak - eq) / np.where(peak > 0, peak, 1.0))) if len(eq) else 0.0


# ------------------------------------------------------------------------------------------ passive comparators (daily accounting)
def passive_equity(
    opens: np.ndarray,
    closes: np.ndarray,
    weights_at: dict[int, np.ndarray],
    costs: CostScenario,
    wallet: float,
) -> np.ndarray:
    """Daily mark-to-liquidation equity of a buy-and-rebalance portfolio. ``weights_at[i]`` = target weights (sum <= 1) set
    at the OPEN of day i. Trades cost ``fee + slippage`` per side on the traded notional; positions are valued at the
    close of the day net of the exit cost (the engine's convention); missing prices keep the last observed price."""
    t_n, s_n = opens.shape
    px_o, px_c = pd.DataFrame(opens).ffill().to_numpy(), pd.DataFrame(closes).ffill().to_numpy()
    qty = np.zeros(s_n)
    cash = wallet
    eq = np.full(t_n, np.nan)
    c = costs.per_side
    for i in range(t_n):
        if i in weights_at:
            w = weights_at[i]
            price = px_o[i]
            val = float(np.nansum(qty * price))
            total = cash + val * (1.0 - c)  # liquidation value of the current book
            target = (
                np.nan_to_num(w) * total / (1.0 + c)
            )  # buying costs (1 + c): never spend more than the book is worth
            cur = qty * price
            diff = target - cur
            sell = np.where(diff < 0, -diff, 0.0)
            buy = np.where(diff > 0, diff, 0.0)
            cash += float(np.nansum(sell) * (1.0 - c) - np.nansum(buy) * (1.0 + c))
            qty = np.where(
                np.isfinite(price) & (price > 0),
                (cur + diff) / np.where(price > 0, price, 1.0),
                qty,
            )
        eq[i] = cash + float(np.nansum(qty * px_c[i])) * (1.0 - c)
    return eq


# ------------------------------------------------------------------------------------------ statistics on returns
def paired_test(a: np.ndarray, b: np.ndarray, lag: int) -> dict:
    d = np.asarray(a, float) - np.asarray(b, float)
    mean, se, _ = l1.newey_west(d, lag)
    t = mean / se if se > 0 else 0.0
    return {"mean_daily_diff": mean, "annualised_diff": mean * DAYS_PER_YEAR, "t_hac": t,
            "p_one_sided": float(1.0 - l1.N.cdf(t)), "hac_lag": lag, "n_days": len(d)}  # fmt: skip


def alpha_regression(y: np.ndarray, x: np.ndarray, lag: int) -> dict:
    """OLS of daily strategy returns on one benchmark's returns with a Newey-West standard error of the intercept."""
    n = len(y)
    X = np.column_stack([np.ones(n), x])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    u = y - X @ beta
    xtx_inv = np.linalg.inv(X.T @ X)
    s = (X * u[:, None]).T @ (X * u[:, None]) / n
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1)
        g = (X[k:] * u[k:, None]).T @ (X[:-k] * u[:-k, None]) / n
        s += w * (g + g.T)
    cov = n * xtx_inv @ s @ xtx_inv
    se_a = math.sqrt(max(cov[0, 0], 1e-300))
    return {"alpha_daily": float(beta[0]), "alpha_annualised": float(beta[0] * DAYS_PER_YEAR), "beta": float(beta[1]),
            "t_alpha_hac": float(beta[0] / se_a), "p_alpha_one_sided": float(1.0 - l1.N.cdf(beta[0] / se_a))}  # fmt: skip


def risk_matched_returns(
    strategy_daily: np.ndarray, btc_daily: np.ndarray
) -> tuple[np.ndarray, float]:
    """Ex-post, non-tradable comparator: w x BTC + (1-w) x cash with w = (sd of the strategy) / (sd of BTC), capped at 1."""
    w = min(1.0, float(strategy_daily.std(ddof=1) / max(btc_daily.std(ddof=1), 1e-12)))
    return w * btc_daily, w


# ------------------------------------------------------------------------------------------ decision
def decide_config(spec: dict, per_config: dict) -> dict:
    """Pre-registered per-configuration decision (all criteria must hold)."""
    cr = spec["criteria"]
    out: dict = {}
    for cid, c in per_config.items():
        m_n, m_d = c["normal"]["metrics"], c["double"]["metrics"]
        cond = {
            "A1_net_return_positive_normal_costs": m_n["net_return"] > cr["min_net_return"],
            "A1_net_return_positive_double_costs": m_d["net_return"] > cr["min_net_return"],
            "A2_sortino_at_least_btc_buy_hold": m_n["sortino"]
            >= c["benchmarks"]["btc_buy_hold"]["sortino"],
            "A2_sortino_at_least_equal_weight": m_n["sortino"]
            >= c["benchmarks"]["equal_weight"]["sortino"],
            "A3_max_drawdown_within_limit": m_n["max_drawdown"] <= cr["max_drawdown"],
            "A3_max_drawdown_not_above_btc": m_n["max_drawdown"]
            <= c["benchmarks"]["btc_buy_hold"]["max_drawdown"],
            "A4_no_v3_shutdown": not c["normal"]["capital_protection"]["shutdown"],
            "A5_incremental_value_vs_low_volatility": c["incremental_vs_low_volatility"][
                "p_one_sided"
            ]
            <= cr["alpha_incremental"],
            "A6_fill_ratio": c["normal"]["execution"]["fill_ratio"] >= cr["min_fill_ratio"],
        }
        out[cid] = {"criteria": cond, "passes": all(cond.values()),
                    "failed": sorted(k for k, v in cond.items() if not v),
                    "decision": "L2 PASS" if all(cond.values()) else "NO-GO"}  # fmt: skip
    return out
