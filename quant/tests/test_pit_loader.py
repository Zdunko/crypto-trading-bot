"""S5 loader: fail-closed modes (L1), causality (L2), determinism (L3). Synthetic data only, no network."""

from __future__ import annotations

import gzip
import random
import socket
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from synth_pit import build

from quantlab import pit_loader as pl


U = "UTC"


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pit")
    return build(tmp, "base")


@pytest.fixture
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def open_ds(base):
    out, store, freeze = base
    return pl.PitDataset.open(out, store, freeze)


def ts(s):
    return pd.Timestamp(s, tz=U)


# ------------------------------------------------------------------ L1 fail-closed
def test_opens_and_serves_members_and_candles(base, no_network):
    ds = open_ds(base)
    assert ds.universe_at(ts("2021-01-15")) == ["AAAUSDT"] or "AAAUSDT" in ds.universe_at(
        ts("2021-01-15")
    )
    assert "ADAUPUSDT" not in ds.universe_at(
        ts("2021-01-15")
    )  # explicit classification, not a regex
    df = ds.candles("AAAUSDT", "1d", ts("2021-01-10"))
    assert df["date"].iloc[-1] == ts("2021-01-09") and df["date"].is_monotonic_increasing
    # completed candles only: the candle opening 2021-01-09 closes at 2021-01-10 00:00 and is the last one
    assert (df["date"] + pd.Timedelta(days=1) <= ts("2021-01-10")).all()
    h = ds.candles("AAAUSDT", "1h", ts("2021-01-02 05:30"))
    assert h["date"].iloc[-1] == ts("2021-01-02 04:00")


def test_freeze_mismatches_are_refused(base, tmp_path):
    out, store, freeze = base
    with pytest.raises(pl.FreezeMismatch):
        pl.PitDataset.open(out, store, {**freeze, "dataset_hash": "0" * 64})
    with pytest.raises(pl.FreezeMismatch):
        pl.PitDataset.open(
            out,
            store,
            {**freeze, "files": {**freeze["files"], "dev_window_listing.json": "0" * 64}},
        )
    import shutil

    alt = tmp_path / "alt"
    shutil.copytree(out, alt)
    mem = alt / "membership.csv.gz"
    with gzip.open(mem, "rt", newline="") as f:
        text = f.read()
    with gzip.open(mem, "wt", newline="") as f:
        f.write(text + "2021-01,1M,AAAUSDT#9,0\n")  # an extra member smuggled into the table
    with pytest.raises(pl.FreezeMismatch):
        pl.PitDataset.open(alt, store, freeze)


def test_dates_outside_the_window_are_refused(base):
    ds = open_ds(base)
    for bad in ("2025-07-01", "2025-07-02 12:00", "2026-01-01"):
        with pytest.raises(pl.HoldoutError):
            ds.universe_at(ts(bad))
        with pytest.raises(pl.HoldoutError):
            ds.candles("AAAUSDT", "1d", ts(bad))
    with pytest.raises(pl.PitError):
        ds.universe_at(ts("2017-01-01"))
    with pytest.raises(pl.PitError):
        ds.universe_at(pd.Timestamp("2021-01-15"))  # naive timestamp


def test_unknown_symbol_and_missing_table(base):
    ds = open_ds(base)
    with pytest.raises(pl.UnknownSymbol):
        ds.candles("ZZZUSDT", "1d", ts("2021-01-10"))
    with pytest.raises(pl.PitError):
        ds.universe_at(ts("2021-01-15"), threshold="25M")


def test_stale_members_are_excluded_point_in_time(base):
    ds = open_ds(base)
    assert "BBBUSDT" in ds.universe_at(ts("2020-12-10"))  # still trading
    # at the 2021-01 month start BBB's last candle (2020-12-20) is 11 days old
    assert "BBBUSDT" not in ds.universe_at(ts("2021-01-15"), max_stale_days=3)
    assert "BBBUSDT" in ds.universe_at(ts("2021-01-15"), max_stale_days=30)
    ok, why = ds.tradable("BBBUSDT", ts("2021-01-15"))
    assert not ok and why == "not_member"
    ok, why = ds.tradable("AAAUSDT", ts("2021-01-15"))
    assert ok and why == "ok"
    ok, why = ds.tradable(
        "BBBUSDT", ts("2020-12-31"), max_stale_days=3
    )  # member but 10 days stale now
    assert not ok and why == "stale"


