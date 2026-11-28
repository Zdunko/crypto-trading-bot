"""Stage 0 engine: costs, funds, minimum sizes, missing candles, gaps, simultaneous orders,
continuous circuit breaker, determinism and trade-level causality (with a leaky negative control)."""

import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
from synth import random_walk_ohlcv

from quantlab.causality import mutation_mismatches, restart_mismatches
from quantlab.costs import BASE, CostScenario, entry_price, exit_price
from quantlab.equity import buy_and_hold
from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run


N = 300
IDX = pd.date_range("2024-01-01", periods=N, freq="1h", tz="UTC")


def candles(seed=1, vol=0.01):
    return random_walk_ohlcv(N, seed=seed, vol=vol)


def flat(price=100.0, n=N):
    return pd.DataFrame(
        {"date": IDX[:n], "open": price, "high": price, "low": price, "close": price, "volume": 1.0}
    )


class Schedule(Strategy):
    def __init__(self, orders):
        self.orders = orders

    def on_candle(self, t, hist, view):
        return [Order(**o.__dict__) for o in self.orders.get(t, [])]


def go(sched, cdict, **kw):
    cfg = ExecConfig(**kw)
    return run(Schedule(sched), PriceData(cdict, IDX), cfg), cfg


# ------------------------------------------------------------------ costs
def test_costs_use_the_shared_price_functions_and_one_round_trip_matches_hand_calculation():
    s = CostScenario("t", fee=0.001, slippage=0.0005, stop_extra=0.0005)
    res, _ = go(
        {IDX[1]: [Order("A", "buy", notional=100.0)], IDX[5]: [Order("A", "sell")]},
        {"A": flat()},
        costs=s,
    )
    qty = 100.0 / (float(entry_price(100.0, s)) * 1.001)
    proceeds = qty * float(exit_price(100.0, s, False)) * 0.999
    tr = res.trades.iloc[0]
    assert tr["amount"] == pytest.approx(qty) and tr["profit_abs"] == pytest.approx(
        proceeds - 100.0
    )
    assert res.equity.iloc[-1] == pytest.approx(1000.0 + proceeds - 100.0)


def test_buy_and_hold_matches_the_legacy_benchmark_within_the_documented_valuation_difference():
    cd = {"A": candles(1), "B": candles(2)}
    n = len(cd)
    sched = {IDX[0]: [Order(p, "buy", notional=1000.0 / n) for p in cd]}
    res, _ = go(sched, cd, breaker=False)
    legacy, _ = buy_and_hold(cd, IDX, 1000.0, BASE)
    assert np.allclose(res.equity.to_numpy(), legacy.to_numpy(), rtol=2e-6)  # (1-s)(1-f) vs 1-s-f


# ------------------------------------------------------------------ funds and minimum sizes
def test_below_minimum_notional_is_rejected_never_rounded_up():
    res, _ = go({IDX[1]: [Order("A", "buy", notional=4.99)]}, {"A": flat()}, min_notional=5.0)
    assert res.trades.empty and res.rejects[0]["reason"] == "below_min_notional"


def test_insufficient_funds_clip_to_cash_then_reject_when_nothing_usable_is_left():
    sched = {IDX[1]: [Order("A", "buy", notional=900.0), Order("B", "buy", notional=300.0),
                      Order("C", "buy", notional=300.0)]}  # fmt: skip
    res, _ = go(sched, {"A": flat(), "B": flat(), "C": flat()}, wallet=1000.0)
    spent = {k: p.open_value for k, p in res.state.positions.items()}
    assert spent["A"] == pytest.approx(900.0) and spent["B"] == pytest.approx(100.0)  # clipped
    assert [r["reason"] for r in res.rejects] == ["insufficient_funds"]  # C: no cash left
    assert res.state.cash == pytest.approx(0.0, abs=1e-9)


def test_simultaneous_orders_are_deterministic_sells_first_then_priority_then_pair():
    sched = {
        IDX[1]: [Order("A", "buy", notional=800.0)],
        IDX[3]: [Order("B", "buy", notional=700.0, priority=1), Order("C", "buy", notional=700.0, priority=0),
                 Order("A", "sell")],
    }  # fmt: skip
    res, _ = go(sched, {"A": flat(), "B": flat(), "C": flat()})
    # the sell frees cash first; C (priority 0) is served before B (priority 1)
    assert "C" in res.state.positions and res.state.positions["C"].open_value == pytest.approx(
        700.0
    )
    assert res.state.positions["B"].open_value < 700.0  # only what is left


