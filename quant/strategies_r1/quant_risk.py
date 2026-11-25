# mypy: ignore-errors
"""
R1 risk overlay (Phase 4 research). Pure decision functions + a thin Freqtrade mixin.

Design rules (owner-approved, protocol v3):
* every input is information available at the decision timestamp ``t``: only candles that are
  CLOSED before ``t`` (``date < t``) are ever read; daily regimes use COMPLETED days only;
* equity, drawdown and exposure are mark-to-market portfolio values, not realised profit;
* position size accounts for equity, free cash, current exposure, stop distance, fees and
  slippage, and is never silently rounded UP to an exchange minimum (below minimum -> no trade);
* the drawdown circuit breaker is a LATCH: at ``dd_halt`` new entries stop and only an explicit
  owner approval (``approve_resume``) can restart them; open positions are NOT liquidated, they stay
  under their ATR stops and exit signals (no averaging, no new entries).

Every numeric default below is frozen in ``quant/protocol/protocol_v3.json`` and pinned by the
manifest; a test asserts both agree. Nothing here is tuned on results.
"""

from __future__ import annotations

import atexit
import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)
HOUR = pd.Timedelta("1h")
STOP_EXIT_REASONS = frozenset({"stop_loss", "trailing_stop_loss", "stoploss_on_exchange"})


@dataclass(frozen=True)
class RiskConfig:
    # --- R1 parameters (frozen) -------------------------------------------------------------
    risk_per_trade: float = 0.005  # share of equity lost if the stop is hit
    atr_stop_mult: float = 3.0  # chandelier stop width, also the sizing stop distance
    max_stake_fraction: float = 0.20  # cap per position, share of equity
    max_positions: int = 3
    max_gross_exposure: float = 0.60  # share of equity, mark-to-market
    corr_limit: float = 0.80
    corr_window: int = 720  # hourly returns (30 days)
    corr_min_obs: int = 500  # fewer overlapping observations -> treated as "cannot verify" -> block
    sideways_risk_factor: float = 0.5
    cooldown_hours: int = 24
    cluster_stops: int = 3
    cluster_window_hours: int = 48
    cluster_pause_hours: int = 24
    dd_halve: float = 0.15
    dd_halt: float = 0.20
    halve_factor: float = 0.5
    fixed_stop: float = -0.10  # the original strategies' stop, used when the stop component is off
    # cost assumptions used for SIZING only (the evaluation applies its own cost model)
    fee: float = 0.001
    slippage: float = 0.0005
    stop_extra: float = 0.0005
    # --- components (ablations switch exactly one off) -------------------------------------
    vol_sizing: bool = True
    exposure_limits: bool = True
    correlation: bool = True
    regime_filter: bool = True
    stop_cooldown: bool = True
    circuit_breaker: bool = True


# ============================================================================== time helpers
def last_closed_index(dates: pd.Series, t: pd.Timestamp) -> int:
    """Index of the last candle whose open time is strictly before ``t``; -1 if none."""
    return int(dates.searchsorted(pd.Timestamp(t))) - 1


def closed_closes(df: pd.DataFrame, t: pd.Timestamp, n: int) -> pd.Series:
    """Last ``n`` closes of candles closed before ``t``, indexed by candle open time."""
    i = last_closed_index(df["date"], t)
    if i < 0:
        return pd.Series(dtype=float)
    lo = max(0, i - n + 1)
    return pd.Series(
        df["close"].to_numpy()[lo : i + 1], index=pd.DatetimeIndex(df["date"].iloc[lo : i + 1])
    )


def atr_fraction(df: pd.DataFrame, t: pd.Timestamp) -> float:
    """ATR / close of the last closed candle (``atr`` column from populate_indicators)."""
    i = last_closed_index(df["date"], t)
    if i < 0 or "atr" not in df:
        return math.nan
    atr, close = float(df["atr"].iloc[i]), float(df["close"].iloc[i])
    return atr / close if close > 0 and np.isfinite(atr) else math.nan


