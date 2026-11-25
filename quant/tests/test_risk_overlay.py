"""R1 risk overlay: sizing arithmetic, breaker latch, causality, gaps, minimums, missing data."""

import json
import math
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import talib
from quant_risk import (
    DrawdownBreaker,
    RiskConfig,
    atr_fraction,
    chandelier_stop,
    closed_closes,
    cooldown_reason,
    correlation,
    correlation_blocked,
    decide_entry,
    last_closed_index,
    loss_fraction_at_stop,
    regime_at,
    sized_stake,
    snapshot,
)
from synth import random_walk_ohlcv


CFG = RiskConfig()
T0 = pd.Timestamp("2024-03-01 12:00", tz="UTC")


def frame(n=1500, seed=1, start="2024-01-01", drift=0.0, vol=0.008):
    df = random_walk_ohlcv(n, seed=seed, vol=vol, start=start)
    if drift:
        df["close"] = df["close"] * np.exp(drift * np.arange(n))
        df["open"], df["high"], df["low"] = df["close"], df["close"] * 1.001, df["close"] * 0.999
    df["atr"] = talib.ATR(df["high"], df["low"], df["close"], timeperiod=14)
    return df


def snap(equity=1000.0, cash=None, exposure=0.0, positions=0):
    return (
        snapshot(equity, 0.0, [])
        if cash is None and not exposure
        else type(snapshot(1, 0, []))(
            equity=equity,
            cash=equity - exposure if cash is None else cash,
            exposure=exposure,
            positions=positions,
        )
    )


# ------------------------------------------------------------------ closed-candle discipline
def test_only_candles_closed_before_t_are_used():
    df = frame()
    t = df["date"].iloc[500]  # the candle opening exactly at t is NOT closed yet
    assert last_closed_index(df["date"], t) == 499
    assert closed_closes(df, t, 10).index[-1] == df["date"].iloc[499]
    assert last_closed_index(df["date"], df["date"].iloc[0]) == -1


def test_atr_fraction_ignores_everything_from_t_onwards():
    df = frame()
    t = df["date"].iloc[800]
    base = atr_fraction(df, t)
    mutated = df.copy()
    mutated.loc[800:, ["open", "high", "low", "close", "atr"]] *= (
        7.0  # wild future (and the t candle)
    )
    assert atr_fraction(mutated, t) == pytest.approx(base) and 0 < base < 0.2


def test_regime_uses_completed_days_only_and_needs_history():
    n = 24 * 330
    btc = frame(n, drift=0.0004, start="2023-01-01")
    day = pd.Timestamp("2023-11-20", tz="UTC")
    t = day + pd.Timedelta("15h")
    label = regime_at(btc, t)
    assert label in ("bull", "bear", "sideways")
    changed = btc.copy()
    changed.loc[changed["date"] >= day, ["open", "high", "low", "close"]] *= 0.1  # crash 'today'
    assert regime_at(changed, t) == label  # today's candles must not matter
    assert regime_at(btc, pd.Timestamp("2023-03-01", tz="UTC")) == "unknown"  # too little history
    assert regime_at(None, t) == "unknown" and regime_at(btc.iloc[0:0], t) == "unknown"


# ------------------------------------------------------------------ correlation
def test_correlation_blocks_same_bet_allows_independent_and_fails_closed():
    a = closed_closes(frame(seed=1), T0 + pd.Timedelta(days=40), 721)
    twin = a * 1.5
    other = closed_closes(frame(seed=9), T0 + pd.Timedelta(days=40), 721)
    assert correlation_blocked(a, {"TWIN": twin}, CFG)[0] is True
    assert correlation_blocked(a, {"OTHER": other}, CFG) == (False, "")
    short = a.iloc[-100:]
    blocked, why = correlation_blocked(a, {"SHORT": short}, CFG)
    assert blocked and why.startswith("corr_unverifiable")
    flat = pd.Series(1.0, index=a.index)
    assert math.isnan(correlation(a, flat, 10))