def test_a_second_buy_in_an_open_pair_is_rejected_no_pyramiding():
    res, _ = go({IDX[1]: [Order("A", "buy", notional=100.0)], IDX[2]: [Order("A", "buy", notional=100.0)]},
                {"A": flat()})  # fmt: skip
    assert res.rejects[0]["reason"] == "already_open"


# ------------------------------------------------------------------ missing candles
def holes(df, rows):
    return df.drop(index=list(rows)).reset_index(drop=True)


def test_order_on_a_missing_candle_waits_and_fills_on_the_next_one():
    cd = {"A": holes(flat(), [5])}
    res, _ = go({IDX[5]: [Order("A", "buy", notional=100.0)]}, cd)
    assert res.state.positions["A"].open_time == IDX[6] and not res.rejects


def test_order_expires_after_max_defer_candles_and_is_logged():
    cd = {"A": holes(flat(), range(5, 12))}
    res, _ = go({IDX[5]: [Order("A", "buy", notional=100.0)]}, cd, max_defer=3)
    assert "A" not in res.state.positions and res.rejects[-1]["reason"] == "expired"


def test_positions_are_valued_at_the_last_known_close_across_a_hole_and_stops_wait():
    df = flat()
    df.loc[10, ["open", "high", "low", "close"]] = np.nan
    cd = {"A": holes(df.dropna(subset=["open"]), [])}
    cd["A"] = cd["A"].reset_index(drop=True)
    res, _ = go({IDX[1]: [Order("A", "buy", notional=100.0, stop_pct=0.1)]}, cd)
    assert not res.equity.isna().any() and "A" in res.state.positions


# ------------------------------------------------------------------ gaps and stops
def gap_frame(open_after, high_after):
    df = flat()
    df.loc[20:, ["open", "high", "low", "close"]] = open_after
    df.loc[20, "high"] = high_after
    return df


def test_gap_through_the_stop_fills_at_the_open_conservatively_and_at_the_stop_in_freqtrade_mode():
    # stop = 90; candle 20 opens at 80 but its high (95) is back above the stop
    cd = {"A": gap_frame(80.0, 95.0)}
    sched = {IDX[1]: [Order("A", "buy", notional=100.0, stop_pct=0.10)]}
    cons, _ = go(sched, cd, stop_fill="conservative", costs=CostScenario("n", 0.0, 0.0, 0.0))
    nat, _ = go(sched, cd, stop_fill="freqtrade", costs=CostScenario("n", 0.0, 0.0, 0.0))
    assert cons.trades.iloc[0]["close_rate"] == 80.0
    assert nat.trades.iloc[0]["close_rate"] == pytest.approx(
        90.0
    )  # documented optimism of Freqtrade
    # whole candle below the stop: both rules fill at the open
    cd2 = {"A": gap_frame(80.0, 85.0)}
    assert go(sched, cd2, stop_fill="freqtrade")[0].trades.iloc[0]["close_rate"] == 80.0


def test_stop_exit_pays_the_extra_stop_slippage_and_is_labelled_stop_loss():
    s = CostScenario("t", 0.001, 0.0005, 0.0005)
    res, _ = go(
        {IDX[1]: [Order("A", "buy", notional=100.0, stop_pct=0.10)]},
        {"A": gap_frame(80.0, 85.0)},
        costs=s,
    )
    tr = res.trades.iloc[0]
    assert tr["exit_reason"] == "stop_loss"
    assert tr["profit_abs"] == pytest.approx(tr["amount"] * 80.0 * (1 - 0.001) * 0.999 - 100.0)


# ------------------------------------------------------------------ continuous breaker
def crash_frame(at, level):
    df = flat()
    df.loc[at:, ["open", "high", "low", "close"]] = level
    return df