# ============================================================================== regime filter
def regime_at(btc: pd.DataFrame | None, t: pd.Timestamp, min_days: int = 250) -> str:
    """BTC/USDT daily regime from COMPLETED days before ``t`` ('unknown' if not computable)."""
    from quant_common import REGIME_UNKNOWN, market_regime

    if btc is None or btc.empty:
        return REGIME_UNKNOWN
    day = pd.Timestamp(t).floor("1D")
    i = last_closed_index(btc["date"], day)  # candles of days strictly before today
    if i < 0:
        return REGIME_UNKNOWN
    frame = btc.iloc[max(0, i - 24 * 420) : i + 1]
    daily = (
        frame.set_index("date")
        .resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    if len(daily) < min_days:
        return REGIME_UNKNOWN
    return str(market_regime(daily.reset_index(drop=True)).iloc[-1])


# ============================================================================== correlation
def correlation(a: pd.Series, b: pd.Series, min_obs: int) -> float:
    """Pearson correlation of hourly returns on the overlapping candles; NaN if too few."""
    ra, rb = a.pct_change(), b.pct_change()
    both = pd.concat([ra.rename("a"), rb.rename("b")], axis=1, join="inner").dropna()
    if len(both) < min_obs or both["a"].std() == 0 or both["b"].std() == 0:
        return math.nan
    return float(both["a"].corr(both["b"]))


def correlation_blocked(
    candidate: pd.Series, open_pairs: dict[str, pd.Series], cfg: RiskConfig
) -> tuple[bool, str]:
    """Block when the candidate is too correlated with ANY open position, or cannot be verified."""
    for pair, series in open_pairs.items():
        c = correlation(candidate, series, cfg.corr_min_obs)
        if math.isnan(c):
            return True, f"corr_unverifiable:{pair}"
        if c >= cfg.corr_limit:
            return True, f"corr:{pair}:{c:.2f}"
    return False, ""


# ============================================================================== stops / cooldown
def chandelier_stop(highest_close: float, atr: float, mult: float) -> float:
    return highest_close - mult * atr


def cooldown_reason(
    stopped: list[tuple[str, pd.Timestamp]], pair: str, t: pd.Timestamp, cfg: RiskConfig
) -> str:
    """Pair cooldown after a stop-out and portfolio pause after a cluster of stop-outs."""
    t = pd.Timestamp(t)
    for p, closed_at in stopped:
        if p == pair and t - closed_at < pd.Timedelta(hours=cfg.cooldown_hours):
            return "pair_cooldown"
    recent = sorted(c for _, c in stopped if t - c < pd.Timedelta(hours=cfg.cluster_window_hours))
    if len(recent) >= cfg.cluster_stops:
        trigger = recent[cfg.cluster_stops - 1]  # the stop-out that completed the cluster
        if t - trigger < pd.Timedelta(hours=cfg.cluster_pause_hours):
            return "cluster_pause"
    return ""


# ============================================================================== equity / sizing
@dataclass(frozen=True)
class Snapshot:
    equity: float
    cash: float
    exposure: float  # mark-to-market value of open positions
    positions: int


def snapshot(
    start: float, closed_profit: float, open_positions: list[tuple[float, float]]
) -> Snapshot:
    """``open_positions`` = [(cost basis incl. fee, mark-to-market liquidation value)]."""
    cost = sum(c for c, _ in open_positions)
    value = sum(v for _, v in open_positions)
    cash = start + closed_profit - cost
    return Snapshot(equity=cash + value, cash=cash, exposure=value, positions=len(open_positions))


def loss_fraction_at_stop(stop_frac: float, cfg: RiskConfig) -> float:
    """Share of the stake lost if the stop fills: price move + 2 fees + 2 slippages + stop extra."""
    return stop_frac + 2 * cfg.fee + 2 * cfg.slippage + cfg.stop_extra


def sized_stake(
    cfg: RiskConfig,
    snap: Snapshot,
    stop_frac: float,
    risk_factor: float,
    proposed: float,
    min_stake: float | None,
    max_stake: float,
) -> tuple[float, str]:
    """Stake for a new position, or (0, reason). Never rounded up to an exchange minimum."""
    if not (
        np.isfinite(snap.equity) and snap.equity > 0 and np.isfinite(stop_frac) and stop_frac > 0
    ):
        return 0.0, "invalid_inputs"
    if cfg.vol_sizing:
        stake = (
            risk_factor * cfg.risk_per_trade * snap.equity / loss_fraction_at_stop(stop_frac, cfg)
        )
        stake = min(stake, cfg.max_stake_fraction * snap.equity)
    else:
        stake = risk_factor * proposed
    if cfg.exposure_limits:
        if snap.positions >= cfg.max_positions:
            return 0.0, "max_positions"
        stake = min(stake, cfg.max_gross_exposure * snap.equity - snap.exposure)
    stake = min(stake, snap.cash / (1 + cfg.fee + cfg.slippage), max_stake)
    if stake <= 0:
        return 0.0, "no_room"
    if min_stake is not None and stake < min_stake:
        return 0.0, "below_min_stake"  # Freqtrade would silently round UP by as much as 30 %
    return float(stake), ""


# ============================================================================== circuit breaker
class DrawdownBreaker:
    """
    Mark-to-market drawdown latch. ``update`` is called with portfolio equity at decision times;
    the peak only moves up. At ``dd_halve`` new risk is halved; at ``dd_halt`` the breaker latches:
    no new entries until ``approve_resume`` is called with the matching halt id (owner decision).
    """

    def __init__(self, cfg: RiskConfig, state_path: str | Path | None = None):
        self.cfg, self.path = cfg, Path(state_path) if state_path else None
        self.peak = 0.0
        self.drawdown = 0.0
        self.halted = False
        self.halt_id: str | None = None
        self.halt_time: pd.Timestamp | None = None
        self.events: list[dict] = []
        if self.path and self.path.exists():
            self._load()

    def update(self, t: pd.Timestamp, equity: float) -> float:
        self.peak = max(self.peak, equity)
        self.drawdown = 1.0 - equity / self.peak if self.peak > 0 else 0.0
        if not self.halted and self.drawdown >= self.cfg.dd_halt:
            self.halted, self.halt_time = True, pd.Timestamp(t)
            self.halt_id = f"halt-{pd.Timestamp(t).strftime('%Y%m%dT%H%M')}"
            self.events.append(
                {
                    "type": "halt",
                    "t": str(t),
                    "dd": self.drawdown,
                    "equity": equity,
                    "id": self.halt_id,
                }
            )
            logger.warning(
                "RISK_HALT %s dd=%.4f equity=%.2f id=%s", t, self.drawdown, equity, self.halt_id
            )
            self._save()
        return self.drawdown

    def multiplier(self) -> float:
        if self.halted:
            return 0.0
        return self.cfg.halve_factor if self.drawdown >= self.cfg.dd_halve else 1.0

    def approve_resume(
        self, halt_id: str, approved_by: str, reset_peak_to: float | None = None
    ) -> bool:
        """Owner-only restart. Returns False (and changes nothing) if the id does not match."""
        if not self.halted or halt_id != self.halt_id or not approved_by:
            return False
        self.halted = False
        if reset_peak_to is not None:
            self.peak = reset_peak_to
        self.events.append({"type": "resume", "id": halt_id, "approved_by": approved_by})
        self._save()
        return True

    def resume_from_file(self, approval_path: str | Path, current_equity: float) -> bool:
        """Live/dry-run: a human writes {"halt_id", "approved_by", "reset_peak": bool}; never automatic."""
        p = Path(approval_path)
        if not self.halted or not p.exists():
            return False
        try:
            data = json.loads(p.read_text())
            return self.approve_resume(
                str(data["halt_id"]),
                str(data["approved_by"]),
                current_equity if data.get("reset_peak") else None,
            )
        except (ValueError, KeyError, OSError):
            return False

    def _save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    {
                        "peak": self.peak,
                        "halted": self.halted,
                        "halt_id": self.halt_id,
                        "halt_time": str(self.halt_time),
                        "events": self.events,
                    }
                )
            )

    def _load(self) -> None:
        d = json.loads(self.path.read_text())  # type: ignore[union-attr]
        self.peak, self.halted, self.halt_id, self.events = (
            d["peak"],
            d["halted"],
            d["halt_id"],
            d["events"],
        )
        self.halt_time = (
            pd.Timestamp(d["halt_time"]) if d.get("halt_time") not in (None, "None") else None
        )


