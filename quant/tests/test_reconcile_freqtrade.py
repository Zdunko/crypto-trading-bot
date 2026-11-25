"""Reconcile the Stage 0 engine with native Freqtrade backtesting on synthetic fixtures.

Equivalent execution assumptions: signal on candle j fills at the open of j+1; fixed stake of 100;
stop = fill price - 10 %; Freqtrade fee = the engine's lumped per-side rate (fee + slippage);
``stop_extra`` = 0 (Freqtrade cannot model it); ``stop_fill="freqtrade"`` (its gap rule).
Uses upstream test helpers read-only (nothing upstream is modified).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synth import random_walk_ohlcv

from quantlab.costs import CostScenario
from quantlab.execution import ExecConfig, Order, PriceData, Strategy, run


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

N = 200
IDX = pd.date_range("2024-01-01", periods=N, freq="1h", tz="UTC")
PAIRS = ["BTC/USDT", "ETH/USDT", "TKN/USDT", "XRP/USDT"]

# (pair, entry signal row, exit signal row or None). A and B enter on the SAME candle (simultaneous).
SIGNALS = [
    ("BTC/USDT", 10, 40),
    ("ETH/USDT", 10, None),
    ("TKN/USDT", 30, None),
    ("XRP/USDT", 60, None),
]

STRATEGY_SRC = '''
import json
from freqtrade.strategy import IStrategy

SCHEDULE = json.loads(r"""{schedule}""")


class FixtureStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    minimal_roi = {{"0": 100}}
    stoploss = -0.10
    startup_candle_count = 0
    use_exit_signal = True
    process_only_new_candles = True

    def populate_indicators(self, dataframe, metadata):
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[dataframe.index.isin(SCHEDULE[metadata["pair"]]["entry"]), "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[dataframe.index.isin(SCHEDULE[metadata["pair"]]["exit"]), "exit_long"] = 1
        return dataframe
'''


def fixture_candles():
    out = {}
    for k, pair in enumerate(PAIRS):
        df = random_walk_ohlcv(N, seed=10 + k, vol=0.004)
        out[pair] = df
    # B: stop is crossed intrabar on candle 25 (low below stop, open above it)
    b = out["ETH/USDT"]
    fill_b = float(b.loc[11, "open"])
    b.loc[25, "low"] = fill_b * 0.85
    # C: whole candle 45 gaps below the stop -> both rules fill at the open
    c = out["TKN/USDT"]
    fill_c = float(c.loc[31, "open"])
    for col, mult in (("open", 0.80), ("high", 0.808), ("low", 0.792), ("close", 0.80)):
        c.loc[45:, col] = fill_c * mult
    # D: candle 80 opens far below the stop but its high is back above it (rules differ here)
    d = out["XRP/USDT"]
    fill_d = float(d.loc[61, "open"])
    d.loc[80, ["open", "low"]] = fill_d * 0.80
    d.loc[80, "high"] = fill_d * 0.97
    d.loc[80, "close"] = fill_d * 0.90
    for col, mult in (("open", 0.90), ("high", 0.909), ("low", 0.891), ("close", 0.90)):
        d.loc[81:, col] = fill_d * mult
    return out


class FixtureEngineStrategy(Strategy):
    # Freqtrade's stake_amount of 100 buys 100 USDT of coins and the fee comes on top, while the
    # engine's notional includes costs: equivalent notional = 100 * (1 + slippage) * (1 + fee).
    def __init__(self, fee, slip):
        self.notional = 100.0 * (1 + slip) * (1 + fee)

    def on_candle(self, t, hist, view):
        i = len(hist.times)  # fills at the open of candle i; the signal row was i-1
        out = []
        for pair, entry, exit_ in SIGNALS:
            if i == entry + 1:
                out.append(Order(pair, "buy", notional=self.notional, stop_pct=0.10))
            if exit_ is not None and i == exit_ + 1 and pair in view.positions:
                out.append(Order(pair, "sell"))
        return out


@pytest.fixture(autouse=True)
def restore_freqtrade_globals():
    """Backtesting switches Trade to in-memory backtest mode globally; upstream tests (which share
    the process under ``pytest --random-order -n auto``) must not inherit that state."""
    yield
    from freqtrade.optimize.backtesting import Backtesting
    from freqtrade.persistence import PairLocks, Trade

    Backtesting.cleanup()
    Trade.reset_trades()
    PairLocks.reset_locks()


def native_trades(mocker, tmp_path, candles, fee):
    from freqtrade.configuration import TimeRange
    from freqtrade.data.converter import trim_dataframes
    from freqtrade.optimize.backtesting import Backtesting
    from tests.conftest import EXMS, get_default_conf_usdt, patch_exchange

    sched = {p: {"entry": [e], "exit": [x] if x is not None else []} for p, e, x in SIGNALS}
    (tmp_path / "fixture_strategy.py").write_text(STRATEGY_SRC.format(schedule=json.dumps(sched)))
    conf = get_default_conf_usdt(tmp_path)
    for key in ("minimal_roi", "stoploss", "trailing_stop"):
        conf.pop(key, None)
    conf.update({
        "strategy": "FixtureStrategy", "strategy_path": str(tmp_path), "timeframe": "1h",
        "max_open_trades": 4, "stake_amount": 100, "dry_run_wallet": 1000, "fee": fee,
        "datadir": tmp_path, "export": "none", "timerange": "20240101-20240110",
    })  # fmt: skip
    conf["exchange"] = {**conf["exchange"], "pair_whitelist": PAIRS}
    mocker.patch(f"{EXMS}.get_fee", return_value=fee)
    patch_exchange(mocker)
    bt = Backtesting(conf)
    bt._set_strategy(bt.strategylist[0])
    data = {p: df.copy() for p, df in candles.items()}
    processed = bt.strategy.advise_all_indicators(data)
    tr = TimeRange.parse_timerange("20240101-20240110")
    processed = trim_dataframes(processed, tr, bt.required_startup)
    res = bt.backtest(
        processed=processed, start_date=IDX[0].to_pydatetime(), end_date=IDX[-1].to_pydatetime()
    )
    return res["results"].sort_values(["pair", "open_date"]).reset_index(drop=True)


def engine_trades(candles, fee, slip, stop_fill):
    pd_ = PriceData({p.replace("/USDT", "/USDT"): df for p, df in candles.items()}, IDX)
    cfg = ExecConfig(costs=CostScenario("rec", fee, slip, 0.0), stop_fill=stop_fill, breaker=False)
    res = run(FixtureEngineStrategy(fee, slip), pd_, cfg)
    return res, res.trades.sort_values(["pair", "open_date"]).reset_index(drop=True)


@pytest.mark.parametrize("fee,slip", [(0.001, 0.0), (0.001, 0.0005)])
def test_engine_reproduces_native_freqtrade_on_synthetic_fixtures(mocker, tmp_path, fee, slip):
    candles = fixture_candles()
    nat = native_trades(mocker, tmp_path, candles, fee + slip)
    _, eng = engine_trades(candles, fee, slip, "freqtrade")
    assert len(nat) == len(eng) == 4
    assert list(nat["pair"]) == list(eng["pair"])
    for col_n, col_e in (("open_date", "open_date"), ("close_date", "close_date")):
        assert [pd.Timestamp(x) for x in nat[col_n]] == [pd.Timestamp(x) for x in eng[col_e]]
    np.testing.assert_allclose(
        nat["open_rate"], eng["open_rate"], rtol=1e-6
    )  # Freqtrade rounds to exchange precision
    np.testing.assert_allclose(nat["close_rate"], eng["close_rate"], rtol=1e-6)
    # profit agrees within 5e-4 USDT (measured max 3.3e-4) on a 100 USDT stake (exchange rounding; with slippage also the
    # cross term slip*fee ~ 5e-7 of notional)
    np.testing.assert_allclose(nat["profit_abs"], eng["profit_abs"], atol=5e-4)
    assert set(eng["exit_reason"]) <= {"stop_loss", "exit_signal", "signal"}


def test_the_conservative_stop_rule_differs_from_freqtrade_only_on_the_gap_that_recovers(
    mocker, tmp_path
):
    candles = fixture_candles()
    _, native_rule = engine_trades(candles, 0.001, 0.0, "freqtrade")
    _, cons = engine_trades(candles, 0.001, 0.0, "conservative")
    diff = native_rule.merge(cons, on="pair", suffixes=("_f", "_c"))
    changed = diff[~np.isclose(diff["close_rate_f"], diff["close_rate_c"])]
    assert list(changed["pair"]) == ["XRP/USDT"]  # the documented optimism of Freqtrade's gap rule
    assert (changed["close_rate_c"] < changed["close_rate_f"]).all()