def test_breaker_monitors_every_candle_halts_and_flattens_at_the_next_open():
    cd = {"A": crash_frame(50, 70.0)}  # -30 % on a fully invested account -> far beyond 20 %
    res, _ = go({IDX[1]: [Order("A", "buy", notional=990.0)]}, cd, costs=CostScenario("n", 0, 0, 0))
    assert res.breaker_events and res.breaker_events[0]["type"] == "halt"
    t_halt = pd.Timestamp(res.breaker_events[0]["time"])
    assert (
        t_halt == IDX[51]
    )  # crash candle 50 closes low; detected on the first candle after the crash closes, not at an entry
    assert (
        res.trades.iloc[0]["exit_reason"] == "halt" and res.trades.iloc[0]["close_date"] == IDX[51]
    )
    assert not res.state.positions


def test_halt_blocks_new_entries_and_is_latched_even_if_price_recovers():
    df = flat()
    df.loc[50:60, ["open", "high", "low", "close"]] = 70.0  # crash then full recovery
    sched = {
        IDX[1]: [Order("A", "buy", notional=990.0)],
        IDX[100]: [Order("A", "buy", notional=100.0)],
    }
    res, _ = go(sched, {"A": df}, costs=CostScenario("n", 0, 0, 0))
    assert any(r["reason"] == "halted" for r in res.rejects) and "A" not in res.state.positions


def test_hold_policy_keeps_positions_after_a_halt_but_still_blocks_buys():
    cd = {"A": crash_frame(50, 70.0), "B": flat()}
    sched = {
        IDX[1]: [Order("A", "buy", notional=990.0)],
        IDX[60]: [Order("B", "buy", notional=5.0)],
    }
    res, _ = go(sched, cd, halt_action="hold", costs=CostScenario("n", 0, 0, 0))
    assert "A" in res.state.positions and any(r["reason"] == "halted" for r in res.rejects)


def test_only_an_owner_approval_timestamp_resumes_trading_and_resets_the_peak():
    cd = {"A": crash_frame(50, 70.0), "B": flat()}
    sched = {
        IDX[1]: [Order("A", "buy", notional=990.0)],
        IDX[100]: [Order("B", "buy", notional=100.0)],
    }
    cfg = {"costs": CostScenario("n", 0, 0, 0)}
    res, _ = go(sched, cd, **cfg)
    assert "B" not in res.state.positions  # terminal without approval
    ok = run(Schedule(sched), PriceData(cd, IDX), ExecConfig(**cfg), approvals=[IDX[90]])
    assert "B" in ok.state.positions and [e["type"] for e in ok.breaker_events] == [
        "halt",
        "resume",
    ]


def test_reduce_threshold_halves_the_risk_multiplier_seen_by_the_strategy():
    seen = []

    class Probe(Strategy):
        def on_candle(self, t, hist, view):
            seen.append(view.risk_multiplier)
            return [Order("A", "buy", notional=990.0)] if t == IDX[1] else []

    df = flat()
    df.loc[30:, ["open", "high", "low", "close"]] = 84.0  # -16 %: reduce, no halt
    run(Probe(), PriceData({"A": df}, IDX), ExecConfig(costs=CostScenario("n", 0, 0, 0)))
    assert 0.5 in seen and 0.0 not in seen and seen[0] == 1.0


# ------------------------------------------------------------------ determinism
def test_identical_inputs_give_identical_hashes_in_process_and_across_processes():
    cd = {"A": candles(1), "B": candles(2)}
    sched = {IDX[3]: [Order("A", "buy", notional=300.0, stop_pct=0.05)], IDX[9]: [Order("B", "buy", notional=200.0)],
             IDX[40]: [Order("A", "sell")]}  # fmt: skip
    h1 = go(sched, cd)[0].hash
    assert h1 == go(sched, cd)[0].hash
    assert len(h1) == 64


# ------------------------------------------------------------------ trade-level causality
class Momentum(Strategy):
    """Stateful, causal: buys after two up closes, cools down 5 candles after any exit."""

    def __init__(self):
        self.last_exit = -99

    def on_candle(self, t, hist, view):
        out = []
        i = len(hist.times)
        for p in hist.pairs:
            c = hist.closes(p, 3)
            if len(c) < 3 or np.isnan(c).any():
                continue
            if p in view.positions and c[-1] < c[-2]:
                out.append(Order(p, "sell"))
                self.last_exit = i
            elif p not in view.positions and c[-1] > c[-2] > c[-3] and i - self.last_exit > 5:
                out.append(Order(p, "buy", notional=150.0 * view.risk_multiplier, stop_pct=0.05))
        return out