def test_quarantined_absent_altered_and_deleted_data_raise(tmp_path):
    q = build(tmp_path, "quarantine")
    ds = pl.PitDataset.open(*q)
    with pytest.raises(pl.DataQuarantined):
        ds.candles("AAAUSDT", "1d", ts("2021-01-10"))  # range includes the quarantined 2020-11
    assert (
        len(ds.candles("AAAUSDT", "1d", ts("2021-01-10"), start=ts("2020-12-01"))) == 40
    )  # later start is fine
    g = build(tmp_path, "gap")
    dsg = pl.PitDataset.open(*g)
    with pytest.raises(pl.DataMissing):
        dsg.candles("AAAUSDT", "1d", ts("2021-01-10"))
    assert len(dsg.candles("AAAUSDT", "1d", ts("2021-01-10"), allow_gaps=True)) > 0
    # altered stored file (hash differs) and deleted stored file
    out, store, freeze = build(tmp_path, "base")
    ds2 = pl.PitDataset.open(out, store, freeze)
    z = ds2.store.paths("AAAUSDT", "1d", "2020-12")[0]
    z.write_bytes(z.read_bytes() + b"x")
    with pytest.raises(pl.IntegrityError):
        ds2.candles("AAAUSDT", "1d", ts("2021-01-10"))
    z.unlink()
    with pytest.raises(pl.DataMissing):
        ds2.candles("AAAUSDT", "1d", ts("2021-01-10"))
    ds3 = pl.PitDataset.open(out, None, freeze)
    with pytest.raises(pl.DataMissing):
        ds3.candles("AAAUSDT", "1d", ts("2021-01-10"))


# ------------------------------------------------------------------ L2 causality
def test_later_files_are_never_read_and_results_do_not_depend_on_them(base, tmp_path):
    import shutil

    out, store, freeze = base
    ds = pl.PitDataset.open(out, store, freeze)
    rnd = random.Random(20261126)
    cases = []
    for _ in range(24):
        sym = rnd.choice(["AAAUSDT", "BBBUSDT"])
        month = rnd.choice(
            ["2020-11", "2020-12"] if sym == "BBBUSDT" else ["2020-11", "2020-12", "2021-01"]
        )
        cases.append((sym, ts(f"{month}-{rnd.randrange(3, 28):02d} {rnd.randrange(0, 24):02d}:00")))
    for n, (sym, t) in enumerate(cases):
        m = f"{t.year}-{t.month:02d}"
        for itv, step in (("1d", pd.Timedelta(days=1)), ("1h", pd.Timedelta(hours=1))):
            want = ds.candles(sym, itv, t, start=ts("2020-10-15"))
            assert want.empty or (want["date"] + step <= t).all()  # completed candles only
            # a copy of the store in which EVERY file of every later month is destroyed
            alt = tmp_path / f"s{n}_{itv}"
            shutil.copytree(store, alt)
            for p in alt.rglob("*.zip"):
                if p.stem.rsplit("-", 2)[-2] + "-" + p.stem.rsplit("-", 1)[-1] > m:
                    p.write_bytes(b"destroyed later data") if n % 2 else p.unlink()
            got = pl.PitDataset.open(out, alt, freeze).candles(sym, itv, t, start=ts("2020-10-15"))
            pd.testing.assert_frame_equal(got, want)
        assert pl.PitDataset.open(out, None, freeze).universe_at(t) == ds.universe_at(
            t
        )  # tables only


# ------------------------------------------------------------------ L3 determinism
def test_repeated_loads_and_engine_runs_are_identical_across_processes(base, tmp_path):
    out, store, freeze = base
    ds1, ds2 = pl.PitDataset.open(out, store, freeze), pl.PitDataset.open(out, store, freeze)
    pd.testing.assert_frame_equal(
        ds1.candles("AAAUSDT", "1h", ts("2021-01-05")),
        ds2.candles("AAAUSDT", "1h", ts("2021-01-05")),
    )
    script = tmp_path / "run.py"
    script.write_text(
        "import sys, json, pandas as pd\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
        "from quantlab import pit_loader as pl\n"
        "from quantlab.execution import ExecConfig, Order, Strategy, run\n"
        "class S(Strategy):\n"
        "    def on_candle(self, t, hist, view):\n"
        "        return [Order('AAA/USDT', 'buy', notional=100.0)] if not view.positions else []\n"
        f"freeze = json.loads({__import__('json').dumps(__import__('json').dumps(freeze))})\n"
        f"ds = pl.PitDataset.open({str(out)!r}, {str(store)!r}, freeze)\n"
        "data = pl.to_price_data(ds, ['AAAUSDT'], '1h', pd.Timestamp('2020-12-01', tz='UTC'), pd.Timestamp('2020-12-20', tz='UTC'))\n"
        "print(run(S(), data, ExecConfig()).hash)\n",
        encoding="utf-8",
    )
    hs = [
        subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, check=True
        ).stdout.strip()
        for _ in range(2)
    ]
    assert hs[0] == hs[1] and len(hs[0]) == 64