# ============================================================================== decision
@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    stake: float = 0.0
    risk_factor: float = 1.0


def decide_entry(
    cfg: RiskConfig,
    *,
    snap: Snapshot,
    breaker: DrawdownBreaker,
    regime: str,
    atr_frac: float,
    candidate_closes: pd.Series,
    open_closes: dict[str, pd.Series],
    stopped: list[tuple[str, pd.Timestamp]],
    pair: str,
    t: pd.Timestamp,
    proposed: float,
    min_stake: float | None,
    max_stake: float,
) -> Decision:
    """Pure entry decision. Order: halt, regime, cooldown, correlation, then sizing."""
    if cfg.circuit_breaker and breaker.halted:
        return Decision(False, "halted")
    risk_factor = breaker.multiplier() if cfg.circuit_breaker else 1.0
    if cfg.regime_filter:
        if regime in ("bear", "unknown"):
            return Decision(False, f"regime_{regime}")
        if regime == "sideways":
            risk_factor *= cfg.sideways_risk_factor
    if cfg.stop_cooldown:
        why = cooldown_reason(stopped, pair, t, cfg)
        if why:
            return Decision(False, why)
    if cfg.correlation and open_closes:
        blocked, why = correlation_blocked(candidate_closes, open_closes, cfg)
        if blocked:
            return Decision(False, why)
    stop_frac = cfg.atr_stop_mult * atr_frac if cfg.stop_cooldown else abs(cfg.fixed_stop)
    if not (np.isfinite(stop_frac) and stop_frac > 0):
        return Decision(False, "no_atr")
    stake, why = sized_stake(cfg, snap, stop_frac, risk_factor, proposed, min_stake, max_stake)
    if stake <= 0:
        return Decision(False, why or "no_stake")
    return Decision(True, "ok", stake, risk_factor)