# ------------------------------------------------------------------ cooldown / cluster pause
def test_cooldown_and_cluster_pause_windows():
    h = pd.Timedelta(hours=1)
    stops = [("A/USDT", T0 - 10 * h)]
    assert cooldown_reason(stops, "A/USDT", T0, CFG) == "pair_cooldown"
    assert cooldown_reason(stops, "B/USDT", T0, CFG) == ""
    assert cooldown_reason(stops, "A/USDT", T0 + 15 * h, CFG) == ""  # 25 h after the stop
    three = [("A/USDT", T0 - 30 * h), ("B/USDT", T0 - 20 * h), ("C/USDT", T0 - 5 * h)]
    assert cooldown_reason(three, "D/USDT", T0, CFG) == "cluster_pause"
    assert (
        cooldown_reason(three, "D/USDT", T0 + 20 * h, CFG) == ""
    )  # pause (24 h from the 3rd) over
    assert cooldown_reason(three[:2], "D/USDT", T0, CFG) == ""  # two stop-outs are not a cluster


# ------------------------------------------------------------------ sizing arithmetic
def test_stake_makes_the_stop_loss_exactly_the_risk_budget_including_costs():
    s = snap(1000.0)
    stake, why = sized_stake(CFG, s, 0.06, 1.0, 100.0, 5.0, 1e9)
    assert why == "" and stake == pytest.approx(1000 * 0.005 / (0.06 + 0.002 + 0.001 + 0.0005))
    assert stake * loss_fraction_at_stop(0.06, CFG) == pytest.approx(5.0)  # 0.5 % of equity
    half, _ = sized_stake(CFG, s, 0.06, 0.5, 100.0, 5.0, 1e9)
    assert half == pytest.approx(stake / 2)


def test_stake_respects_cap_cash_exposure_room_and_positions():
    big, _ = sized_stake(CFG, snap(1000.0), 0.002, 1.0, 100.0, 5.0, 1e9)
    assert big == pytest.approx(200.0)  # 20 % cap
    poor, _ = sized_stake(CFG, snap(1000.0, cash=50.0), 0.02, 1.0, 100.0, 5.0, 1e9)
    assert poor == pytest.approx(50.0 / (1 + CFG.fee + CFG.slippage))  # cash incl. fee and slippage
    room, _ = sized_stake(
        CFG, snap(1000.0, exposure=550.0, positions=2), 0.02, 1.0, 100.0, 5.0, 1e9
    )
    assert room == pytest.approx(50.0)  # 60 % * 1000 - 550
    assert (
        sized_stake(CFG, snap(1000.0, exposure=600.0, positions=2), 0.02, 1.0, 100.0, 5.0, 1e9)[1]
        == "no_room"
    )
    assert (
        sized_stake(CFG, snap(1000.0, exposure=100.0, positions=3), 0.02, 1.0, 100.0, 5.0, 1e9)[1]
        == "max_positions"
    )
    assert sized_stake(CFG, snap(1000.0), 0.02, 1.0, 100.0, 5.0, 40.0)[0] == pytest.approx(
        40.0
    )  # exchange max


def test_below_exchange_minimum_means_no_trade_never_rounding_up():
    stake, why = sized_stake(
        CFG, snap(1000.0), 0.06, 1.0, 100.0, 80.0, 1e9
    )  # wants 78.7, minimum 80
    assert (stake, why) == (0.0, "below_min_stake")
    assert sized_stake(CFG, snap(1000.0), 0.06, 1.0, 100.0, 78.0, 1e9)[0] > 78.0


@pytest.mark.parametrize("bad", [0.0, -0.1, math.nan, math.inf])
def test_invalid_stop_distance_or_equity_sizes_to_zero(bad):
    assert sized_stake(CFG, snap(1000.0), bad, 1.0, 100.0, 5.0, 1e9)[0] == 0.0
    assert sized_stake(CFG, snap(bad), 0.05, 1.0, 100.0, 5.0, 1e9)[0] == 0.0


def test_gap_through_the_stop_loses_more_than_budget_but_the_cap_bounds_it():
    s = snap(1000.0)
    stake, _ = sized_stake(CFG, s, 0.01, 1.0, 100.0, 5.0, 1e9)  # calm market -> capped at 20 %
    assert stake == pytest.approx(200.0)
    gap_loss = stake * 0.50  # price halves overnight, stop cannot fill
    assert gap_loss > 0.005 * 1000  # budget is exceeded (gap risk is real) ...
    assert gap_loss <= 0.20 * 1000 * 0.50  # ... but bounded by cap x gap, i.e. 10 % of equity here


def test_snapshot_is_mark_to_market_and_cash_accounting_is_consistent():
    s = snapshot(1000.0, closed_profit=50.0, open_positions=[(200.0, 150.0), (100.0, 130.0)])
    assert s.cash == pytest.approx(1000 + 50 - 300) and s.exposure == pytest.approx(280)
    assert (
        s.equity == pytest.approx(750 + 280) and s.positions == 2
    )  # unrealised loss and gain both count


