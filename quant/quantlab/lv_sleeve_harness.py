"""M6-S0 minimal SYNTHETIC test harness for the proposed capped, volatility-targeted sleeve (NOT a strategy).

It reuses the frozen engine (``execution.run``) and the unchanged Risk Management V3. Fixtures, predictions, claims and
rules are read from ``protocol/m6_s0_fixtures_freeze.json`` (frozen before the first run). No market data is read."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from quantlab.costs import BASE, STRESS
from quantlab.execution import ExecConfig, History, Order, PortfolioView, PriceData, Strategy, run
from quantlab.risk_v2 import RiskStateMachine
from quantlab.risk_v3 import RiskManagedStrategyV3, RiskV3Config, ScheduleFeed, Status


Q = Path(__file__).resolve().parents[1]
FREEZE = Q / "protocol" / "m6_s0_fixtures_freeze.json"
CORRECTIONS = Q / "protocol" / "m6_s0_defect_corrections.json"
RESULTS = Q / "docs" / "phase4c" / "m6_s0_results.json"
PAIRS = [f"L{i:02d}/USDT" for i in range(10)]
H1 = pd.Timedelta(hours=1)


def load_freeze() -> dict:
    return json.loads(FREEZE.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------ estimator
def basket_vol(hist: History, pairs: list[str], window_days: int) -> float:
    """Causal annualised volatility of the equal-weight basket from daily closes sampled every 24 candles back
    from the last completed candle. NaN if history is short or any asset has a missing close (fail closed)."""
    need = (window_days + 1) * 24
    cols = []
    for p in pairs:
        c = hist.closes(p, need)
        if len(c) < need or not np.all(np.isfinite(c)):
            return float("nan")
        cols.append(c[::-1][::24][::-1][: window_days + 1])
    px = np.array(cols)  # assets x (window+1)
    rets = px[:, 1:] / px[:, :-1] - 1.0
    return float(np.std(rets.mean(axis=0), ddof=1) * math.sqrt(365.0))


def target_exposure(mode: str, sigma_hat: float, e_max: float, sigma_star: float) -> float:
    if not math.isfinite(sigma_hat) or sigma_hat < 0:
        return 0.0  # missing / invalid estimate: no exposure
    if mode == "LV-2":
        return e_max
    if sigma_hat == 0.0:
        return e_max  # zero volatility: the cap binds, no division
    return min(e_max, sigma_star / sigma_hat)


class SleeveInner(Strategy):
    """Weekly (Monday 01:00 UTC) resizing of a FIXED equal-weight basket to the target exposure; nothing in between."""

    def __init__(self, mode: str, sleeve: dict, pairs: list[str] | None = None):
        self.mode, self.s, self.pairs = mode, sleeve, pairs or PAIRS
        self.targets: list[dict] = []

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        if t.day_of_week != 0 or t.hour != 1:
            return []
        s = self.s
        sig = basket_vol(hist, self.pairs, s["vol_window_days"])
        e = target_exposure(self.mode, sig, s["e_max"], s["sigma_star"])
        per = e * view.equity / len(self.pairs)
        self.targets.append({"t": str(t), "sigma_hat": sig, "E": e, "equity": view.equity})
        out: list[Order] = []
        for p in self.pairs:
            v = view.positions.get(p, (0.0, 0.0))[1]
            if per - v >= 5.0:
                out.append(Order(p, "buy", notional=per - v, add=True, reason="sleeve"))
            elif v - per >= 5.0 and v > 0:
                out.append(Order(p, "sell", fraction=1.0 - per / v, reason="sleeve"))
        return out


# ------------------------------------------------------------------------------------ fixtures
def build_feed(fx: dict, common: dict) -> PriceData:
    n = int(fx["days"]) * 24
    idx = pd.date_range(common["start"], periods=n, freq="1h", tz="UTC")
    f_sd = fx.get("f_sd", common["f_sd"])
    vol = fx.get("volume", common["volume"])
    ev = fx["events"]
    mult = np.ones(n)  # cumulative gap factor from candle k on
    gap = np.ones(n)  # factor applied at the open of candle k
    drift = np.zeros(n)
    for e in ev:
        if e["kind"] == "gap":
            k = e["day"] * 24 + e["hour"]
            gap[k] *= e["factor"]
            mult[k:] *= e["factor"]
        elif e["kind"] == "drift":
            a, b = e["from_day"] * 24, e["to_day"] * 24
            drift[a:b] += e["daily_log_drift"] / 24.0
    rng_f = np.random.default_rng([common["seed"], 0])
    f = rng_f.normal(0.0, f_sd, n)
    out = {}
    for k, p in enumerate(PAIRS):
        r = np.random.default_rng([common["seed"], 1 + k]).normal(0.0, 0.002, n) + f + drift
        c = 100.0 * np.exp(np.cumsum(r)) * mult
        o = np.concatenate([[100.0], c[:-1]]) * gap
        df = pd.DataFrame({"date": idx, "open": o, "high": np.maximum(o, c), "low": np.minimum(o, c),
                           "close": c, "volume": vol})  # fmt: skip
        drop = np.zeros(n, dtype=bool)
        for e in ev:
            if e.get("pair") != k:
                continue
            if e["kind"] == "missing":
                drop[e["from_hour"] : e["to_hour"]] = True
            elif e["kind"] == "delist":
                drop[e["from_hour"] :] = True
        out[p] = df[~drop]
    return PriceData(out, idx)


def run_fixture(fx: dict, mode: str, freeze: dict) -> dict:
    common = freeze["common"]
    d = build_feed(fx, common)
    cfg = RiskV3Config()
    m = RiskStateMachine.new(cfg.v2, common["wallet"])
    feed = None
    sf = fx.get("status_feed")
    if sf:
        t0 = pd.Timestamp(common["start"]) + sf["from_hour"] * H1
        feed = ScheduleFeed({PAIRS[sf["pair"]]: [(t0, Status[sf["status"]])]})
    inner = SleeveInner(mode, common["sleeve"])
    strat = RiskManagedStrategyV3(inner, m, cfg, feed)
    ex = ExecConfig(wallet=common["wallet"], costs=STRESS if fx.get("costs") == "STRESS" else BASE,
                    max_participation=fx.get("max_participation"))  # fmt: skip
    res = run(strat, d, ex)
    eq = res.equity.astype(float)
    hwm = eq.cummax()
    dd = float((1.0 - eq / hwm).max())
    sleeve_t = [x for x in inner.targets if x["E"] > 0]
    gap_days = sorted({e["day"] for e in fx["events"] if e["kind"] == "gap" and e["factor"] < 1.0})
    # single-event equity loss: equity just before the gap candle to the lowest equity within 3 days after it
    single = 0.0
    for e in fx["events"]:
        if e["kind"] == "gap" and e["factor"] < 1.0:
            k = e["day"] * 24 + e["hour"]
            before = float(eq.iloc[max(k - 1, 0)])
            after = float(eq.iloc[k : k + 72].min())
            single = max(single, 1.0 - after / before)
    recs = [
        {"t": str(r["t"]), "from": r.get("from"), "to": r["to"], "cause": r.get("cause")}
        for r in m.records
    ]
    shut = next((r for r in recs if r["to"] == "SHUTDOWN"), None)
    exposure = res.exposure if res.exposure is not None else pd.Series(dtype=float)
    # buys filled while V3 was FLAT_COOLDOWN or SHUTDOWN (claim C5): compare fill times with the state windows
    windows, cur = [], None
    for r in recs:
        if r["to"] in ("FLAT_COOLDOWN", "SHUTDOWN") and cur is None:
            cur = [r["t"], None]
        elif cur is not None and r["to"] not in ("FLAT_COOLDOWN", "SHUTDOWN"):
            cur[1] = r["t"]
            windows.append(tuple(cur))
            cur = None
    if cur is not None:
        windows.append((cur[0], None))
    buys_blocked = 0
    for o in res.orders:
        if o.get("side") == "buy":
            ts = o["time"]
            if any(a <= ts and (b is None or ts < b) for a, b in windows):
                buys_blocked += 1
    port_vol = None
    if len(eq) > 24 * 70:
        dly = eq.iloc[::24].pct_change().dropna()
        port_vol = float(dly.iloc[-60:].std(ddof=1) * math.sqrt(365.0))
    return {
        "fixture": fx["id"], "config": mode, "order_hash": res.hash, "n_orders": len(res.orders),
        "final_equity": float(eq.iloc[-1]), "min_equity": float(eq.min()), "max_drawdown_from_hwm": dd,
        "min_equity_over_hwm": float((eq / hwm).min()), "max_single_event_loss": single,
        "max_realized_exposure": float(exposure.max()) if len(exposure) else None,
        "mean_realized_exposure": float(exposure.mean()) if len(exposure) else None,
        "mean_target_E": float(np.mean([x["E"] for x in inner.targets])) if inner.targets else None,
        "max_target_E": float(max(x["E"] for x in inner.targets)) if inner.targets else None,
        "n_rebalances_with_exposure": len(sleeve_t),
        "mean_sigma_hat": float(np.nanmean([x["sigma_hat"] for x in inner.targets])) if inner.targets else None,
        "realised_portfolio_vol_last60d": port_vol, "gap_days": gap_days,
        "transitions": recs, "shutdown": shut, "buys_filled_in_flat_or_shutdown": buys_blocked,
        "suppressed_signals": len(strat.suppressed), "n_rejects": len(res.rejects),
        "engine_breaker_events": len([b for b in res.breaker_events if b.get("type") == "halt"]),
        "writeoffs": list(strat.writeoffs), "equity_series_hash": int(pd.util.hash_pandas_object(eq).sum() % (2**63)),
    }  # fmt: skip


def evaluate_claims(rows: list[dict], freeze: dict) -> dict:
    out = {}
    out["C1"] = {"claim": freeze["claims_under_test"]["C1"],
                 "falsified_by": sorted({f'{r["fixture"]}|{r["config"]}' for r in rows if r["shutdown"]})}  # fmt: skip
    out["C2"] = {"claim": freeze["claims_under_test"]["C2"],
                 "falsified_by": sorted({f'{r["fixture"]}|{r["config"]}' for r in rows
                                         if (r["max_realized_exposure"] or 0) > 0.1575})}  # fmt: skip
    out["C3"] = {"claim": freeze["claims_under_test"]["C3"],
                 "falsified_by": sorted({f'{r["fixture"]}|{r["config"]}' for r in rows if r["max_single_event_loss"] > 0.15})}  # fmt: skip
    out["C4"] = {"claim": freeze["claims_under_test"]["C4"],
                 "falsified_by": sorted({f'{r["fixture"]}|{r["config"]}' for r in rows if r["min_equity_over_hwm"] < 0.82})}  # fmt: skip
    out["C5"] = {"claim": freeze["claims_under_test"]["C5"],
                 "falsified_by": sorted({f'{r["fixture"]}|{r["config"]}' for r in rows if r["buys_filled_in_flat_or_shutdown"] > 0})}  # fmt: skip
    for v in out.values():
        v["status"] = "FALSIFIED" if v["falsified_by"] else "not falsified by the frozen fixtures"
    return out


def run_all() -> dict:
    fr = load_freeze()
    extra = json.loads(CORRECTIONS.read_text(encoding="utf-8"))["replacement_fixtures"]
    rows = []
    for fx in [*fr["fixtures"], *extra]:
        for mode in ("LV-1", "LV-2"):
            for _ in range(int(fx.get("repeat", 1))):
                rows.append(run_fixture(fx, mode, fr))
    return {"freeze": "protocol/m6_s0_fixtures_freeze.json", "synthetic_only": True, "runs": rows,
            "claims": evaluate_claims(rows, fr)}  # fmt: skip


def main() -> None:
    RESULTS.write_text(
        json.dumps(run_all(), indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print("wrote", RESULTS)


if __name__ == "__main__":
    main()
