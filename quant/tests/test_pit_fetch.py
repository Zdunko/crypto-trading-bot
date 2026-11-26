"""S4 fetch layer: holdout guard, rate limit, integrity, resumability, fail-closed behaviour (fake S3)."""

from __future__ import annotations

import hashlib

import pytest
from fake_s3 import FakeS3, key, zip_bytes

from quantlab import pit_fetch as pf


DAY = 86_400_000


def mk_client(fake, rate=1000.0):
    return pf.Client(fake, pf.RateLimiter(rate), retries=2, backoff=0)


def test_guard_refuses_holdout_urls_and_unbounded_prefixes():
    for u in [
        f"{pf.BASE}/{pf.KLINES}X/1d/X-1d-2025-07.zip",
        f"{pf.BASE}/{pf.KLINES}X/1d/X-1d-2026-01.zip.CHECKSUM",
        f"{pf.BASE}?prefix={pf.KLINES}X/1d/&max-keys=5",
        f"{pf.BASE}?prefix={pf.KLINES}X/1d/X-1d-2025-&max-keys=5",
        f"{pf.BASE}?prefix={pf.KLINES}X/1d/X-1d-2025-0&max-keys=5",
        f"{pf.BASE}?prefix={pf.KLINES}X/1d/X-1d-&max-keys=5",
    ]:
        with pytest.raises(pf.HoldoutViolation):
            pf.check_url(u)
    for u in [
        f"{pf.BASE}?delimiter=/&prefix={pf.KLINES}&max-keys=1000",
        f"{pf.BASE}?prefix={pf.KLINES}X/1d/X-1d-2024-&max-keys=5",
        f"{pf.BASE}?prefix={pf.KLINES}X/1d/X-1d-2025-06&max-keys=5",
        f"{pf.BASE}/{pf.KLINES}X/1d/X-1d-2025-06.zip",
    ]:
        pf.check_url(u)
    # every listing prefix the builder generates is itself guarded
    for p in pf.month_prefixes("BTCUSDT", "1h"):
        pf.check_url(f"{pf.BASE}?prefix={p}&max-keys=1000")


def test_response_keys_in_holdout_are_rejected():
    class Leaky(FakeS3):
        def get(self, url):
            if "?" in url:
                return 200, f"<Contents><Key>{key('X', '1d', '2025-09')}</Key></Contents>".encode()
            return super().get(url)

    c = mk_client(Leaky({}))
    with pytest.raises(pf.HoldoutViolation):
        c.list_keys(f"{pf.KLINES}X/1d/X-1d-2025-06")


def test_listing_never_asks_for_holdout_and_months_are_dev_only():
    objs = {key("AAAUSDT", "1d", m): b"x" for m in ("2020-01", "2025-06", "2025-07", "2025-08")}
    objs.update({key("AAAUSDT", "1d", m) + ".CHECKSUM": b"x" for m in ("2025-06", "2025-07")})
    fake = FakeS3(objs)
    months = pf.list_symbol_months(mk_client(fake), "AAAUSDT")
    assert months == ["2020-01", "2025-06"]  # the 2025-07/08 objects exist but are never seen
    assert all(pf.url_months(u) == [] or max(pf.url_months(u)) < pf.DEV_END for u in fake.log)


def test_fetch_ok_absent_and_cached(tmp_path):
    z = zip_bytes("a.csv", "1,2,3\n")
    fake = FakeS3({key("AAAUSDT", "1d", "2021-01"): z})
    c, st = mk_client(fake), pf.Store(tmp_path)
    r = pf.fetch_file(c, st, "AAAUSDT", "1d", "2021-01")
    assert r.status == "ok" and r.sha256 == r.published_sha256 == hashlib.sha256(z).hexdigest()
    n = fake.n
    assert (
        pf.fetch_file(c, st, "AAAUSDT", "1d", "2021-01") == r and fake.n == n
    )  # cached, no request
    a = pf.fetch_file(c, st, "AAAUSDT", "1h", "2021-01")
    assert a.status == "absent"
    n = fake.n
    assert pf.fetch_file(c, st, "AAAUSDT", "1h", "2021-01") == a and fake.n == n
    with pytest.raises(pf.HoldoutViolation):
        pf.fetch_file(c, st, "AAAUSDT", "1d", "2025-07")


def test_checksum_mismatch_refetched_once_then_quarantined(tmp_path):
    z = zip_bytes("a.csv", "1,2,3\n")
    k = key("AAAUSDT", "1d", "2021-01")
    fake = FakeS3({k: z}, corrupt={k})
    r = pf.fetch_file(mk_client(fake), pf.Store(tmp_path), "AAAUSDT", "1d", "2021-01")
    assert r.status == "quarantined" and r.reason == "checksum_mismatch"
    assert sum(1 for u in fake.log if u.endswith(".zip")) == 2  # exactly one refetch