# ------------------------------------------------------------------ circuit breaker
def test_breaker_halves_then_halts_and_latch_survives_recovery_until_owner_approves(tmp_path):
    b = DrawdownBreaker(CFG, tmp_path / "state.json")
    b.update(T0, 1000.0)
    assert b.multiplier() == 1.0
    b.update(T0 + pd.Timedelta("1h"), 840.0)  # -16 %
    assert b.multiplier() == 0.5 and not b.halted
    b.update(T0 + pd.Timedelta("2h"), 790.0)  # -21 % -> halt
    assert b.halted and b.multiplier() == 0.0 and b.halt_id
    b.update(T0 + pd.Timedelta("3h"), 1200.0)  # equity "recovers" - the latch must not release
    assert b.halted and b.multiplier() == 0.0
    assert not b.approve_resume("wrong-id", "owner")
    assert not b.approve_resume(b.halt_id, "")  # anonymous approval is not approval
    assert b.halted
    assert b.approve_resume(b.halt_id, "owner", reset_peak_to=1200.0)
    assert not b.halted and b.peak == 1200.0
    reloaded = DrawdownBreaker(CFG, tmp_path / "state.json")
    assert [e["type"] for e in reloaded.events] == ["halt", "resume"]


def test_halted_state_is_persisted_and_resume_needs_an_owner_written_file(tmp_path):
    state = tmp_path / "s.json"
    b = DrawdownBreaker(CFG, state)
    b.update(T0, 1000.0)
    b.update(T0 + pd.Timedelta("1h"), 700.0)
    again = DrawdownBreaker(CFG, state)  # a restart must not forget the halt
    assert again.halted and again.halt_id == b.halt_id
    approval = tmp_path / "approval.json"
    assert not again.resume_from_file(approval, 700.0)  # no file -> nothing happens
    approval.write_text("not json")
    assert not again.resume_from_file(approval, 700.0) and again.halted
    approval.write_text(json.dumps({"halt_id": "other", "approved_by": "owner"}))
    assert not again.resume_from_file(approval, 700.0) and again.halted
    approval.write_text(
        json.dumps({"halt_id": again.halt_id, "approved_by": "owner", "reset_peak": True})
    )
    assert again.resume_from_file(approval, 700.0) and not again.halted and again.peak == 700.0


def test_flat_portfolio_cannot_trade_its_way_out_of_a_halt():
    """Owner correction: a halted account with no positions stays halted - nothing can change equity."""
    b = DrawdownBreaker(CFG)
    b.update(T0, 1000.0)
    b.update(T0 + pd.Timedelta("1h"), 790.0)
    for k in range(2, 400):  # flat: equity never moves; no entries are allowed to change that
        b.update(T0 + pd.Timedelta(hours=k), 790.0)
    assert b.halted


# ------------------------------------------------------------------ the full entry decision
def _decide(cfg=CFG, **over):
    a = closed_closes(frame(seed=1), T0 + pd.Timedelta(days=40), 721)
    base = dict(
        snap=snap(1000.0), breaker=DrawdownBreaker(cfg), regime="bull", atr_frac=0.02, candidate_closes=a,
        open_closes={}, stopped=[], pair="A/USDT", t=T0, proposed=300.0, min_stake=5.0, max_stake=1e9,
    )  # fmt: skip
    base.update(over)
    return decide_entry(cfg, **base)


def test_decision_order_and_reasons():
    ok = _decide()
    assert ok.allowed and ok.stake == pytest.approx(1000 * 0.005 / loss_fraction_at_stop(0.06, CFG))
    assert _decide(regime="bear").reason == "regime_bear"
    assert _decide(regime="unknown").reason == "regime_unknown"
    assert _decide(regime="sideways").stake == pytest.approx(ok.stake / 2)
    assert _decide(atr_frac=math.nan).reason == "no_atr"
    assert _decide(stopped=[("A/USDT", T0 - pd.Timedelta("2h"))]).reason == "pair_cooldown"
    halted = DrawdownBreaker(CFG)
    halted.update(T0, 1000.0), halted.update(T0, 700.0)
    assert _decide(breaker=halted).reason == "halted"
    warn = DrawdownBreaker(CFG)
    warn.update(T0, 1000.0), warn.update(T0, 840.0)
    assert _decide(breaker=warn).stake == pytest.approx(ok.stake / 2)