# ============================================================================== Freqtrade mixin
class RiskOverlayMixin:
    """Glue only: gathers closed-candle data and open trades, then calls the pure functions."""

    risk_cfg: RiskConfig = RiskConfig()
    use_custom_stoploss = True
    startup_candle_count = (
        600  # exchange limit: 5 OHLCV calls per pair; BTC regime history is read separately
    )
    BTC_PAIR = "BTC/USDT"

    def __init__(self, config: dict) -> None:
        super().__init__(config)  # type: ignore[misc]
        self._breaker = DrawdownBreaker(self.risk_cfg, config.get("risk_state_file"))
        self._decisions: dict = {}
        self._last: dict = {}
        self._snap_cache: tuple | None = None
        self._regime_cache: dict = {}
        self._btc_hist: pd.DataFrame | bool | None = None
        self._denied: dict[str, int] = {}
        self._accepted = 0
        stats_dir = os.environ.get("RISK_STATS_DIR")
        if stats_dir:
            atexit.register(self._dump_stats, Path(stats_dir) / f"{type(self).__name__}.json")

    # -- indicators ------------------------------------------------------------------------
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        import talib

        dataframe = super().populate_indicators(dataframe, metadata)  # type: ignore[misc]
        dataframe["atr"] = talib.ATR(
            dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=14
        )
        return dataframe

    # -- data access (closed candles only) -----------------------------------------------------
    def _frame(self, pair: str) -> pd.DataFrame | None:
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)  # type: ignore[attr-defined]
        except Exception:
            return None
        return None if df is None or df.empty else df

    def _btc_frame(self) -> pd.DataFrame | None:
        """
        BTC candles for the daily regime. EMA(200 days) needs ~250 days of history, far more than
        the exchange lets a strategy request as startup candles, so in offline runs (backtest, analysis) the stored
        candle file is read once. It is only ever sliced to completed days before the decision
        timestamp (see ``regime_at``), so reading the file does not leak the future.
        """
        if self._btc_hist is None:
            hist = None
            try:
                from freqtrade.data.history import load_pair_history
                from freqtrade.enums import RunMode

                if self.dp.runmode not in (RunMode.LIVE, RunMode.DRY_RUN):  # type: ignore[attr-defined]
                    hist = load_pair_history(
                        pair=self.BTC_PAIR,
                        timeframe=self.timeframe,
                        datadir=self.config["datadir"],
                        data_format=self.config.get("dataformat_ohlcv", "feather"),
                        candle_type=self.config.get("candle_type_def"),
                    )
            except Exception:
                logger.warning("BTC history file not readable, using analysed candles only")
            self._btc_hist = hist if hist is not None and not hist.empty else False
        return self._btc_hist if self._btc_hist is not False else self._frame(self.BTC_PAIR)

    def _regime(self, t: pd.Timestamp) -> str:
        day = pd.Timestamp(t).floor("1D")
        if day not in self._regime_cache:
            self._regime_cache[day] = regime_at(self._btc_frame(), t)
        return self._regime_cache[day]

    def _start_balance(self) -> float:
        wallets = getattr(self, "wallets", None)
        if wallets is not None:
            try:
                return float(wallets.get_starting_balance())
            except Exception:
                logger.debug("starting balance unavailable, falling back to config")
        w = self.config.get("dry_run_wallet", 1000)
        return float(w if not isinstance(w, dict) else next(iter(w.values())))

    def _snapshot(self, t: pd.Timestamp) -> Snapshot:
        from freqtrade.persistence import Trade

        key = (
            pd.Timestamp(t),
            len(Trade.get_trades_proxy(is_open=False)),
            len(Trade.get_trades_proxy(is_open=True)),
        )
        if self._snap_cache and self._snap_cache[0] == key:
            return self._snap_cache[1]
        closed = sum(
            float(tr.close_profit_abs or 0.0) for tr in Trade.get_trades_proxy(is_open=False)
        )
        open_pos = []
        for tr in Trade.get_trades_proxy(is_open=True):
            df = self._frame(tr.pair)
            i = last_closed_index(df["date"], t) if df is not None else -1
            rate = float(df["close"].iloc[i]) if i >= 0 else float(tr.open_rate)
            open_pos.append(
                (
                    float(tr.open_trade_value),
                    float(tr.open_trade_value) + float(tr.calc_profit(rate)),
                )
            )
        snap = snapshot(self._start_balance(), closed, open_pos)
        self._snap_cache = (key, snap)
        if self.risk_cfg.circuit_breaker:
            self._breaker.update(pd.Timestamp(t), snap.equity)
        return snap

    def _stopped(self) -> list[tuple[str, pd.Timestamp]]:
        from freqtrade.persistence import Trade

        return [
            (tr.pair, pd.Timestamp(tr.close_date_utc))
            for tr in Trade.get_trades_proxy(is_open=False)
            if tr.exit_reason in STOP_EXIT_REASONS and tr.close_date_utc is not None
        ]

    # -- decisions ---------------------------------------------------------------------------
    def _decide(self, pair: str, t, proposed: float, min_stake, max_stake: float) -> Decision:
        from freqtrade.persistence import Trade

        key = (pair, pd.Timestamp(t))
        if key in self._decisions:
            return self._decisions[key]
        snap = self._snapshot(t)
        df = self._frame(pair)
        if df is None:
            d = Decision(False, "no_data")
        else:
            open_pairs = {tr.pair for tr in Trade.get_trades_proxy(is_open=True)} - {pair}
            n = self.risk_cfg.corr_window + 1
            d = decide_entry(
                self.risk_cfg,
                snap=snap,
                breaker=self._breaker,
                regime=self._regime(t) if self.risk_cfg.regime_filter else "bull",
                atr_frac=atr_fraction(df, t),
                candidate_closes=closed_closes(df, t, n),
                open_closes={
                    p: closed_closes(f, t, n)
                    for p in open_pairs
                    if (f := self._frame(p)) is not None
                },
                stopped=self._stopped(),
                pair=pair,
                t=pd.Timestamp(t),
                proposed=proposed,
                min_stake=min_stake,
                max_stake=max_stake,
            )
        self._decisions[key] = d
        self._last[pair] = (pd.Timestamp(t), d)
        if d.allowed:
            self._accepted += 1
        else:
            self._denied[d.reason.split(":")[0]] = self._denied.get(d.reason.split(":")[0], 0) + 1
        return d

    def custom_stake_amount(
        self,
        pair,
        current_time,
        current_rate,
        proposed_stake,
        min_stake,
        max_stake,
        leverage,
        entry_tag,
        side,
        **kwargs,
    ):
        d = self._decide(pair, current_time, float(proposed_stake), min_stake, float(max_stake))
        return d.stake if d.allowed else 0.0

    def confirm_trade_entry(
        self, pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side, **kwargs
    ):
        last = self._last.get(pair)
        if last is None or abs(pd.Timestamp(current_time) - last[0]) > pd.Timedelta(minutes=5):
            return False  # fail closed: no matching sizing decision
        return bool(last[1].allowed)

    def custom_stoploss(
        self, pair, trade, current_time, current_rate, current_profit, after_fill=False, **kwargs
    ):
        from freqtrade.strategy import stoploss_from_absolute

        self._snapshot(
            current_time
        )  # keeps the mark-to-market peak current while positions are open
        cfg = self.risk_cfg
        if not cfg.stop_cooldown:
            return stoploss_from_absolute(trade.open_rate * (1 + cfg.fixed_stop), current_rate)
        df = self._frame(pair)
        if df is None:
            return None
        i = last_closed_index(df["date"], current_time)
        atr = float(df["atr"].iloc[i]) if i >= 0 else math.nan
        if not np.isfinite(atr):
            return None  # keep the previous stop
        since = (df["date"] >= pd.Timestamp(trade.open_date_utc)).to_numpy()[: i + 1]
        seg = df["close"].to_numpy()[: i + 1][since]
        highest = max(float(seg.max()) if seg.size else 0.0, float(trade.open_rate))
        return stoploss_from_absolute(
            chandelier_stop(highest, atr, cfg.atr_stop_mult), current_rate
        )

    # -- bookkeeping ---------------------------------------------------------------------------
    def _dump_stats(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "accepted": self._accepted,
                    "denied": self._denied,
                    "breaker_events": self._breaker.events,
                    "peak_equity": self._breaker.peak,
                    "config": asdict(self.risk_cfg),
                }
            )
        )
