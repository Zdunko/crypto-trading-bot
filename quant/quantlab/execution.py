"""
Stage 0 execution engine: ONE cost model, ONE equity definition, deterministic fills.

Why it exists (Phase 4B findings): costs used to enter in two places (Freqtrade ``--fee`` and a
post-hoc layer), so state-dependent rules (sizing, circuit breaker) acted on a cheaper world than
the one that was reported. Here the strategy sees the same net, mark-to-market equity the report
uses, and the engine is restartable from an explicit state (needed for trade-level causality tests).

Contract
* Time step = one candle. At the open of candle ``i`` the strategy sees ONLY candles ``< i``
  (:class:`History`) plus an explicit :class:`PortfolioView`; its orders fill at the open of ``i``.
* Costs come from :class:`~quantlab.costs.CostScenario` through ``entry_price``/``exit_price``
  (the same functions the legacy post-hoc layer uses): buy at ``open*(1+slip)`` plus fee on value;
  sell at ``open*(1-slip)`` less fee; stop exits also pay ``stop_extra``.
* Equity = cash + open positions at liquidation value (last known close less one exit cost).
* Order processing order is fixed: stop moves, sells, then buys, each sorted by (priority, pair).
* Liquidity (optional ``max_participation``): one order fills at most that share of the candle's
  volume; the rest of a SELL continues on the next candle. Halt liquidations never expire.
* Missing candle: the order waits (at most ``max_defer`` candles, then it expires and is logged);
  positions are valued at the last known close; a stop cannot trigger without a candle.
* Funds: a buy is clipped to free cash; below ``min_notional`` it is rejected (never rounded up).
* Stops fill at the stop price, or at the open when the candle opens beyond it
  (``stop_fill="conservative"``); ``"freqtrade"`` reproduces Freqtrade (stop price unless the whole
  candle is beyond the stop) and exists for reconciliation only.
* Circuit breaker (continuous): equity is checked at the close of EVERY candle. Drawdown from peak
  >= ``dd_reduce`` halves ``risk_multiplier``; >= ``dd_halt`` halts: new buys are rejected and, with
  ``halt_action="flatten"``, every position is sold at the next open (``"hold"`` keeps positions
  and their stops). A halt is latched; only an owner approval timestamp in ``approvals`` resumes
  (peak reset to current equity). Without approval a halt is terminal.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quantlab.costs import BASE, CostScenario, entry_price, exit_price


@dataclass(frozen=True)
class ExecConfig:
    costs: CostScenario = BASE
    wallet: float = 1000.0
    min_notional: float = 5.0
    max_defer: int = 3
    max_participation: float | None = None  # max share of a candle's volume one order may take
    stop_fill: str = "conservative"  # or "freqtrade"
    halt_action: str = "flatten"  # or "hold"
    breaker: bool = True
    dd_reduce: float = 0.15
    dd_halt: float = 0.20
    reduce_factor: float = 0.5

    def lumped_fee(self) -> float:
        """Single per-side rate for a native Freqtrade confirmation run (stop_extra not representable)."""
        return self.costs.fee + self.costs.slippage


@dataclass
class Order:
    pair: str
    side: str  # "buy" | "sell" | "set_stop"
    notional: float = 0.0  # buy: quote amount to spend including fee
    fraction: float = 1.0  # sell: share of the position
    stop: float | None = None  # buy / set_stop: absolute stop price
    stop_pct: float | None = (
        None  # buy: stop as a share below the FILL price (unknown to the strategy)
    )
    priority: int = 0
    reason: str = "signal"
    attempts: int = 0
    add: bool = False  # buy: allow adding to an open position (weighted cost basis)


@dataclass
class Position:
    qty: float
    open_time: pd.Timestamp
    open_ref: float
    open_value: float
    stop: float | None = None


@dataclass
class BreakerState:
    peak: float
    halted: bool = False
    halt_id: str | None = None
    events: list[dict] = field(default_factory=list)
    drawdown: float = 0.0


@dataclass
class EngineState:
    """Everything needed to restart a run mid-way (state injection for causality tests)."""

    cash: float
    positions: dict[str, Position]
    pending: list[Order]
    breaker: BreakerState

    def copy(self) -> EngineState:
        return deepcopy(self)


@dataclass
class PortfolioView:
    time: pd.Timestamp
    cash: float
    equity: float
    positions: dict[str, tuple[float, float]]  # pair -> (qty, liquidation value at last close)
    halted: bool
    drawdown: float
    risk_multiplier: float


class PriceData:
    """Candles aligned on one index; NaN marks a missing candle (never forward-filled here)."""

    def __init__(self, candles: dict[str, pd.DataFrame], index: pd.DatetimeIndex):
        self.index = index
        self.pairs = sorted(candles)
        cols = {
            k: np.full((len(index), len(self.pairs)), np.nan)
            for k in ("open", "high", "low", "close", "volume")
        }
        for j, pair in enumerate(self.pairs):
            df = candles[pair].copy()
            df["date"] = pd.to_datetime(df["date"], utc=True).dt.as_unit("ns")
            df = df.drop_duplicates("date").set_index("date").reindex(index)
            for k, arr in cols.items():
                if k in df:
                    arr[:, j] = df[k].to_numpy(dtype=float)
        self.open, self.high, self.low, self.close = (
            cols[k] for k in ("open", "high", "low", "close")
        )
        self.volume = cols["volume"]  # base-currency volume per candle; NaN if unknown
        self.close_ff = pd.DataFrame(self.close).ffill().to_numpy()
        self.col = {p: j for j, p in enumerate(self.pairs)}


class History:
    """Read-only view of candles strictly before ``i``. The strategy never receives anything else."""

    def __init__(self, data: PriceData, i: int):
        self._d, self._i = data, i

    @property
    def pairs(self) -> list[str]:
        return self._d.pairs

    @property
    def times(self) -> pd.DatetimeIndex:
        return self._d.index[: self._i]

    def closes(self, pair: str, n: int | None = None) -> np.ndarray:
        a = self._d.close[: self._i, self._d.col[pair]]
        return a[-n:].copy() if n else a.copy()

    def ohlc(self, pair: str, n: int | None = None) -> np.ndarray:
        j = self._d.col[pair]
        a = np.column_stack([self._d.open[: self._i, j], self._d.high[: self._i, j],
                             self._d.low[: self._i, j], self._d.close[: self._i, j]])  # fmt: skip
        return a[-n:].copy() if n else a.copy()

    def last_close(self, pair: str) -> float:
        return (
            float(self._d.close_ff[self._i - 1, self._d.col[pair]]) if self._i > 0 else float("nan")
        )


class Strategy:
    def on_candle(self, t: pd.Timestamp, hist: History, view: PortfolioView) -> list[Order]:
        raise NotImplementedError


@dataclass
class Result:
    trades: pd.DataFrame
    equity: pd.Series
    orders: list[dict]
    rejects: list[dict]
    breaker_events: list[dict]
    state: EngineState
    hash: str


def _liq(qty: float, px: float, costs: CostScenario) -> float:
    return qty * float(exit_price(px, costs, False)) * (1 - costs.fee)


def run(
    strategy: Strategy,
    data: PriceData,
    cfg: ExecConfig,
    start: int = 0,
    end: int | None = None,
    state: EngineState | None = None,
    approvals: Sequence[pd.Timestamp] = (),
) -> Result:
    c = cfg.costs
    end = len(data.index) if end is None else end
    st = state.copy() if state else EngineState(cfg.wallet, {}, [], BreakerState(cfg.wallet))
    approvals_ns = {pd.Timestamp(a).value for a in approvals}
    trades: list[dict] = []
    orders_log: list[dict] = []
    rejects: list[dict] = []
    eq_out = np.full(end - start, np.nan)

    def equity_at(i_close: int) -> float:
        if i_close < 0:
            return st.cash
        return st.cash + sum(
            _liq(p.qty, data.close_ff[i_close, data.col[k]], c) for k, p in st.positions.items()
        )

    def cap_qty(i: int, j: int) -> float:
        """Largest quantity one order may fill on candle i (liquidity constraint)."""
        if cfg.max_participation is None:
            return float("inf")
        v = data.volume[i, j]
        return float(cfg.max_participation * v) if np.isfinite(v) else 0.0

    def reject(i, o, why):
        rejects.append(
            {"i": i, "time": str(data.index[i]), "pair": o.pair, "side": o.side, "reason": why}
        )

    def close_pos(i, pair, fraction, ref_px, is_stop, reason):
        p = st.positions[pair]
        qty = p.qty * fraction
        ex = float(exit_price(ref_px, c, is_stop))
        proceeds = qty * ex * (1 - c.fee)
        cost = p.open_value * fraction
        st.cash += proceeds
        trades.append({
            "pair": pair, "open_date": p.open_time, "close_date": data.index[i], "amount": qty,
            "open_rate": p.open_ref, "close_rate": ref_px, "fee_open": c.fee, "fee_close": c.fee,
            "exit_reason": "stop_loss" if is_stop else reason, "open_value": cost,
            "profit_abs": proceeds - cost, "profit_ratio": proceeds / cost - 1,
        })  # fmt: skip
        if fraction >= 1 - 1e-12:
            del st.positions[pair]
        else:
            p.qty -= qty
            p.open_value -= cost

    for i in range(start, end):
        t = data.index[i]
        eq_prev = equity_at(i - 1)
        br = st.breaker
        # ---- continuous circuit breaker on the close of the previous candle
        if (cfg.breaker and i > start) or (cfg.breaker and state is not None):
            br.peak = max(br.peak, eq_prev)
            br.drawdown = 1.0 - eq_prev / br.peak if br.peak > 0 else 0.0
            if br.halted and t.value in approvals_ns:
                br.halted = False
                br.peak = eq_prev
                br.drawdown = 0.0
                br.events.append({"type": "resume", "time": str(t), "id": br.halt_id})
            if not br.halted and br.drawdown >= cfg.dd_halt:
                br.halted, br.halt_id = True, f"halt-{t.strftime('%Y%m%dT%H%M')}"
                br.events.append({"type": "halt", "time": str(t), "drawdown": br.drawdown,
                                  "equity": eq_prev, "id": br.halt_id})  # fmt: skip
                if cfg.halt_action == "flatten":
                    st.pending = [o for o in st.pending if o.side != "buy"]
                    st.pending += [
                        Order(k, "sell", priority=-1, reason="halt") for k in st.positions
                    ]
        mult = 0.0 if br.halted else (cfg.reduce_factor if br.drawdown >= cfg.dd_reduce else 1.0)
        view = PortfolioView(
            t, st.cash, eq_prev,
            {k: (p.qty, _liq(p.qty, data.close_ff[i - 1, data.col[k]], c) if i > 0 else 0.0) for k, p in st.positions.items()},
            br.halted, br.drawdown, mult,
        )  # fmt: skip
        new = strategy.on_candle(t, History(data, i), view) or []
        for o in new:
            orders_log.append({"i": i, "time": str(t), "pair": o.pair, "side": o.side, "notional": o.notional,
                               "fraction": o.fraction, "stop": o.stop, "reason": o.reason})  # fmt: skip
        queue = st.pending + list(new)
        st.pending = []
        rank = {"set_stop": 0, "sell": 1, "buy": 2}
        queue.sort(key=lambda o: (rank[o.side], o.priority, o.pair))
        for o in queue:
            j = data.col[o.pair]
            have = not np.isnan(data.open[i, j])
            if o.side == "set_stop":
                if o.pair in st.positions:
                    st.positions[o.pair].stop = o.stop
                else:
                    reject(i, o, "no_position")
                continue
            if o.side == "sell":
                if o.pair not in st.positions:
                    reject(i, o, "no_position")
                elif not have or cap_qty(i, j) <= 0:
                    o.attempts += 1
                    # a halt liquidation never expires: it waits for a candle with liquidity
                    if o.reason == "halt" or o.attempts <= cfg.max_defer:
                        st.pending.append(o)
                    else:
                        reject(i, o, "expired")
                else:
                    pos = st.positions[o.pair]
                    want = pos.qty * min(o.fraction, 1.0)
                    got = min(want, cap_qty(i, j))
                    close_pos(i, o.pair, got / pos.qty, float(data.open[i, j]), False, o.reason)
                    if got < want * (
                        1 - 1e-12
                    ):  # liquidity-limited: the rest continues next candle
                        rest = pos.qty if o.pair in st.positions else 0.0
                        if rest > 0:
                            rem = (want - got) / rest
                            st.pending.append(
                                Order(
                                    o.pair,
                                    "sell",
                                    fraction=min(rem, 1.0),
                                    priority=o.priority,
                                    reason=o.reason,
                                )
                            )
                continue
            # buy
            if br.halted and cfg.breaker:
                reject(i, o, "halted")
            elif o.pair in st.positions and not o.add:
                reject(i, o, "already_open")
            elif o.notional < cfg.min_notional:
                reject(i, o, "below_min_notional")
            elif not have:
                o.attempts += 1
                (st.pending.append(o) if o.attempts <= cfg.max_defer else reject(i, o, "expired"))
            else:
                spend = min(o.notional, st.cash)
                if spend < cfg.min_notional:
                    reject(i, o, "insufficient_funds")
                    continue
                ref = float(data.open[i, j])
                unit = float(entry_price(ref, c)) * (1 + c.fee)
                spend = min(spend, cap_qty(i, j) * unit)  # liquidity: never more than the cap
                if spend < cfg.min_notional:
                    reject(i, o, "illiquid")
                    continue
                qty = spend / unit
                st.cash -= spend
                stop = (
                    o.stop
                    if o.stop is not None
                    else (ref * (1 - o.stop_pct) if o.stop_pct else None)
                )
                if o.pair in st.positions:  # add: weighted cost basis, stop unchanged
                    p0 = st.positions[o.pair]
                    p0.open_ref = (p0.qty * p0.open_ref + qty * ref) / (p0.qty + qty)
                    p0.qty += qty
                    p0.open_value += spend
                else:
                    st.positions[o.pair] = Position(qty, t, ref, spend, stop)
        # ---- stops (also on the entry candle, as Freqtrade does)
        for pair in sorted(st.positions):
            p = st.positions[pair]
            j = data.col[pair]
            if p.stop is None or np.isnan(data.open[i, j]):
                continue
            op, hi, lo = (float(data.open[i, j]), float(data.high[i, j]), float(data.low[i, j]))
            if cfg.stop_fill == "freqtrade":
                if lo <= p.stop:
                    close_pos(i, pair, 1.0, op if p.stop > hi else p.stop, True, "stop")
            elif op <= p.stop or lo <= p.stop:
                close_pos(i, pair, 1.0, min(op, p.stop), True, "stop")
        eq_out[i - start] = equity_at(i)

    tdf = pd.DataFrame(trades)
    eq = pd.Series(eq_out, index=data.index[start:end])
    h = hashlib.sha256()
    h.update(eq.to_numpy().tobytes())
    h.update(tdf.to_json(date_format="iso", double_precision=15).encode() if len(tdf) else b"")
    h.update(repr(orders_log).encode() + repr(rejects).encode())
    return Result(tdf, eq, orders_log, rejects, st.breaker.events, st, h.hexdigest())