@pytest.mark.parametrize(
    "switch,over,blocked_reason",
    [
        ("regime_filter", {"regime": "bear"}, "regime_bear"),
        ("stop_cooldown", {"stopped": [("A/USDT", T0 - pd.Timedelta("1h"))]}, "pair_cooldown"),
        ("exposure_limits", {"snap": snapshot(1000.0, 0.0, [(100.0, 100.0)] * 3)}, "max_positions"),
    ],
)
def test_each_ablation_switch_removes_exactly_its_rule(switch, over, blocked_reason):
    assert _decide(**over).reason == blocked_reason
    off = RiskConfig(**{switch: False})
    assert _decide(cfg=off, **over).allowed


def test_correlation_and_breaker_ablations():
    a = closed_closes(frame(seed=1), T0 + pd.Timedelta(days=40), 721)
    over = {"open_closes": {"TWIN/USDT": a * 2}}
    assert _decide(**over).reason.startswith("corr:")
    assert _decide(cfg=RiskConfig(correlation=False), **over).allowed
    halted = DrawdownBreaker(RiskConfig(circuit_breaker=False))
    halted.update(T0, 1000.0), halted.update(T0, 100.0)
    assert _decide(cfg=RiskConfig(circuit_breaker=False), breaker=halted).allowed


def test_without_vol_sizing_the_proposed_stake_is_used_scaled_by_the_risk_factor():
    off = RiskConfig(vol_sizing=False)
    assert _decide(cfg=off).stake == pytest.approx(300.0)
    assert _decide(cfg=off, regime="sideways").stake == pytest.approx(150.0)


def test_simultaneous_entries_cannot_exceed_positions_exposure_or_cash():
    s = snapshot(1000.0, 0.0, [])
    opened = []
    for _ in range(6):  # six signals on the same candle, processed one after the other
        d = _decide(snap=s, atr_frac=0.015)
        if not d.allowed:
            break
        opened.append(d.stake)
        positions = [(c, c) for c in opened]
        s = snapshot(1000.0, 0.0, positions)
    assert len(opened) == 3
    assert sum(opened) <= 0.60 * 1000 + 1e-9 and s.cash >= 0


def test_missing_candidate_history_with_open_positions_fails_closed():
    d = _decide(
        candidate_closes=pd.Series(dtype=float), open_closes={"X/USDT": pd.Series([1.0, 2.0])}
    )
    assert not d.allowed and d.reason.startswith("corr_unverifiable")


def test_chandelier_and_exchange_minimum_constants():
    assert chandelier_stop(110.0, 2.0, 3.0) == 104.0


# ------------------------------------------------------------------ Freqtrade glue with fakes
class FakeDP:
    def __init__(self, frames):
        self.frames = frames

    def get_analyzed_dataframe(self, pair, timeframe):
        if pair not in self.frames:
            raise KeyError(pair)
        return self.frames[pair], None


def fake_trade(pair, open_rate, amount, open_date, rate_now=None, closed=None, exit_reason=None):
    cost = amount * open_rate * 1.001
    return SimpleNamespace(
        pair=pair, open_rate=open_rate, amount=amount, open_trade_value=cost, open_date_utc=open_date,
        calc_profit=lambda r, _a=amount, _c=cost: _a * r * 0.999 - _c,
        close_profit_abs=closed, exit_reason=exit_reason, close_date_utc=open_date + pd.Timedelta("5h"),
    )  # fmt: skip


@pytest.fixture
def overlay(monkeypatch):
    from freqtrade.persistence import Trade
    from trend_ema_cross_r1 import TrendEmaCrossR1

    n = 24 * 330
    frames = {
        "BTC/USDT": frame(n, seed=2, start="2023-01-01", drift=0.0004),
        "A/USDT": frame(n, seed=3, start="2023-01-01"),
        "B/USDT": frame(n, seed=4, start="2023-01-01"),
    }
    state = {"open": [], "closed": []}
    monkeypatch.setattr(
        Trade,
        "get_trades_proxy",
        staticmethod(lambda is_open=None, **k: state["open"] if is_open else state["closed"]),
    )
    strat = TrendEmaCrossR1({"dry_run_wallet": 1000})
    strat.dp = FakeDP(frames)
    t = pd.Timestamp("2023-11-20 10:00", tz="UTC")
    return strat, frames, state, t


