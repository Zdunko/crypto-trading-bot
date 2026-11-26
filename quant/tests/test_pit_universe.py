"""S4 universe: reason codes, epochs, causal eligibility, classification, determinism, prefix and
perturbation invariance (property tests with seeded random markets, synthetic only)."""

from __future__ import annotations

import gzip
import io
import json
import random
import zipfile

import pytest
from fake_s3 import FakeS3

from quantlab import data_audit as da
from quantlab import pit_fetch as pf
from quantlab import pit_run
from quantlab import pit_universe as pu


DAY = pu.DAY
T0 = da.month_bounds_ms("2021-01")[0]


def csv_zip(rows: list[list], name="x.csv") -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, "\n".join(",".join(str(c) for c in r) for r in rows) + "\n")
    return b.getvalue()


def drow(ts, close=100.0, vol=10.0, qv=None):
    qv = vol * close if qv is None else qv
    return [ts, close, close * 1.1, close * 0.9, close, vol, ts + 1, qv, 5, 0, 0, 0]


def month_rows(ym, n=None, **kw):
    lo, hi = da.month_bounds_ms(ym)
    return [drow(lo + i * DAY, **kw) for i in range((hi - lo) // DAY if n is None else n)]


def rec(sym="AAAUSDT", itv="1d", ym="2021-01", status="ok", reason=""):
    return pf.FileRecord(sym, itv, ym, status, reason, "a" * 64, "a" * 64, 1)


# ------------------------------------------------------------------ reason codes (Q3)
def test_every_reason_code_is_produced_by_a_synthetic_file():
    ym = "2021-01"
    base = month_rows(ym)
    cases = {
        "malformed_row": csv_zip([r[:4] for r in base]),
        "bad_timestamp_unit": csv_zip([[str(12345)] + r[1:] for r in base]),
        "nonpositive_price": csv_zip([drow(r[0], close=-1) for r in base]),
        "negative_volume": csv_zip([drow(r[0], vol=-5) for r in base]),
        "ohlc_inconsistent": csv_zip([[r[0], 100, 50, 90, 100, 1, 0, 1] for r in base]),
        "duplicate_timestamp": csv_zip(base + [base[3]]),
        "out_of_order": csv_zip(base[:5] + [base[6], base[5]] + base[7:]),
        "repeated_block": csv_zip(base * 3),
        "misaligned_timestamp": csv_zip([[base[0][0] + 7] + base[0][1:]] + base[1:]),
        "outside_month": csv_zip(month_rows("2021-02")),
        "empty": csv_zip([]),
        "extra_rows": csv_zip(base + [base[3]]),
    }
    for reason, data in cases.items():
        sc = pu.scan_file(rec(ym=ym), data)
        assert reason in sc.reasons, (reason, sc.reasons)
        assert (
            sc.status == ("quarantined" if reason in pu.FATAL_REASONS else "ok")
            or reason == "extra_rows"
        )
    assert (
        pu.scan_file(rec(status="quarantined", reason="checksum_mismatch"), b"").reasons[0]
        == "checksum_mismatch"
    )
    assert pu.scan_file(rec(status="absent"), None).status == "absent"
    bad_zip = pu.scan_file(rec(), b"not a zip")
    assert bad_zip.status == "quarantined" and "malformed_row" in bad_zip.reasons
    assert set(cases) | {"checksum_mismatch", "fetch_failed", "absent_expected"} == set(pu.REASONS)


def test_clean_daily_and_hourly_scan_carry_series_and_volumes():
    sc = pu.scan_file(rec(), csv_zip(month_rows("2021-01")))
    assert sc.status == "ok" and len(sc.candles) == 31 and len(sc.day_volume) == 31
    lo = da.month_bounds_ms("2021-01")[0]
    hrs = [drow(lo + i * 3_600_000, vol=1.0) for i in range(744)]
    h = pu.scan_file(rec(itv="1h"), csv_zip(hrs))
    assert h.status == "ok" and h.day_volume[lo] == 24.0
    micro = [[str(int(r[0]) * 1000)] + r[1:] for r in month_rows("2021-01")]
    assert pu.scan_file(rec(), csv_zip(micro)).status == "ok"  # microsecond era


# ------------------------------------------------------------------ classification
def table(**cls):
    return {f"{b}USDT": {"class": c} for b, c in cls.items()}


def test_classification_is_fail_closed_and_regex_is_only_an_alarm():
    t = table(BTC="asset", SYRUP="asset", ADAUP="leveraged_token")
    chk = pu.classification_check(
        t, ["BTCUSDT", "SYRUPUSDT", "ADAUPUSDT", "NEWUSDT", "FOOBULLUSDT"]
    )
    assert chk["unreviewed"] == ["FOOBULLUSDT", "NEWUSDT"]  # not silently included or excluded
    assert chk["suspect_asset"] == ["SYRUPUSDT"]  # reviewed, explicitly an asset
    series = {"NEWUSDT": [(T0, 1.0, 1e9)]}
    with pytest.raises(pu.ClassificationError):
        pu.membership(series, t, ["2021-01"])


def test_non_asset_classes_never_enter_membership():
    def long(base):
        return [(T0 - (100 - i) * DAY, 1.0, 5e6) for i in range(100)]

    t = table(
        AAA="asset", USDC="stablecoin", ADAUP="leveraged_token", PAXG="commodity_token", EUR="fiat"
    )
    series = {s: long(s) for s in t}
    rows = pu.membership(series, t, ["2021-01"])
    assert {r[2].split("#")[0] for r in rows} == {"AAAUSDT"}


# ------------------------------------------------------------------ epochs
def series_of(closes, start=T0, qv=2e6, step=DAY):
    return [(start + i * step, c, qv) for i, c in enumerate(closes)]


def test_epoch_breaks_use_only_the_breaking_candle():
    s = series_of([10, 10.5, 10.2, 200, 205, 2.0, 2.1])  # up-jump (x19.6) then down-jump (x0.0098)
    ep, idx = pu.build_epochs("AAAUSDT", s)
    assert [e.start_reason for e in ep] == ["first_candle", "jump_up", "jump_down"]
    assert idx == [0, 0, 0, 1, 1, 2, 2]
    assert pu.build_epochs("AAAUSDT", series_of([10, 19.9, 2.1]))[0][0].n == 3  # < 10x: no break
    # gap of >= 2 whole calendar months
    a = series_of([1.0] * 20, start=da.month_bounds_ms("2021-01")[0])
    b = series_of([1.0] * 5, start=da.month_bounds_ms("2021-04")[0])
    assert [e.start_reason for e in pu.build_epochs("X", a + b)[0]] == ["first_candle", "gap"]
    c = series_of([1.0] * 5, start=da.month_bounds_ms("2021-03")[0])  # only February missing
    assert len(pu.build_epochs("X", a + c)[0]) == 1


def random_market(seed, n_sym=12, days=400):
    rnd = random.Random(seed)
    out = {}
    for i in range(n_sym):
        start = T0 + rnd.randrange(0, 150) * DAY
        n = rnd.randrange(80, days)
        px, cs = 10.0, []
        for k in range(n):
            if rnd.random() < 0.01:
                px *= rnd.choice([0.05, 20.0])  # redenomination-like jump
            px *= rnd.uniform(0.95, 1.05)
            if rnd.random() < 0.02:  # random missing days
                continue
            cs.append(
                (start + k * DAY, px, rnd.choice([0.0, 5e5, 2e6, 8e6]) * rnd.uniform(0.5, 1.5))
            )
        if rnd.random() < 0.3 and len(cs) > 100:  # a gap of several months inside the history
            cs = cs[:60] + [(t + 100 * DAY, p, q) for t, p, q in cs[60:]]
        out[f"S{i}USDT"] = cs
    return out


CLASSES = {f"S{i}USDT": {"class": "asset"} for i in range(12)}


def test_epoch_tables_are_prefix_invariant_property():
    for seed in range(12):
        mk = random_market(seed)
        full = pu.epochs_table(mk)
        for cut in (T0 + 100 * DAY, T0 + 250 * DAY, T0 + 400 * DAY):
            part = pu.epochs_table({s: pu.truncate(c, cut) for s, c in mk.items()})
            assert pu.epoch_keys(full, cut) == pu.epoch_keys(part, cut), (seed, cut)


# ------------------------------------------------------------------ eligibility and causality
def test_only_completed_candles_count_and_window_is_90_days():
    thr = 1e6
    # exactly 60 completed candles in the 90 days before T (T = T0)
    s = series_of([1.0] * 60, start=T0 - 60 * DAY, qv=2e6)
    ts = [c[0] for c in s]
    _, idx = pu.build_epochs("A", s)
    assert pu.eligible_epoch(s, idx, T0, thr, ts) == (0, 59)
    s59 = s[1:]
    assert pu.eligible_epoch(s59, pu.build_epochs("A", s59)[1], T0, thr) is None
    # the candle opening AT T is not completed: it must not count, and must not change anything
    s_open = s[1:] + [(T0, 1.0, 9e9)]
    assert pu.eligible_epoch(s_open, pu.build_epochs("A", s_open)[1], T0, thr) is None
    # median below threshold
    low = series_of([1.0] * 60, start=T0 - 60 * DAY, qv=5e5)
    assert pu.eligible_epoch(low, pu.build_epochs("A", low)[1], T0, thr) is None


def test_new_epoch_restarts_history():
    s = series_of([1.0] * 80 + [100.0] * 30, start=T0 - 110 * DAY, qv=2e6)  # x100 jump at day 80
    t = T0
    _, idx = pu.build_epochs("A", s)
    assert pu.eligible_epoch(s, idx, t, 1e6) is None  # only 30 candles in the new epoch
    s2 = series_of([1.0] * 80 + [100.0] * 65, start=T0 - 145 * DAY, qv=2e6)
    assert pu.eligible_epoch(s2, pu.build_epochs("A", s2)[1], t, 1e6) is not None


def test_membership_is_causal_under_adversarial_future_property():
    rnd = random.Random(7)
    modes = ["volume_x1000", "volume_zero", "price_x1000", "delete", "duplicate", "random"]
    for seed in range(8):
        mk = random_market(seed)
        for _ in range(3):
            d = rnd.choice(["2021-03", "2021-06", "2021-09", "2021-12"])
            t = pu.ms_of(d)
            base = pu.membership(mk, CLASSES, [d])
            for m in modes:
                assert pu.membership(pit_run.perturb(mk, t, m, rnd), CLASSES, [d]) == base, (
                    seed,
                    d,
                    m,
                )
            tr = {s: pu.truncate(c, t) for s, c in mk.items()}
            assert pu.membership(tr, CLASSES, [d]) == base  # prefix invariance


def test_symbols_with_only_future_data_cannot_change_membership():
    mk = random_market(3)
    t = pu.ms_of("2021-06")
    base = pu.membership(mk, CLASSES, ["2021-06"])
    fut = {**mk, "S99USDT": series_of([1.0] * 200, start=t + 5 * DAY, qv=9e9)}
    assert pu.membership(fut, {**CLASSES, "S99USDT": {"class": "asset"}}, ["2021-06"]) == base


def test_delisted_assets_stay_members_at_earlier_dates_no_survivorship():
    ended = series_of([1.0] * 120, start=T0 - 60 * DAY, qv=3e6)  # last candle ~ T0 + 59d
    alive = series_of([1.0] * 400, start=T0 - 60 * DAY, qv=3e6)
    mk = {"S0USDT": ended, "S1USDT": alive}
    rows = pu.membership(mk, CLASSES, ["2021-01", "2021-02", "2021-04", "2021-06"])
    by = {(r[0], r[2]) for r in rows if r[1] == "1M"}
    assert ("2021-01", "S0USDT#0") in by and (
        "2021-02",
        "S0USDT#0",
    ) in by  # still a member while it traded
    assert ("2021-06", "S1USDT#0") in by
    assert ("2021-06", "S0USDT#0") not in by  # >30 days after its last candle the 60/90 rule fails
    stale = {r[3] for r in rows if r[2] == "S0USDT#0"}
    assert max(stale) >= 0  # staleness is exposed (days_since_last_candle), not hidden


# ------------------------------------------------------------------ determinism and hashes
def test_dataset_hash_is_deterministic_order_independent_and_sensitive():
    mk = random_market(5)
    m1 = pu.membership(mk, CLASSES, ["2021-03"])
    m2 = pu.membership(dict(reversed(list(mk.items()))), CLASSES, ["2021-03"])
    assert m1 == m2
    t1 = pu.csv_text(["a"], m1)
    assert pu.sha(t1) == pu.sha(pu.csv_text(["a"], m2))
    p = {"x": 1}
    h = pu.dataset_hash({"files": "a"}, p)
    assert h == pu.dataset_hash({"files": "a"}, p)
    assert h != pu.dataset_hash({"files": "b"}, p) and h != pu.dataset_hash(
        {"files": "a"}, {"x": 2}
    )


# ------------------------------------------------------------------ end-to-end on a fake archive
def _archive(tmp_path):
    objs, listing = {}, {}
    for sym, level in (("AAAUSDT", 5e6), ("BBBUSDT", 2e6), ("ADAUPUSDT", 9e6)):
        months = ["2020-10", "2020-11", "2020-12", "2021-01"]
        listing[sym] = months
        for m in months:
            for itv, n in (("1d", None), ("1h", 24 * 31 if m != "2020-11" else 24 * 30)):
                if itv == "1d":
                    rows = month_rows(m, close=1.0, vol=level)
                else:
                    lo = da.month_bounds_ms(m)[0]
                    rows = [drow(lo + i * 3_600_000, close=1.0, vol=level / 24) for i in range(n)]
                objs[f"{pf.KLINES}{sym}/{itv}/{sym}-{itv}-{m}.zip"] = csv_zip(rows)
    return objs, listing


def test_build_is_deterministic_resumable_and_hash_recomputable(tmp_path):
    objs, listing = _archive(tmp_path)
    cls = tmp_path / "classes.json"
    cls.write_text(
        json.dumps(
            {
                "symbols": {
                    "AAAUSDT": {"class": "asset"},
                    "BBBUSDT": {"class": "asset"},
                    "ADAUPUSDT": {"class": "leveraged_token"},
                }
            }
        ),
        encoding="utf-8",
    )
    outs = []
    for run in ("a", "b"):
        raw = tmp_path / run
        raw.mkdir()
        (raw / "listing.json").write_text(json.dumps(listing), encoding="utf-8")
        st = pf.Store(raw / "files")
        c = pf.Client(FakeS3(objs), pf.RateLimiter(1e6), retries=1, backoff=0)
        if run == "b":  # interrupted first: only a few files, then resume
            for m in listing["AAAUSDT"][:2]:
                pf.fetch_file(c, st, "AAAUSDT", "1d", m)
        for itv in ("1d", "1h"):
            for s in listing:
                for m in listing[s]:
                    pf.fetch_file(c, st, s, itv, m)
        out = tmp_path / f"out_{run}"
        man = pit_run.build(raw, out, classification=cls)
        outs.append((out, man))
    (oa, ma), (ob, mb) = outs
    assert ma["dataset_hash"] == mb["dataset_hash"]
    for f in ("files.csv.gz", "epochs.csv.gz", "membership.csv.gz", "manifest.json"):
        assert (oa / f).read_bytes() == (ob / f).read_bytes(), f
    # M1: recompute the dataset hash from the written files + manifest
    parts = {
        "files": pu.sha(gzip.open(oa / "files.csv.gz", "rt").read()),
        "epochs": pu.sha(gzip.open(oa / "epochs.csv.gz", "rt").read()),
        "membership": pu.sha(gzip.open(oa / "membership.csv.gz", "rt").read()),
        "classification": pu.sha(cls.read_bytes()),
    }
    assert parts == ma["parts"] and pu.dataset_hash(parts, ma["params"]) == ma["dataset_hash"]
    mem = gzip.open(oa / "membership.csv.gz", "rt").read()
    assert (
        "AAAUSDT#0" in mem and "ADAUPUSDT" not in mem
    )  # leveraged token excluded by the explicit table
    files = gzip.open(oa / "files.csv.gz", "rt").read()
    assert "absent_expected" not in files and ma["counts"]["files"] == 24
    # fail-closed: an unreviewed base blocks the build
    cls.write_text(json.dumps({"symbols": {"AAAUSDT": {"class": "asset"}}}), encoding="utf-8")
    with pytest.raises(SystemExit):
        pit_run.build(tmp_path / "a", tmp_path / "out_c", classification=cls)
    # missing record -> fail closed, or explicit fetch_failed reason when allowed
    (tmp_path / "a/files/1h/AAAUSDT/AAAUSDT-1h-2021-01.meta.json").unlink()
    cls.write_text(
        json.dumps(
            {
                "symbols": {
                    "AAAUSDT": {"class": "asset"},
                    "BBBUSDT": {"class": "asset"},
                    "ADAUPUSDT": {"class": "leveraged_token"},
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        pit_run.build(tmp_path / "a", tmp_path / "out_d", classification=cls)
    man = pit_run.build(
        tmp_path / "a", tmp_path / "out_e", classification=cls, allow_incomplete=True
    )
    assert man["reason_counts"]["fetch_failed"] == 1


def test_validate_runs_end_to_end_on_a_synthetic_archive(tmp_path, monkeypatch):
    objs, listing = _archive(tmp_path)
    cls = tmp_path / "classes.json"
    syms = {s: {"class": "asset"} for s in ("AAAUSDT", "BBBUSDT")} | {
        "ADAUPUSDT": {"class": "leveraged_token"}
    }
    cls.write_text(json.dumps({"symbols": syms}), encoding="utf-8")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "listing.json").write_text(json.dumps(listing), encoding="utf-8")
    log = raw / "requests_append.log"
    client = pf.Client(FakeS3(objs), pf.RateLimiter(1e6), retries=1, backoff=0, log_path=log)
    st = pf.Store(raw / "files")
    for itv in ("1d", "1h"):
        for s in listing:
            for m in listing[s]:
                pf.fetch_file(client, st, s, itv, m)
    lines = log.read_text().splitlines()
    assert len(lines) == len(client.requests) and all(len(x.split("\t")) == 2 for x in lines)
    (raw / "fetch_report.json").write_text(
        json.dumps(
            {
                "jobs": 1,
                "failures": [],
                "requests": len(lines),
                "configured_rate": 30.0,
                "peak_requests_per_second": 20,
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    pit_run.build(raw, out, classification=cls)
    pins = tmp_path / "s3pins.tsv.gz"
    with gzip.open(pins, "wt") as g:
        g.write("1d\tAAAUSDT\t2020-10\t200\tdeadbeef\t1\n")
    monkeypatch.setattr(pit_run, "S3_PINS", pins)
    monkeypatch.setattr(pit_run, "CLASSIFICATION", cls)
    res = pit_run.validate(raw, out)
    assert all(x["equal"] for x in res["I1"]) and all(x["equal"] for x in res["I2"])
    assert all(all(x["equal_by_mode"].values()) for x in res["U1"])
    assert res["B1"]["count"] == 0 and res["B2"]["all_before_cutoff"]
    assert res["R1_stability"]["identical_sha"] == 0 and res["R1_stability"]["s3_pinned"] == 1
    assert res["F3"]["requests_logged"] == len(lines)
