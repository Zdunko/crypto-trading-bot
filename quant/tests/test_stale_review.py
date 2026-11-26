"""S6 risk review R1: what the frozen S2 risk layer does when a HELD asset stops printing candles.
Characterisation on synthetic data; nothing in the frozen risk layer or its parameters is modified."""

from __future__ import annotations

import numpy as np
import pandas as pd
from test_benchmarks import CFG, members, panel

from quantlab import benchmarks as bm
from quantlab.execution import Order, PriceData, Strategy, run
from quantlab.risk_v2 import RiskManagedStrategy, RiskStateMachine, RiskV2Config


SHUTDOWN = "SHUTDOWN"


class HoldBoth(Strategy):
    def on_candle(self, t, hist, view):
        return [
            Order(p, "buy", notional=300.0) for p in ("X/USDT", "Y/USDT") if p not in view.positions
        ]


def hourly_panel(n=400, stop=100):
    idx = pd.date_range("2022-01-01", periods=n, freq="1h", tz="UTC")
    out = {}
    for p in ("X/USDT", "Y/USDT"):
        c = np.full(n, 100.0)
        o = c.copy()
        df = pd.DataFrame({"date": idx, "open": o, "high": c, "low": c, "close": c, "volume": 1e9})
        out[p] = df.iloc[:stop].copy() if p == "X/USDT" else df
    return PriceData(out, idx)


def run_risk(data):
    machine = RiskStateMachine.new(RiskV2Config(), 1000.0)
    res = run(RiskManagedStrategy(HoldBoth(), machine), data, CFG)
    return machine, res


def test_hourly_candles_a_stale_held_asset_triggers_shutdown_after_48_candles_and_stays_stuck():
    stop = 100
    machine, res = run_risk(hourly_panel(stop=stop))
    rec = [r for r in machine.records if r["to"] == SHUTDOWN]
    assert (
        rec and rec[0]["cause"] == "integrity" and machine.s.safety_disqualified
    )  # permanent, no auto-restart
    t_alarm = pd.Timestamp(rec[0]["t"])
    first_missing = pd.Timestamp("2022-01-01", tz="UTC") + pd.Timedelta(hours=stop)
    delay = (t_alarm - first_missing) / pd.Timedelta(hours=1)
    assert 47 <= delay <= 50  # data_gap_candles = 48 candles
    # liquidation: Y (still printing) is sold, X (no candle) cannot be: it stays held, valued at its last close
    assert "Y/USDT" not in res.state.positions and "X/USDT" in res.state.positions
    assert res.state.positions["X/USDT"].open_value > 0
    assert np.isfinite(res.equity.iloc[-1])
    # no new entries after the shutdown
    assert not [o for o in res.orders if o["side"] == "buy" and pd.Timestamp(o["time"]) > t_alarm]


def test_the_stale_asset_is_valued_at_its_last_close_so_equity_hides_the_loss():
    """Documented weakness: even if X is worthless after it stops printing, reported equity keeps valuing it at the last
    close less one exit cost. The risk layer cannot see that loss; stuck positions must be reported separately."""
    _machine, res = run_risk(hourly_panel(stop=100))
    x = res.state.positions["X/USDT"]
    assert res.equity.iloc[-1] > 800  # the X position (300 notional) is still counted in equity
    last = {"X/USDT": pd.Timestamp("2022-01-05 03:00", tz="UTC")}
    stuck = bm.stuck_positions(
        res, last, pd.Timestamp("2022-01-17 15:00", tz="UTC"), pd.Timedelta(hours=48)
    )
    assert [s["pair"] for s in stuck] == ["X/USDT"] and abs(stuck[0]["cost"] - x.open_value) < 1e-9


def test_daily_candles_delay_stale_detection_to_48_days_because_the_thresholds_are_in_candles():
    """The frozen S2 config counts CANDLES (data_gap_candles = 48): on daily data a delisted holding is only detected
    after 48 days. Parameters stay frozen; the consequence is a design constraint for daily strategies."""
    n = 200
    idx = pd.date_range("2022-01-01", periods=n, freq="1D", tz="UTC")
    out = {}
    for p in ("X/USDT", "Y/USDT"):
        c = np.full(n, 100.0)
        df = pd.DataFrame({"date": idx, "open": c, "high": c, "low": c, "close": c, "volume": 1e9})
        out[p] = df.iloc[:20].copy() if p == "X/USDT" else df
    machine, _res = run_risk(PriceData(out, idx))
    rec = [r for r in machine.records if r["to"] == SHUTDOWN]
    assert rec
    delay_days = (pd.Timestamp(rec[0]["t"]) - idx[20]) / pd.Timedelta(days=1)
    assert 47 <= delay_days <= 50


def test_a_benchmark_holding_a_delisted_asset_also_keeps_it_valued_at_the_last_close():
    data = panel(["X/USDT"], n=60, flat=True, ends={"X/USDT": 30})
    res = run(bm.PitEqualWeight(members("X/USDT")), data, CFG)
    assert "X/USDT" in res.state.positions  # cannot be sold without a candle
    assert (
        res.equity.iloc[-1] == res.equity.iloc[40]
    )  # the loss of a dead asset is invisible in engine equity