def test_glue_sizes_confirms_and_stops_from_closed_candles(overlay):
    strat, frames, state, t = overlay
    stake = strat.custom_stake_amount("A/USDT", t, 100.0, 300.0, 5.0, 1e9, 1.0, None, "long")
    assert 0 < stake <= 200.0
    assert strat.confirm_trade_entry("A/USDT", "limit", 1.0, 100.0, "GTC", t, None, "long") is True
    # confirm without a matching sizing decision must fail closed
    assert strat.confirm_trade_entry("B/USDT", "limit", 1.0, 100.0, "GTC", t, None, "long") is False

    df = frames["A/USDT"]
    i = last_closed_index(df["date"], t)
    trade = fake_trade("A/USDT", float(df["close"].iloc[i]), 1.0, t - pd.Timedelta("3h"))
    rate = float(df["open"].iloc[i + 1])
    stop = strat.custom_stoploss("A/USDT", trade, t, rate, 0.0)
    highest = max(float(df["close"].iloc[i - 2 : i + 1].max()), trade.open_rate)
    expected = max(1 - (highest - 3 * float(df["atr"].iloc[i])) / rate, 0.0)
    assert stop == pytest.approx(expected)


def test_glue_decisions_do_not_depend_on_the_future(overlay):
    from trend_ema_cross_r1 import TrendEmaCrossR1

    strat, frames, state, t = overlay
    a = strat.custom_stake_amount("A/USDT", t, 100.0, 300.0, 5.0, 1e9, 1.0, None, "long")
    future = {k: v.copy() for k, v in frames.items()}
    for v in future.values():
        v.loc[v["date"] >= t, ["open", "high", "low", "close", "atr"]] *= 50.0
    other = TrendEmaCrossR1({"dry_run_wallet": 1000})
    other.dp = FakeDP(future)
    assert other.custom_stake_amount(
        "A/USDT", t, 100.0, 300.0, 5.0, 1e9, 1.0, None, "long"
    ) == pytest.approx(a)


def test_glue_missing_data_and_minimum_sizes_never_trade(overlay):
    strat, frames, state, t = overlay
    assert (
        strat.custom_stake_amount("ZZZ/USDT", t, 1.0, 100.0, 5.0, 1e9, 1.0, None, "long") == 0.0
    )  # no data
    assert (
        strat.custom_stake_amount("B/USDT", t, 100.0, 300.0, 5000.0, 1e9, 1.0, None, "long") == 0.0
    )  # min stake
    assert strat._denied.get("no_data") == 1 and strat._denied.get("below_min_stake") == 1


def test_glue_mark_to_market_equity_drives_the_halt_and_blocks_new_entries(overlay):
    strat, frames, state, t = overlay
    df = frames["A/USDT"]
    i = last_closed_index(df["date"], t)
    px = float(df["close"].iloc[i])
    # a position bought at 4x the current price: huge unrealised loss, nothing realised yet
    state["open"].append(
        fake_trade("B/USDT", px * 4, 1.0 * 1000 / (px * 4) * 0.9, t - pd.Timedelta("5h"))
    )
    state["open"][0].pair = "A/USDT"
    snap_ = strat._snapshot(t)
    assert snap_.equity < 1000 * 0.9 < 1000 and snap_.exposure > 0
    strat._breaker.update(t - pd.Timedelta("1h"), 1000.0)
    strat._snapshot(t + pd.Timedelta("1h"))
    assert strat._breaker.halted
    assert (
        strat.custom_stake_amount(
            "B/USDT", t + pd.Timedelta("1h"), 100.0, 300.0, 5.0, 1e9, 1.0, None, "long"
        )
        == 0.0
    )
    assert strat._denied.get("halted", 0) >= 1


def test_glue_stop_outs_create_a_pair_cooldown(overlay):
    strat, frames, state, t = overlay
    state["closed"].append(
        fake_trade(
            "A/USDT", 100.0, 1.0, t - pd.Timedelta("8h"), closed=-5.0, exit_reason="stop_loss"
        )
    )
    assert strat.custom_stake_amount("A/USDT", t, 100.0, 300.0, 5.0, 1e9, 1.0, None, "long") == 0.0
    assert strat._denied.get("pair_cooldown") == 1


def test_start_balance_comes_from_config_not_from_the_moving_wallet(overlay):
    """Regression: wallets.get_starting_balance() grows with profit in backtests (double counting)."""
    strat, _frames, _state, _t = overlay
    strat.wallets = SimpleNamespace(get_starting_balance=lambda: 1234.0)
    assert strat._start_balance() == 1000.0
