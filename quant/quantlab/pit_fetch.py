"""S4 point-in-time dataset builder, part 1: guarded, rate-limited, resumable, hash-pinned fetching.

Data source: Binance Vision public archive (CC BY-NC-SA 4.0, non-commercial research only; see
``quant/docs/phase4c/s3_licensing_findings.md``). This module never requests, lists or parses any
month >= ``DEV_END`` (2025-07): every URL goes through :meth:`Client.get`, which refuses it first.
No network access happens at import time and the transport is injectable for tests.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


DEV_END = "2025-07"  # exclusive, YYYY-MM: the holdout starts here
BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
KLINES = "data/spot/monthly/klines/"
_MONTH = re.compile(r"-(\d{4})-(\d{2})(?!\d)")
_YEAR_PREFIX = re.compile(r"-(\d{4})-$")


class HoldoutViolation(Exception):
    """Raised before any byte of a holdout month is requested, or if one is ever returned."""


class FetchError(Exception):
    """Transient failure that survived the retry budget (never persisted; a resume retries it)."""


class Transport(Protocol):
    def get(self, url: str) -> tuple[int, bytes]: ...


class HttpTransport:
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def get(self, url: str) -> tuple[int, bytes]:
        try:
            safe_url = urllib.parse.quote(url, safe=":/?&=%-._~")  # non-ASCII symbols exist
            with urllib.request.urlopen(safe_url, timeout=self.timeout) as r:  # noqa: S310
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, b""


class RateLimiter:
    """Global token bucket (``rate`` requests/s, burst 1) with a request-time log for measurement."""

    def __init__(self, rate: float, clock=time.monotonic, sleep=time.sleep):
        self.rate, self.clock, self.sleep = float(rate), clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()
        self.log: deque[float] = deque()

    def acquire(self) -> None:
        with self._lock:
            now = self.clock()
            at = max(now, self._next)
            self._next = at + 1.0 / self.rate
            self.log.append(at)
        if at > now:
            self.sleep(at - now)

    def peak_per_second(self) -> int:
        ts = sorted(self.log)
        best, j = 0, 0
        for i, t in enumerate(ts):
            while ts[j] <= t - 1.0 + 1e-9:
                j += 1
            best = max(best, i - j + 1)
        return best


def url_months(url: str) -> list[str]:
    return [f"{y}-{m}" for y, m in _MONTH.findall(url)]


def check_url(url: str) -> None:
    """Refuse any URL that names, or whose listing prefix could contain, a month >= DEV_END."""
    for ym in url_months(url):
        if ym >= DEV_END:
            raise HoldoutViolation(f"holdout guard: {url}")
    if "?" in url and "prefix=" in url:
        found = re.search(r"prefix=([^&]*)", url)
        prefix = found.group(1) if found else ""
        if prefix == KLINES:  # symbol directory names only; no month information is returned
            return
        name = prefix.rsplit("/", 1)[-1]
        pre_months = url_months(prefix)
        ypre = _YEAR_PREFIX.search(prefix)
        if "-" not in name or not (pre_months or ypre):
            raise HoldoutViolation(f"unbounded listing prefix: {url}")
        if ypre and f"{ypre.group(1)}-12" >= DEV_END:
            raise HoldoutViolation(f"listing prefix could include holdout months: {url}")


def check_keys(keys: list[str]) -> None:
    for k in keys:
        for ym in url_months(k):
            if ym >= DEV_END:
                raise HoldoutViolation(f"holdout key returned by the archive: {k}")


class Client:
    """Single choke point for every request: guard, rate limit, retry, request log."""

    def __init__(self, transport: Transport, limiter: RateLimiter, retries: int = 4, backoff=1.0):
        self.t, self.limiter, self.retries, self.backoff = transport, limiter, retries, backoff
        self.requests: list[str] = []
        self._lock = threading.Lock()

    def get(self, url: str) -> tuple[int, bytes]:
        check_url(url)
        for k in range(self.retries):
            self.limiter.acquire()
            with self._lock:
                self.requests.append(url)
            status, body = self.t.get(url)
            if status in (200, 404):
                return status, body
            time.sleep(self.backoff * (2**k) if self.backoff else 0)
        raise FetchError(url)

    # ---- listings (S3 ListObjects v1 XML)
    def list_dirs(self, prefix: str) -> list[str]:
        url = f"{BASE}?delimiter=/&prefix={prefix}&max-keys=1000"
        out, marker = [], ""
        while True:
            st, body = self.get(url + (f"&marker={marker}" if marker else ""))
            if st != 200:
                raise FetchError(url)
            t = body.decode()
            out += re.findall(r"<CommonPrefixes><Prefix>([^<]+)</Prefix>", t)
            if "<IsTruncated>true</IsTruncated>" not in t:
                return out
            m = re.search(r"<NextMarker>([^<]+)</NextMarker>", t)
            marker = m.group(1) if m else out[-1]

    def list_keys(self, prefix: str) -> list[str]:
        url = f"{BASE}?delimiter=/&prefix={prefix}&max-keys=1000"
        st, body = self.get(url)
        if st != 200:
            raise FetchError(url)
        keys = re.findall(r"<Contents><Key>([^<]+)</Key>", body.decode())
        check_keys(keys)
        return keys


def month_prefixes(symbol: str, interval: str) -> list[str]:
    """Listing prefixes covering 2017-2025-06 and nothing later (year prefixes to 2024, months in 2025)."""
    base = f"{KLINES}{symbol}/{interval}/{symbol}-{interval}-"
    return [f"{base}{y}-" for y in range(2017, 2025)] + [f"{base}2025-{m:02d}" for m in range(1, 7)]


def list_symbol_months(client: Client, symbol: str, interval: str = "1d") -> list[str]:
    months = set()
    for p in month_prefixes(symbol, interval):
        for k in client.list_keys(p):
            if k.endswith(".zip"):
                months.add(k.rsplit("-", 2)[-2] + "-" + k.rsplit("-", 1)[-1][:2])
    return sorted(months)


# ---------------------------------------------------------------------------- resumable store
@dataclass
class FileRecord:
    symbol: str
    interval: str
    month: str
    status: str  # ok | absent | quarantined
    reason: str = ""
    sha256: str = ""
    published_sha256: str = ""
    size: int = 0


class Store:
    """Directory store. A ``.meta.json`` sidecar is written LAST and is the commit marker, so an
    interrupted download is simply redone; a committed zip whose hash no longer matches is refetched."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def paths(self, symbol: str, interval: str, month: str) -> tuple[Path, Path]:
        d = self.root / interval / symbol
        n = f"{symbol}-{interval}-{month}"
        return d / f"{n}.zip", d / f"{n}.meta.json"

    def cached(self, symbol: str, interval: str, month: str) -> FileRecord | None:
        z, m = self.paths(symbol, interval, month)
        if not m.exists():
            return None
        try:
            rec = FileRecord(**json.loads(m.read_text(encoding="utf-8")))
        except (ValueError, TypeError):
            return None
        if rec.status == "absent":
            return rec
        if z.exists() and hashlib.sha256(z.read_bytes()).hexdigest() == rec.sha256:
            return rec
        return None


