"""S6: benchmarks on the frozen-style point-in-time dataset loader (synthetic archive): identity transitions,
stale/ended assets, quarantined data, holdout dates. Fail closed, nothing silently skipped."""

from __future__ import annotations

import pandas as pd
import pytest
import synth_pit
from synth_pit import HOUR, build, csv_zip, row

from quantlab import benchmarks as bm
from quantlab import data_audit as da
from quantlab import pit_loader as pl
from quantlab.execution import ExecConfig, run


DAY = synth_pit.DAY


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def jump_archive(variant="base"):
    """AAA jumps x20 on 2020-12-20 (identity transition); BBB stops printing candles on 2020-12-20."""
    from quantlab import pit_fetch as pf

    spec = {
        "AAAUSDT": (["2020-10", "2020-11", "2020-12", "2021-01"], None),
        "BBBUSDT": (["2020-10", "2020-11", "2020-12"], 20),
    }
    objs, listing = {}, {}
    for sym, (months, last_days) in spec.items():
        listing[sym] = months
        for m in months:
            for itv, step in (("1d", DAY), ("1h", HOUR)):
                lo, hi = da.month_bounds_ms(m)
                n = (
                    (hi - lo) // step
                    if not (last_days and m == months[-1])
                    else last_days * (24 if itv == "1h" else 1)
                )
                rows = []
                for i in range(n):
                    t = lo + i * step
                    px = 1.0
                    if sym == "AAAUSDT" and t >= da.month_bounds_ms("2020-12")[0] + 19 * DAY:
                        px = 20.0
                    rows.append(row(t, px, 5e6 / (24 if itv == "1h" else 1) / px))
                objs[f"{pf.KLINES}{sym}/{itv}/{sym}-{itv}-{m}.zip"] = csv_zip(rows)
    return objs, listing


@pytest.fixture(scope="module")
def jump_ds(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(synth_pit, "archive", jump_archive)
    try:
        out, store, freeze = synth_pit.build(tmp_path_factory.mktemp("jump"), "jump")
    finally:
        mp.undo()
    return pl.PitDataset.open(out, store, freeze)


def test_identity_transition_ends_membership_and_stale_assets_are_held_but_reported_stuck(jump_ds):
    ds = jump_ds
    uni = bm.PitUniverse(ds)
    assert {"AAA/USDT", "BBB/USDT"} <= uni(ts("2020-12-05"))
    jan = uni(ts("2021-01-05"))
    assert (
        "AAA/USDT" not in jan
    )  # new epoch since 2020-12-20: history restarts, not a member in January
    assert "BBB/USDT" not in jan  # stale: last candle 2020-12-20
    syms = ["AAAUSDT", "BBBUSDT"]
    data = pl.to_price_data(ds, syms, "1d", ts("2020-12-01"), ts("2021-01-31"))
    res = run(bm.PitEqualWeight(uni), data, ExecConfig(wallet=1000.0))
    bought = {o["pair"] for o in res.orders if o["side"] == "buy"}
    assert {"AAA/USDT", "BBB/USDT"} <= bought
    assert (
        "AAA/USDT" not in res.state.positions
    )  # sold at the January rebalance (it still prints candles)
    assert "BBB/USDT" in res.state.positions  # no candles after 2020-12-20: cannot be sold
    last = {
        p: data.index[
            max(
                i
                for i in range(len(data.index))
                if data.close[i, data.col[p]] == data.close[i, data.col[p]]
            )
        ]
        for p in data.pairs
    }
    stuck = bm.stuck_positions(res, last, data.index[-1], pd.Timedelta(days=3))
    assert [s["pair"] for s in stuck] == ["BBB/USDT"]
    assert uni.errors == []


def test_loader_errors_make_the_universe_empty_and_are_recorded(jump_ds):
    uni = bm.PitUniverse(jump_ds)
    assert uni(ts("2025-07-01")) == set() and uni(ts("2026-01-01")) == set()
    assert [e["error"] for e in uni.errors] == ["HoldoutError", "HoldoutError"]
    res = run(
        bm.PitEqualWeight(bm.PitUniverse(jump_ds, max_stale_days=-1)),
        pl.to_price_data(jump_ds, ["AAAUSDT"], "1d", ts("2020-12-01"), ts("2021-01-10")),
        ExecConfig(wallet=1000.0),
    )
    assert res.orders == [] and (res.equity == 1000.0).all()  # nothing qualifies -> cash


def test_quarantined_data_stops_the_benchmark_before_it_starts(tmp_path):
    q = build(tmp_path, "quarantine")
    ds = pl.PitDataset.open(*q)
    with pytest.raises(pl.DataQuarantined):
        pl.to_price_data(ds, ["AAAUSDT"], "1d", ts("2020-10-15"), ts("2021-01-10"))
