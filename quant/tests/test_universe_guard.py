"""S5 universe guard with the Stage 0 engine and the risk wrapper (L4, L6). Synthetic data, no network."""

from __future__ import annotations

import socket
from types import SimpleNamespace

import pandas as pd
import pytest
from synth_pit import build

from quantlab import pit_loader as pl
from quantlab.execution import ExecConfig, Order, Strategy, run
from quantlab.risk_v2 import RiskManagedStrategy, RiskStateMachine, RiskV2Config
from quantlab.universe_guard import UniverseGuard


NO_POS = SimpleNamespace(positions={})


def ts(s):
    return pd.Timestamp(s, tz="UTC")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return build(tmp_path_factory.mktemp("guard"), "base")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", boom)


class BuyEach(Strategy):
    """Tries to hold each pair: a buy whenever the pair is not held (add=True keeps trying when held)."""

    def __init__(self, pairs, add=False):
        self.pairs, self.add = pairs, add

    def on_candle(self, t, hist, view):
        return [
            Order(p, "buy", notional=100.0, add=self.add)
            for p in self.pairs
            if self.add or p not in view.positions
        ]


def engine(strategy, ds, symbols, start="2020-12-01", end="2021-01-20"):
    data = pl.to_price_data(ds, symbols, "1h", ts(start), ts(end))
    return run(strategy, data, ExecConfig())


def open_ds(base, store=True):
    out, root, freeze = base
    return pl.PitDataset.open(out, root if store else None, freeze)


def test_non_members_are_blocked_with_reasons_and_members_trade(base):
    ds = open_ds(base)
    g = UniverseGuard(BuyEach(["AAA/USDT", "BBB/USDT", "ADAUP/USDT"]), ds)
    res = engine(g, ds, ["AAAUSDT", "BBBUSDT", "ADAUPUSDT"])
    assert set(res.state.positions) == {"AAA/USDT", "BBB/USDT"}
    assert {b["pair"] for b in g.blocked} == {"ADAUP/USDT"}
    assert {b["reason"] for b in g.blocked} == {
        "not_member"
    }  # explicit classification, leveraged token


def test_held_positions_are_not_force_sold_when_the_asset_leaves_the_universe(base):
    ds = open_ds(base)
    g = UniverseGuard(BuyEach(["BBB/USDT"], add=True), ds)  # keeps trying to add to BBB
    res = engine(g, ds, ["BBBUSDT"])
    assert (
        "BBB/USDT" in res.state.positions
    )  # BBB stopped trading on 2020-12-20; the guard never sells it
    reasons = {b["reason"] for b in g.blocked}
    assert {
        "stale",
        "not_member",
    } <= reasons  # first stale in December, then not a member in January
    assert all(b["t"] >= "2020-12-1" for b in g.blocked)


def test_sells_and_stops_always_pass_and_unknown_pairs_fail_closed(base):
    ds = open_ds(base)

    class Mixed(Strategy):
        def on_candle(self, t, hist, view):
            return [Order("AAA/USDT", "sell"), Order("FOO/USDT", "buy", notional=50.0),
                    Order("AAA/USDT", "set_stop", stop=0.5), Order("ADAUP/USDT", "buy", notional=50.0)]  # fmt: skip

    g = UniverseGuard(Mixed(), ds)
    out = g.on_candle(ts("2021-01-10"), None, None)
    assert [o.side for o in out] == ["sell", "set_stop"]
    assert {(b["pair"], b["reason"]) for b in g.blocked} == {
        ("FOO/USDT", "loader_error:UnknownSymbol"),
        ("ADAUP/USDT", "not_member"),
    }


def test_loader_failure_blocks_every_buy_but_not_sells(base):
    ds = open_ds(base, store=False)  # no raw store: freshness cannot be established
    g = UniverseGuard(BuyEach(["AAA/USDT"]), ds)
    out = g.on_candle(ts("2021-01-10"), None, NO_POS)
    assert out == [] and g.blocked == [
        {"t": str(ts("2021-01-10")), "pair": "AAA/USDT", "reason": "loader_error:DataMissing"}
    ]

    class Seller(Strategy):
        def on_candle(self, t, hist, view):
            return [Order("AAA/USDT", "sell")]

    assert [
        o.side for o in UniverseGuard(Seller(), ds).on_candle(ts("2021-01-10"), None, NO_POS)
    ] == ["sell"]


def test_guard_is_transparent_when_every_pair_is_a_member(base):
    ds = open_ds(base)
    plain = engine(BuyEach(["AAA/USDT"]), ds, ["AAAUSDT"])
    guarded = engine(UniverseGuard(BuyEach(["AAA/USDT"]), ds), ds, ["AAAUSDT"])
    assert plain.hash == guarded.hash and len(plain.trades) == len(guarded.trades)


def test_composition_with_the_risk_wrapper_is_deterministic(base):
    ds = open_ds(base)

    def make():
        machine = RiskStateMachine.new(RiskV2Config(), 1000.0)
        return UniverseGuard(RiskManagedStrategy(BuyEach(["AAA/USDT", "ADAUP/USDT"]), machine), ds)

    a = engine(make(), ds, ["AAAUSDT", "ADAUPUSDT"])
    b = engine(make(), ds, ["AAAUSDT", "ADAUPUSDT"])
    assert a.hash == b.hash and set(a.state.positions) == {"AAA/USDT"}