def _published(body: bytes) -> str:
    parts = body.decode(errors="replace").split()
    return parts[0].lower() if parts and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]) else ""


def fetch_file(client: Client, store: Store, symbol: str, interval: str, month: str) -> FileRecord:
    if month >= DEV_END:
        raise HoldoutViolation(f"{symbol} {interval} {month}")
    done = store.cached(symbol, interval, month)
    if done is not None:
        return done
    z, m = store.paths(symbol, interval, month)
    z.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/{KLINES}{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    rec = FileRecord(symbol, interval, month, "absent")
    st, body = client.get(url)
    if st == 200:
        for attempt in range(2):  # one refetch on checksum mismatch
            cst, cbody = client.get(url + ".CHECKSUM")
            pub = _published(cbody) if cst == 200 else ""
            got = hashlib.sha256(body).hexdigest()
            if pub and got == pub:
                rec = FileRecord(symbol, interval, month, "ok", "", got, pub, len(body))
                break
            if attempt == 0:
                st, body = client.get(url)
                if st != 200:
                    raise FetchError(url)
                continue
            reason = "checksum_mismatch"
            rec = FileRecord(symbol, interval, month, "quarantined", reason, got, pub, len(body))
        tmp = z.with_suffix(".part")
        tmp.write_bytes(body)
        tmp.replace(z)
    m.write_text(json.dumps(asdict(rec), sort_keys=True), encoding="utf-8")
    return rec