def test_transient_failure_is_not_persisted_and_resume_completes(tmp_path):
    objs = {
        key("AAAUSDT", "1d", f"2021-{m:02d}"): zip_bytes("a.csv", f"{m}\n") for m in range(1, 7)
    }
    st = pf.Store(tmp_path)
    broken = FakeS3(objs, fail_after=7)  # network dies mid-run
    c = mk_client(broken)
    done, failed = [], []
    for m in range(1, 7):
        try:
            done.append(pf.fetch_file(c, st, "AAAUSDT", "1d", f"2021-{m:02d}"))
        except pf.FetchError:
            failed.append(m)
    assert (
        failed and done
    )  # partially done, failures raised (fail closed), nothing persisted for them
    for m in failed:
        assert st.cached("AAAUSDT", "1d", f"2021-{m:02d}") is None
    c2 = mk_client(FakeS3(objs))
    resumed = [pf.fetch_file(c2, st, "AAAUSDT", "1d", f"2021-{m:02d}") for m in range(1, 7)]
    clean = [
        pf.fetch_file(
            mk_client(FakeS3(objs)), pf.Store(tmp_path / "clean"), "AAAUSDT", "1d", f"2021-{m:02d}"
        )
        for m in range(1, 7)
    ]
    assert resumed == clean
    assert len(c2.requests) < 2 * 6 + 1  # finished files were not downloaded again


def test_interrupted_write_and_corrupted_cache_are_redone(tmp_path):
    z = zip_bytes("a.csv", "1\n")
    fake = FakeS3({key("AAAUSDT", "1d", "2021-01"): z})
    st = pf.Store(tmp_path)
    zp, mp = st.paths("AAAUSDT", "1d", "2021-01")
    zp.parent.mkdir(parents=True)
    zp.with_suffix(".part").write_bytes(b"half")  # crash before commit: no meta
    zp.write_bytes(b"garbage")
    r = pf.fetch_file(mk_client(fake), st, "AAAUSDT", "1d", "2021-01")
    assert r.status == "ok" and zp.read_bytes() == z
    zp.write_bytes(b"bit rot")  # committed file damaged later
    assert st.cached("AAAUSDT", "1d", "2021-01") is None
    r2 = pf.fetch_file(mk_client(fake), st, "AAAUSDT", "1d", "2021-01")
    assert r2 == r and zp.read_bytes() == z
    mp.write_text("{not json", encoding="utf-8")  # corrupt meta
    assert st.cached("AAAUSDT", "1d", "2021-01") is None


def test_rate_limiter_peak_never_exceeds_limit():
    t = [0.0]
    lim = pf.RateLimiter(10.0, clock=lambda: t[0], sleep=lambda d: t.__setitem__(0, t[0] + d))
    for _ in range(100):
        lim.acquire()
    assert lim.peak_per_second() <= 10
    # elapsed (simulated) time is >= n/rate
    assert t[0] >= 9.8


def test_discovery_lists_usdt_dirs():
    fake = FakeS3({key("AAAUSDT", "1d", "2020-01"): b"x", key("BBBBTC", "1d", "2020-01"): b"x"})
    dirs = mk_client(fake).list_dirs(pf.KLINES)
    assert [d.rstrip("/").rsplit("/", 1)[-1] for d in dirs] == ["AAAUSDT", "BBBBTC"]


def test_non_ascii_symbols_are_percent_encoded(monkeypatch):
    seen = []

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    monkeypatch.setattr(pf.urllib.request, "urlopen", lambda u, timeout: (seen.append(u), R())[1])
    assert pf.HttpTransport().get(
        f"{pf.BASE}?prefix={pf.KLINES}币安人生USDT/1d/币安人生USDT-1d-2024-"
    ) == (200, b"ok")
    assert seen[0].isascii() and "%E5%B8%81" in seen[0] and "?prefix=" in seen[0]


def test_dropped_connections_are_retryable_not_fatal(monkeypatch):
    import http.client

    def boom(u, timeout):
        raise http.client.IncompleteRead(b"x" * 10, 5)

    monkeypatch.setattr(pf.urllib.request, "urlopen", boom)
    assert pf.HttpTransport().get(f"{pf.BASE}/{pf.KLINES}X/1d/X-1d-2021-01.zip") == (0, b"")
    c = pf.Client(pf.HttpTransport(), pf.RateLimiter(1e6), retries=2, backoff=0)
    with pytest.raises(pf.FetchError):  # fail closed after the retry budget, never a crash
        c.get(f"{pf.BASE}/{pf.KLINES}X/1d/X-1d-2021-01.zip")