class Leaky(Momentum):
    """Negative control: peeks at the CURRENT candle's close through a back door."""

    def __init__(self, data):
        super().__init__()
        self.data = data

    def on_candle(self, t, hist, view):
        i = len(hist.times)
        out = []
        for p in hist.pairs:
            j = self.data.col[p]
            if self.data.close[i, j] > self.data.open[i, j]:
                out.append(Order(p, "buy", notional=100.0))
        return out


@pytest.mark.parametrize("k", [60, 140, 220])
def test_mutating_the_future_never_changes_orders_up_to_and_including_that_candle(k):
    cd = {"A": candles(1), "B": candles(2), "C": candles(3)}
    assert mutation_mismatches(lambda d: Momentum(), cd, IDX, ExecConfig(breaker=False), k) == []
    assert (
        mutation_mismatches(lambda d: Momentum(), cd, IDX, ExecConfig(), k) == []
    )  # breaker on too


def test_leaky_strategy_is_caught_by_the_same_mutation_test():
    cd = {"A": candles(1), "B": candles(2)}

    def with_candle_100(up):
        out = {}
        for p, df in cd.items():
            d = df.copy()
            d.loc[100, "close"] = d.loc[100, "open"] * (1.5 if up else 0.5)
            out[p] = d
        return out

    d1, d2 = PriceData(with_candle_100(True), IDX), PriceData(with_candle_100(False), IDX)
    a = run(Leaky(d1), d1, ExecConfig(breaker=False))
    b = run(Leaky(d2), d2, ExecConfig(breaker=False))
    assert [o for o in a.orders if o["i"] <= 100] != [o for o in b.orders if o["i"] <= 100]


def test_state_injection_restart_reproduces_the_full_run_exactly():
    cd = {"A": candles(1), "B": candles(2), "C": candles(3)}
    data = PriceData(cd, IDX)

    def carry(strat, head):  # strategy-internal memory: index of the last exit
        sells = [o["i"] for o in head.orders if o["side"] == "sell"]
        strat.last_exit = max(sells, default=-99)

    for k in (60, 120, 200):
        assert restart_mismatches(Momentum, carry, data, ExecConfig(), k) == []


def test_a_fresh_start_without_the_state_differs_which_is_what_lookahead_analysis_mistakes_for_bias():
    cd = {"A": candles(1), "B": candles(2), "C": candles(3)}
    data = PriceData(cd, IDX)
    full = run(Momentum(), data, ExecConfig())
    fresh = run(Momentum(), data, ExecConfig(), start=120)  # no cash/positions/peak carried over
    assert [o for o in fresh.orders] != [
        o for o in full.orders if o["i"] >= 120
    ] or not np.allclose(fresh.equity.to_numpy(), full.equity.iloc[120:].to_numpy())


def test_cross_process_determinism(tmp_path):
    script = tmp_path / "child.py"
    script.write_text(
        "import sys\nsys.path[:0]=['quant','quant/tests']\n"
        "import pandas as pd\nfrom synth import random_walk_ohlcv\n"
        "from quantlab.execution import *\n"
        "IDX=pd.date_range('2024-01-01',periods=300,freq='1h',tz='UTC')\n"
        "cd={'A':random_walk_ohlcv(300,seed=1,vol=0.01),'B':random_walk_ohlcv(300,seed=2,vol=0.01)}\n"
        "class S(Strategy):\n"
        "    def on_candle(self,t,h,v):\n"
        "        return [Order('A','buy',notional=300.0,stop_pct=0.05)] if len(h.times)==3 else ([Order('A','sell')] if len(h.times)==40 else [])\n"
        "print(run(S(),PriceData(cd,IDX),ExecConfig()).hash)\n"
    )
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    outs = {
        subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, cwd=root, check=True
        ).stdout.strip()
        for _ in range(2)
    }
    assert len(outs) == 1 and len(next(iter(outs))) == 64
