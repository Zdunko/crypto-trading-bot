"""Risk layer V3 (version 3.0.0): stale / untradeable asset handling on top of the FROZEN S2 layer.

Why it exists (S6 finding L-STALEPOS): S2 counts candles (data_gap_candles = 48 means 48 DAYS on daily
data), the engine values a position without candles at its last close, so equity, drawdown tiers and
floors never see the loss of a delisted holding. V3 keeps every S2 parameter and the whole S2 state machine
and changes only what is FED to it and when:

* **elapsed-time semantics**: a held asset without a completed candle for >= ``stale_horizon`` (48 h, the
  S2 intent) is STALE regardless of candle size; the monitoring clock is fixed at 1 hour and any other
  cadence is refused (fail closed). A strategy may decide daily; risk is evaluated hourly.
* **explicit statuses**: SUSPENDED / DELISTED / UNTRADEABLE (from an explicit feed) and MISSING (never a
  candle) are impaired immediately, silent assets after the horizon.
* **three valuations**: last-known (engine), conservative risk valuation (impaired positions at
  ``gate_recovery`` x last-known, default 0 = zero recovery; this value drives the S2 machine) and realized
  (closed trades plus explicit write-offs). Liquidation is never assumed: impaired positions stay in the
  exposure the machine sees.
* S2 behaviour is preserved: with no impaired asset V3 is identical to the V2 wrapper.
No network, no market data. ``risk_v2.py`` is not modified.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path

import numpy as np
import pandas as pd

from quantlab.execution import History, Order, PortfolioView
from quantlab.risk_v2 import FLAT, SHUTDOWN, RiskManagedStrategy, RiskStateMachine, RiskV2Config


VERSION = "3.0.0"
_H48 = pd.Timedelta(hours=48)
_H1 = pd.Timedelta(hours=1)
_ZERO = pd.Timedelta(0)


class ConfigError(Exception):
    """Refusal to run with a configuration or cadence the V3 guarantees do not cover."""


class Status(StrEnum):
    TRADABLE = "tradable"
    GAP = "gap"  # silent for less than the horizon: valued at last known, watched
    STALE = "stale"  # silent for >= horizon
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    UNTRADEABLE = "untradeable"
    MISSING = "missing"  # held, but no candle exists in the history at all


IMPAIRED = frozenset(
    {Status.STALE, Status.SUSPENDED, Status.DELISTED, Status.UNTRADEABLE, Status.MISSING}
)
StatusFeed = Callable[[str, pd.Timestamp], "Status | None"]


@dataclass(frozen=True)
class RiskV3Config:
    v2: RiskV2Config = field(default_factory=RiskV2Config)
    stale_horizon: pd.Timedelta = _H48
    monitor_interval: pd.Timedelta = _H1
    gate_recovery: float = 0.0
    sensitivity_recoveries: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)

    def __post_init__(self) -> None:
        if not (0.0 <= self.gate_recovery <= 1.0):
            raise ConfigError("gate_recovery must be in [0, 1]")
        if self.stale_horizon <= pd.Timedelta(0) or self.monitor_interval <= pd.Timedelta(0):
            raise ConfigError("horizon and monitor interval must be positive")

    def sha256(self) -> str:
        d = {"version": VERSION, "v2": asdict(self.v2), "stale_horizon_h": self.stale_horizon / pd.Timedelta(hours=1),
             "monitor_interval_h": self.monitor_interval / pd.Timedelta(hours=1), "gate_recovery": self.gate_recovery,
             "sensitivity_recoveries": list(self.sensitivity_recoveries)}  # fmt: skip
        return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


class StaleTracker:
    """Elapsed time since the end of the last completed candle of each held pair (O(1) per tick)."""

    def __init__(self) -> None:
        self.last_seen: dict[str, pd.Timestamp | None] = {}

    def update(self, pair: str, hist: History, step: pd.Timedelta) -> None:
        if pair not in self.last_seen:
            self.last_seen[pair] = self._scan(pair, hist, step)
            return
        c = hist.closes(pair, 1)
        if len(c) and not math.isnan(c[-1]):
            self.last_seen[pair] = hist.times[-1] + step

    @staticmethod
    def _scan(pair: str, hist: History, step: pd.Timedelta) -> pd.Timestamp | None:
        c = hist.closes(pair)
        ok = np.flatnonzero(~np.isnan(c))
        return None if len(ok) == 0 else hist.times[int(ok[-1])] + step

    def elapsed(self, pair: str, t: pd.Timestamp) -> pd.Timedelta | None:
        seen = self.last_seen.get(pair)
        return None if seen is None else t - seen

    @classmethod
    def from_history(cls, pairs: list[str], hist: History, step: pd.Timedelta) -> StaleTracker:
        tr = cls()
        for p in pairs:
            tr.last_seen[p] = cls._scan(p, hist, step)
        return tr


class ScheduleFeed:
    """Explicit status events: {pair: [(from_time, Status), ...]}; the latest event at or before t applies."""

    def __init__(self, events: dict[str, list[tuple[pd.Timestamp, Status]]]):
        self.events = {p: sorted(e, key=lambda x: x[0]) for p, e in events.items()}

    def __call__(self, pair: str, t: pd.Timestamp) -> Status | None:
        cur = None
        for ts, st in self.events.get(pair, []):
            if ts <= t:
                cur = st
        return cur


class RiskManagedStrategyV3(RiskManagedStrategy):
    """V2 order logic fed with conservative valuation, elapsed-time stale detection and a separate decision clock."""

    def __init__(self, inner, machine: RiskStateMachine, cfg: RiskV3Config | None = None,
                 status_feed: StatusFeed | None = None, decision_every: pd.Timedelta | None = None,
                 decision_offset: pd.Timedelta = _ZERO, approval_path: str | Path | None = None):  # fmt: skip
        super().__init__(inner, machine, approval_path)
        self.cfg = cfg or RiskV3Config()
        if machine.cfg != self.cfg.v2:
            raise ConfigError(
                "the state machine must use the V3 config's (unchanged) S2 parameters"
            )
        self.feed, self.decision_every, self.decision_offset = (
            status_feed,
            decision_every,
            decision_offset,
        )
        self.tracker = StaleTracker()
        self.ticks: list[dict] = []
        self.writeoffs: dict[str, dict] = {}
        self.unliquidatable: set[str] = set()
        self._step: pd.Timedelta | None = None

    # ---- clocks
    def _check_cadence(self, hist: History) -> pd.Timedelta | None:
        if len(hist.times) < 2:
            return self._step
        step = hist.times[-1] - hist.times[-2]
        if step != self.cfg.monitor_interval:
            raise ConfigError(
                f"risk monitoring needs {self.cfg.monitor_interval} candles, got {step}: run V3 on hourly data"
            )
        self._step = step
        return step

    def _is_decision(self, t: pd.Timestamp) -> bool:
        if self.decision_every is None:
            return True
        return (t - pd.Timestamp(0, tz="UTC")) % self.decision_every == self.decision_offset

    # ---- statuses and valuation
    def classify(self, pair: str, t: pd.Timestamp) -> Status:
        if self.feed is not None:
            s = self.feed(pair, t)
            if s in (Status.SUSPENDED, Status.DELISTED, Status.UNTRADEABLE):
                return s
        el = self.tracker.elapsed(pair, t)
        if el is None:
            return Status.MISSING
        if el >= self.cfg.stale_horizon:
            return Status.STALE
        return Status.GAP if el > pd.Timedelta(0) else Status.TRADABLE

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        step = self._check_cadence(hist)
        held = sorted(view.positions)
        statuses: dict[str, Status] = {}
        for p in held:
            if step is not None:
                self.tracker.update(p, hist, step)
            statuses[p] = self.classify(p, t) if step is not None else Status.TRADABLE
        impaired = [p for p in held if statuses[p] in IMPAIRED]
        lk_equity = view.equity
        impaired_lk = float(sum(view.positions[p][1] for p in impaired))
        cons_equity = lk_equity - impaired_lk * (1.0 - self.cfg.gate_recovery)
        gross = float(
            sum(v for _, v in view.positions.values())
        )  # impaired exposure stays: never assumed gone
        self.unliquidatable = set(impaired)
        for p in impaired:
            if statuses[p] == Status.DELISTED and p not in self.writeoffs:
                v = float(view.positions[p][1])
                self.writeoffs[p] = {"t": str(t), "last_known": v, "recovery": self.cfg.gate_recovery,
                                     "realized_loss": v * (1.0 - self.cfg.gate_recovery)}  # fmt: skip
        vc = replace(view, equity=cons_equity)
        if (
            self.m.s.state == SHUTDOWN
            and self.approval_path is not None
            and Path(self.approval_path).exists()
        ):
            self.m.authorize(t, cons_equity, gross, self.approval_path)
        dec = self.m.step(t, cons_equity, gross, bool(impaired))
        self.ticks.append({"t": t, "lk": lk_equity, "cons": cons_equity, "impaired_lk": impaired_lk,
                           "impaired": impaired, "state": dec.state})  # fmt: skip
        out: list[Order] = []
        if dec.transition is not None and dec.flatten:
            out = [Order(p, "sell", priority=-1, reason="halt") for p in held]
        decide = self._is_decision(t)
        if dec.state in (FLAT, SHUTDOWN):
            if decide:
                for o in self.inner.on_candle(
                    t, hist, replace(vc, risk_multiplier=1.0, halted=False)
                ):
                    self.suppressed.append(
                        {"t": str(t), "pair": o.pair, "side": o.side, "why": dec.state}
                    )
            return out
        proposed = (
            self.inner.on_candle(t, hist, replace(vc, risk_multiplier=dec.cap, halted=False))
            if decide
            else []
        )
        return out + self._enforce(t, vc, gross, proposed, dec)

    # ---- reporting
    def realized_losses(self, trades: pd.DataFrame | None = None) -> dict:
        closed = float(trades["profit_abs"].sum()) if trades is not None and len(trades) else 0.0
        wo = float(sum(w["realized_loss"] for w in self.writeoffs.values()))
        return {
            "closed_trades_pnl": closed,
            "write_offs": wo,
            "write_off_detail": dict(self.writeoffs),
        }


# ---------------------------------------------------------------------------- analysis (pure)
def _max_dd(eq: np.ndarray) -> float:
    peak = np.maximum.accumulate(eq)
    return float(np.max((peak - eq) / np.where(peak > 0, peak, 1.0))) if len(eq) else 0.0


def recovery_sensitivity(ticks: list[dict], cfg: RiskV3Config | None = None) -> dict:
    """What the realised path's drawdown would be if impaired positions recovered a fraction r of their last-known
    value (r = 0 zero recovery, r = 1 the engine's own view). Analysis only: it does not feed the machine."""
    cfg = cfg or RiskV3Config()
    lk = np.array([x["lk"] for x in ticks], dtype=float)
    imp = np.array([x["impaired_lk"] for x in ticks], dtype=float)
    out = {}
    for r in cfg.sensitivity_recoveries:
        eq = lk - imp * (1.0 - r)
        dd = _max_dd(eq)
        out[str(r)] = {"max_drawdown": dd, "final_equity": float(eq[-1]),
                       "trips": {"tier1": dd >= cfg.v2.tier1_dd, "tier2": dd >= cfg.v2.tier2_dd,
                                 "tier3": dd >= cfg.v2.tier3_dd, "t4_limit_exceeded": dd > 0.20}}  # fmt: skip
    return out


def capital_protection_report(ticks: list[dict], limit: float = 0.20) -> dict:
    """Last-known versus conservative drawdown against the (unchanged) 20 % limit. ``concealed`` means the engine's
    own equity passes while the conservative valuation does not: the stale valuation hides the breach."""
    lk = np.array([x["lk"] for x in ticks], dtype=float)
    cons = np.array([x["cons"] for x in ticks], dtype=float)
    d_lk, d_cons = _max_dd(lk), _max_dd(cons)
    return {"max_drawdown_last_known": d_lk, "max_drawdown_conservative": d_cons, "limit": limit,
            "last_known_view_passes": d_lk <= limit, "conservative_view_passes": d_cons <= limit,
            "concealed_by_stale_valuation": d_lk <= limit < d_cons, "verdict_pass": d_cons <= limit}  # fmt: skip
