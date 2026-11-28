"""
Risk layer V2 (L4): deterministic, persistent, fail-closed state machine plus an order-level wrapper.

Specification: ``protocol/protocol_v6_risk_v2.json`` and ``docs/phase4c/s2_risk_v2_specification.md``.
All numeric parameters are PROVISIONAL engineering assumptions (not validated optima, never tuned on
market data). Nothing here is a guaranteed loss limit: gaps and missing liquidity can breach every
floor; breaches are measured and reported as overshoot.

Definitions (E = mark-to-market liquidation equity at the previous close):
    H      all-time high-water mark, max of E ever seen, NEVER reset (not by recovery, restart or approval)
    P      epoch-local peak (P = H in epoch 0; P = E at an authorised restart, then its running maximum)
    d_G    = 1 - E/H        global drawdown   (feeds floors / disqualification)
    d_L    = 1 - E/P        local drawdown    (feeds tiers 1 and 2 and re-entry failure)
    F      floor: epoch 0:  H*(1 - tier3_dd)
                  epoch k:  max(E_auth*(1 - loss_limit_k), H*(1 - hard_dd))
    R      remaining risk budget = max(0, E - F)
    phi    = stress_gap + exit_cost         loss per unit of exposure under a stress gap plus liquidation cost
    X_open gross value of positions still held (including positions queued for liquidation)
    cap    budget: if phi*X_open <= R : X_open + (R - phi*X_open)/(phi + entry_cost)  else R/phi
Transitions are evaluated in a fixed precedence and at most one per candle; see :meth:`RiskStateMachine.step`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import pandas as pd

from quantlab.execution import History, Order, PortfolioView, Strategy


NORMAL, REDUCED, FLAT, REENTRY, SHUTDOWN = (
    "NORMAL",
    "REDUCED",
    "FLAT_COOLDOWN",
    "REENTRY",
    "SHUTDOWN",
)
STATES = (NORMAL, REDUCED, FLAT, REENTRY, SHUTDOWN)


class StateError(Exception):
    """Persisted state is missing, unreadable, inconsistent or tampered with."""


@dataclass(frozen=True)
class RiskV2Config:
    tier1_dd: float = 0.10
    tier1_exit_dd: float = 0.05
    tier1_cap: float = 0.5  # absolute gross-exposure cap (share of equity) while REDUCED
    tier2_dd: float = 0.15
    tier3_dd: float = 0.18
    hard_dd: float = 0.25  # absolute global limit; no authorisation can re-risk above it
    cooldown_hours: int = 14 * 24
    step_hours: int = 7 * 24
    steps: tuple[float, ...] = (0.25, 0.5, 1.0)
    reentry_fail_loss: float = 0.03
    max_failed_reentries: int = 2
    max_flat_cycles: int = 3
    stress_gap: float = 0.30
    entry_cost: float = 0.0015
    exit_cost: float = 0.0015
    liquidity_alarm_candles: int = 24
    data_gap_candles: int = 48
    approval_max_age_hours: int = 168
    epoch_loss_cap: float = 0.05
    flat_tolerance: float = 1e-9


@dataclass
class RiskState:
    state: str = NORMAL
    hwm: float = 0.0
    peak: float = 0.0
    epoch: int = 0
    epoch_floor_abs: float | None = None
    approved_cap: float | None = None
    cooldown_end: str | None = None
    step: int = 0
    step_start: str | None = None
    reentry_start_equity: float | None = None
    failed_reentries: int = 0
    flat_cycles: int = 0
    flatten_started: str | None = None
    candles_since_flatten: int = 0
    shutdown_id: str | None = None
    shutdown_cause: str | None = None
    shutdown_time: str | None = None
    safety_disqualified: bool = False
    safety_events: list = field(default_factory=list)
    consumed_approvals: list = field(default_factory=list)
    seq: int = 0
    last_t: str | None = None
    candles_in_state: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    state: str
    cap: float  # absolute gross exposure cap, share of equity
    flatten: bool  # liquidate everything now
    transition: dict | None


def risk_budget(equity: float, floor: float, x_open: float, cfg: RiskV2Config) -> dict:
    """Remaining risk budget and the largest gross exposure it allows (module docstring)."""
    phi = cfg.stress_gap + cfg.exit_cost
    r = max(0.0, equity - floor)
    if phi * x_open <= r:
        allowed = x_open + (r - phi * x_open) / (phi + cfg.entry_cost)
    else:
        allowed = r / phi
    cap = allowed / equity if equity > 0 else 0.0
    return {"R": r, "phi": phi, "allowed_total": allowed, "cap": min(max(cap, 0.0), 1.0)}


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class StateStore:
    """Atomic single-file store: transition records (hash-chained) plus the latest state, one hash over both."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, state: RiskState, records: list[dict]) -> str:
        body = {"records": records, "state": asdict(state)}
        head = _digest(_canon(body))
        tmp = self.path.with_name(self.path.name + ".tmp")
        data = json.dumps({"body": body, "head": head}, sort_keys=True)
        with tmp.open("w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)  # noqa: PTH105 - a crash before this line leaves the previous file intact
        return head

    def load(self, expected_head: str | None = None) -> tuple[RiskState, list[dict], str]:
        tmp = self.path.with_name(self.path.name + ".tmp")
        if tmp.exists():
            tmp.unlink()  # an interrupted write: the previous, complete file is authoritative
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            body, head = raw["body"], raw["head"]
            state = RiskState(**body["state"])
            records = list(body["records"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise StateError(f"state file unreadable or malformed: {exc}") from exc
        if _digest(_canon(body)) != head:
            raise StateError("state hash mismatch (file modified outside the risk layer)")
        prev = "genesis"
        for rec in records:
            core = {k: v for k, v in rec.items() if k != "hash"}
            if rec.get("prev") != prev or _digest(prev, _canon(core)) != rec.get("hash"):
                raise StateError("transition record chain broken")
            prev = rec["hash"]
        if expected_head is not None and head != expected_head:
            raise StateError(
                "state head does not match the external anchor (rollback or substitution)"
            )
        return state, records, head


class RiskStateMachine:
    def __init__(self, cfg: RiskV2Config, state: RiskState, records: list[dict] | None = None,
                 store: StateStore | None = None):  # fmt: skip
        self.cfg, self.s, self.records, self.store = cfg, state, records or [], store
        self.head: str | None = None
        self._last: Decision | None = None

    # ------------------------------------------------------------------ construction
    @classmethod
    def new(cls, cfg: RiskV2Config, initial_equity: float, store: StateStore | None = None,
            overwrite: bool = False) -> RiskStateMachine:  # fmt: skip
        if store is not None and store.path.exists() and not overwrite:
            raise StateError(
                "state file already exists: refusing to start a new run over it (HWM would be lost)"
            )
        m = cls(cfg, RiskState(hwm=initial_equity, peak=initial_equity), [], store)
        m._persist()
        return m

    @classmethod
    def resume(
        cls, cfg: RiskV2Config, store: StateStore, expected_head: str | None = None
    ) -> RiskStateMachine:
        """Restart after a process stop. Any problem with the file means SHUTDOWN (fail closed)."""
        try:
            state, records, head = store.load(expected_head)
        except StateError as exc:
            m = cls(cfg, RiskState(state=SHUTDOWN, shutdown_cause="state_integrity", safety_disqualified=True,
                                   shutdown_id="shutdown-state-integrity",
                                   safety_events=[{"cause": "state_integrity", "detail": str(exc)}]), [], None)  # fmt: skip
            m.store_error = str(exc)
            return m
        m = cls(cfg, state, records, store)
        m.head = head
        return m

    store_error: str | None = None

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _breached(equity: float, peak: float, dd: float) -> bool:
        """Drawdown >= dd, written on equity so that exact boundaries are not lost to float rounding."""
        return equity <= peak * (1.0 - dd) * (1.0 + 1e-12)

    def floor(self) -> float:
        s, c = self.s, self.cfg
        if s.epoch_floor_abs is None:
            return s.hwm * (1.0 - c.tier3_dd)
        return max(s.epoch_floor_abs, s.hwm * (1.0 - c.hard_dd))

    def _persist(self) -> None:
        if self.store is not None:
            self.head = self.store.save(self.s, self.records)

    def _log(self, t, frm, to, cause, equity, conds) -> dict:
        s = self.s
        prev = self.records[-1]["hash"] if self.records else "genesis"
        core = {"seq": len(self.records) + 1, "t": str(t), "from": frm, "to": to, "cause": cause,
                "equity": equity, "hwm": s.hwm, "d_global": 1 - equity / s.hwm if s.hwm > 0 else None,
                "conditions": sorted(conds), "prev": prev}  # fmt: skip
        rec = {**core, "hash": _digest(prev, _canon(core))}
        self.records.append(rec)
        return rec

    def _to_shutdown(self, t, equity, cause, conds) -> dict:
        s = self.s
        frm = s.state
        s.state, s.shutdown_cause, s.shutdown_time = SHUTDOWN, cause, str(t)
        s.shutdown_id = (
            f"shutdown-{pd.Timestamp(t).strftime('%Y%m%dT%H%M')}-{len(self.records) + 1}"
        )
        s.safety_disqualified = True  # permanent: no later event clears it
        s.safety_events.append({"t": str(t), "cause": cause, "equity": equity, "id": s.shutdown_id})
        s.flatten_started = s.flatten_started or str(t)
        return self._log(t, frm, SHUTDOWN, cause, equity, conds)

    # ------------------------------------------------------------------ one candle
    def step(self, t, equity: float, gross: float, integrity_alarm: bool = False) -> Decision:
        """Advance the machine by one candle. ``equity`` and ``gross`` are previous-close values."""
        s, c = self.s, self.cfg
        t = pd.Timestamp(t)
        if s.last_t is not None:
            last = pd.Timestamp(s.last_t)
            if t == last and self._last is not None:
                return self._last  # idempotent replay of the same candle
            if t < last:
                integrity_alarm = True  # clock regression
        s.last_t = str(t)
        bad_equity = not math.isfinite(equity) or equity <= 0
        if bad_equity:
            integrity_alarm = True
        else:
            s.hwm = max(s.hwm, equity)  # never lowered, never reset
            s.peak = max(s.peak, equity)
        s.candles_in_state[s.state] = s.candles_in_state.get(s.state, 0) + 1
        positions_open = gross > c.flat_tolerance
        d_l = 1 - equity / s.peak if (s.peak > 0 and not bad_equity) else 1.0
        # all conditions that hold on this candle (audit trail of simultaneous triggers)
        conds = set()
        if integrity_alarm:
            conds.add("integrity")
        if s.state != SHUTDOWN and (bad_equity or equity <= self.floor() * (1.0 + 1e-12)):
            conds.add("floor")
        if s.state == FLAT and positions_open:
            s.candles_since_flatten += 1
            if s.candles_since_flatten >= c.liquidity_alarm_candles:
                conds.add("liquidity")
        if s.state in (NORMAL, REDUCED) and not bad_equity:
            if self._breached(equity, s.peak, c.tier2_dd):
                conds.add("tier2")
            elif self._breached(equity, s.peak, c.tier1_dd):
                conds.add("tier1")
        transition = None
        flatten = False
        if s.state == SHUTDOWN:
            flatten = positions_open
        elif "integrity" in conds:
            transition, flatten = self._to_shutdown(t, equity, "integrity", conds), True
        elif "floor" in conds:
            cause = "tier3_floor" if s.epoch == 0 else "epoch_floor"
            transition, flatten = self._to_shutdown(t, equity, cause, conds), True
        elif "liquidity" in conds:
            transition, flatten = (
                self._to_shutdown(t, equity, "liquidation_unavailable", conds),
                True,
            )
        else:
            transition, flatten = self._tiers(t, equity, d_l, positions_open, conds)
        cap = self._cap(equity, gross)
        self._last = Decision(
            s.state, cap, flatten or (s.state in (FLAT, SHUTDOWN) and positions_open), transition
        )
        s.seq += 1
        self._persist()
        return self._last

    def _enter_flat(self, t, equity, cause, conds) -> tuple[dict, bool]:
        s, c = self.s, self.cfg
        frm = s.state
        s.flat_cycles += 1
        if s.flat_cycles > c.max_flat_cycles:
            return self._to_shutdown(t, equity, "flat_cycles", conds), True
        s.state, s.cooldown_end = FLAT, str(pd.Timestamp(t) + pd.Timedelta(hours=c.cooldown_hours))
        s.flatten_started, s.candles_since_flatten = str(t), 0
        s.step, s.step_start, s.reentry_start_equity = 0, None, None
        return self._log(t, frm, FLAT, cause, equity, conds), True

    def _tiers(self, t, equity, d_l, positions_open, conds):
        s, c = self.s, self.cfg
        t = pd.Timestamp(t)
        if s.state == NORMAL:
            if "tier2" in conds:
                return self._enter_flat(t, equity, "tier2", conds)
            if "tier1" in conds:
                s.state = REDUCED
                return self._log(t, NORMAL, REDUCED, "tier1", equity, conds), False
        elif s.state == REDUCED:
            if "tier2" in conds:
                return self._enter_flat(t, equity, "tier2", conds)
            if not self._breached(equity, s.peak, c.tier1_exit_dd):
                s.state = NORMAL
                return self._log(t, REDUCED, NORMAL, "recovered", equity, conds), False
        elif s.state == FLAT:
            if t >= pd.Timestamp(s.cooldown_end) and not positions_open:
                s.state, s.step, s.step_start, s.reentry_start_equity = REENTRY, 0, str(t), equity
                s.flatten_started = None
                return self._log(t, FLAT, REENTRY, "cooldown_elapsed", equity, conds), False
        elif s.state == REENTRY:
            if equity <= s.reentry_start_equity * (1.0 - c.reentry_fail_loss):
                s.failed_reentries += 1
                conds.add("reentry_failed")
                if s.failed_reentries >= c.max_failed_reentries:
                    return self._to_shutdown(t, equity, "reentry_loop", conds), True
                return self._enter_flat(t, equity, "reentry_failed", conds)
            if t >= pd.Timestamp(s.step_start) + pd.Timedelta(hours=c.step_hours):
                if s.step < len(c.steps) - 1:
                    s.step += 1
                    s.step_start = str(t)
                    return self._log(t, REENTRY, REENTRY, f"step_{s.step}", equity, conds), False
                if not self._breached(
                    equity, s.peak, c.tier2_dd
                ):  # held long enough, not in a deep local drawdown
                    s.failed_reentries = 0
                    s.state = REDUCED if self._breached(equity, s.peak, c.tier1_dd) else NORMAL
                    return self._log(t, REENTRY, s.state, "reentry_complete", equity, conds), False
        return None, False

    def _cap(self, equity: float, gross: float) -> float:
        s, c = self.s, self.cfg
        if s.state in (FLAT, SHUTDOWN):
            return 0.0
        cap = {NORMAL: 1.0, REDUCED: c.tier1_cap, REENTRY: c.steps[min(s.step, len(c.steps) - 1)]}[
            s.state
        ]
        if s.state == REENTRY and s.approved_cap is not None:
            cap = min(cap, s.approved_cap)
        if s.state == REENTRY or s.epoch >= 1:
            cap = min(cap, risk_budget(equity, self.floor(), gross, c)["cap"])
        return cap

    # ------------------------------------------------------------------ manual authorisation
    def authorize(
        self, t, equity: float, gross: float, approval: dict | str | Path
    ) -> tuple[bool, str]:
        """Validate an owner approval and, only if every check passes, restart in REENTRY (new epoch)."""
        s, c = self.s, self.cfg
        t = pd.Timestamp(t)
        if s.state != SHUTDOWN:
            return False, "not in SHUTDOWN"
        if s.shutdown_cause == "state_integrity":
            return (
                False,
                "state_integrity shutdown cannot be authorised; start a new run with an explicit HWM",
            )
        try:
            ap = (
                approval
                if isinstance(approval, dict)
                else json.loads(Path(approval).read_text(encoding="utf-8"))
            )
            sid, who, cap = ap["shutdown_id"], ap["approver"], float(ap["exposure_cap"])
            loss, aid = float(ap["epoch_loss_limit"]), ap["approval_id"]
            issued = pd.Timestamp(ap["issued_at"])
        except Exception as exc:
            return False, f"malformed approval: {type(exc).__name__}"
        why = None
        if sid != s.shutdown_id:
            why = "shutdown id mismatch"
        elif not isinstance(who, str) or not who.strip():
            why = "approver missing"
        elif not isinstance(aid, str) or not aid:
            why = "approval id missing"
        elif aid in s.consumed_approvals:
            why = "duplicate approval (already used)"
        elif not (math.isfinite(cap) and 0 < cap <= 1):
            why = "exposure_cap must be in (0, 1]"
        elif not (math.isfinite(loss) and 0 < loss <= c.epoch_loss_cap):
            why = f"epoch_loss_limit must be in (0, {c.epoch_loss_cap}]"
        elif issued.tzinfo is None:
            why = "issued_at needs a timezone"
        elif issued < pd.Timestamp(s.shutdown_time):
            why = "approval older than the shutdown"
        elif issued > t:
            why = "approval issued in the future"
        elif t - issued > pd.Timedelta(hours=c.approval_max_age_hours):
            why = "approval is stale"
        elif not math.isfinite(equity) or equity <= 0:
            why = "equity invalid"
        elif gross > c.flat_tolerance:
            why = "positions still unliquidated"
        elif equity <= s.hwm * (1.0 - c.hard_dd):
            why = "hard drawdown limit reached: no authorisation possible"
        if why:
            return False, why
        s.consumed_approvals.append(aid)
        s.epoch += 1
        s.epoch_floor_abs = equity * (1.0 - loss)
        s.approved_cap, s.peak = cap, equity  # HWM untouched; only the local peak restarts
        s.failed_reentries, s.flat_cycles, s.step = 0, 0, 0
        s.step_start, s.reentry_start_equity, s.cooldown_end = str(t), equity, None
        s.flatten_started, s.candles_since_flatten = None, 0
        s.state = REENTRY
        self._log(t, SHUTDOWN, REENTRY, f"authorised_by:{who.strip()}", equity, {"authorisation"})
        self._last = None
        self._persist()
        return True, "authorised"

    # ------------------------------------------------------------------ reporting
    def report(self) -> dict:
        s = self.s
        return {"state": s.state, "hwm": s.hwm, "epoch": s.epoch, "safety_disqualified": s.safety_disqualified,
                "safety_events": list(s.safety_events), "transitions": list(self.records),
                "candles_in_state": dict(s.candles_in_state), "flat_cycles": s.flat_cycles}  # fmt: skip


class RiskManagedStrategy(Strategy):
    """Order-level L4 wrapper: scales/blocks the inner strategy's orders and liquidates on tier 2 / tier 3."""

    def __init__(
        self, inner: Strategy, machine: RiskStateMachine, approval_path: str | Path | None = None
    ):
        self.inner, self.m, self.approval_path = inner, machine, approval_path
        self.suppressed: list[dict] = []

    def _alarm(self, hist: History, view: PortfolioView) -> bool:
        k = self.m.cfg.data_gap_candles
        for pair in view.positions:
            if len(hist.times) >= k and all(math.isnan(x) for x in hist.closes(pair, k)):
                return True  # a held pair has had no candle for k hours
        return False

    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        gross = sum(v for _, v in view.positions.values())
        if (
            self.m.s.state == SHUTDOWN
            and self.approval_path is not None
            and Path(self.approval_path).exists()
        ):
            self.m.authorize(t, view.equity, gross, self.approval_path)
        dec = self.m.step(t, view.equity, gross, self._alarm(hist, view))
        out: list[Order] = []
        if dec.transition is not None and dec.flatten:
            out = [Order(p, "sell", priority=-1, reason="halt") for p in sorted(view.positions)]
        if dec.state in (FLAT, SHUTDOWN):
            for o in self.inner.on_candle(
                t, hist, replace(view, risk_multiplier=1.0, halted=False)
            ):  # shadow signals
                self.suppressed.append(
                    {"t": str(t), "pair": o.pair, "side": o.side, "why": dec.state}
                )
            return out
        proposed = self.inner.on_candle(
            t, hist, replace(view, risk_multiplier=dec.cap, halted=False)
        )
        return out + self._enforce(t, view, gross, proposed, dec)

    def _enforce(self, t, view, gross: float, proposed: list[Order], dec: Decision) -> list[Order]:
        allowed = dec.cap * view.equity
        buys = [o for o in proposed if o.side == "buy"]
        total_buy = sum(o.notional for o in buys)
        scale = (
            1.0
            if total_buy <= 0 or gross + total_buy <= allowed
            else max(0.0, (allowed - gross) / total_buy)
        )
        out: list[Order] = []
        for o in proposed:
            if o.side == "buy" and scale < 1.0:
                self.suppressed.append(
                    {"t": str(t), "pair": o.pair, "side": "buy", "why": "cap", "scaled_to": scale}
                )
                if scale * o.notional <= 0:
                    continue
                o = replace(o, notional=o.notional * scale)
            out.append(o)
        if gross > allowed * (1.0 + 1e-9) and gross > 0:
            frac = 1.0 - allowed / gross
            sold = {o.pair for o in out if o.side == "sell" and o.fraction >= 1.0}
            out += [Order(p, "sell", fraction=frac, priority=-1, reason="risk_reduce")
                    for p in sorted(view.positions) if p not in sold]  # fmt: skip
        return out
