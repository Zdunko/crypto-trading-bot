"""S4 point-in-time dataset builder, part 2: quality scan, identity epochs, classification,
causal liquidity eligibility, deterministic tables and hashes.

Everything is a pure function of the files handed in. Causality contract (tested, and verified on the
real data by ``pit_run validate``): membership at date T depends only on COMPLETED daily candles
(open + 1 day <= T) and on data/events known at or before T; epoch breaks are triggered by the candle
at which they become observable. No global (whole-sample) exclusion exists anywhere.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import statistics
import zipfile
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path

from quantlab import data_audit as da


DAY = 86_400_000
WINDOW_DAYS, MIN_DAYS = 90, 60
THRESHOLDS = {"1M": 1e6, "5M": 5e6}
GAP_MONTHS, JUMP = 2, 10.0
CLASSES = ("asset", "stablecoin", "fiat", "leveraged_token", "commodity_token")
SUSPECT = re.compile(r"(UP|DOWN|BULL|BEAR)$")  # alarm only, never an authority
REASONS = (
    "checksum_mismatch",
    "malformed_row",
    "bad_timestamp_unit",
    "nonpositive_price",
    "negative_volume",
    "ohlc_inconsistent",
    "duplicate_timestamp",
    "out_of_order",
    "repeated_block",
    "misaligned_timestamp",
    "outside_month",
    "empty",
    "fetch_failed",
    "absent_expected",
    "extra_rows",
)
FATAL_REASONS = frozenset(REASONS) - {"absent_expected", "extra_rows"}


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


# ---------------------------------------------------------------------------- classification
class ClassificationError(Exception):
    pass


def load_classification(path: str | Path) -> dict[str, dict]:
    t = json.loads(Path(path).read_text(encoding="utf-8"))
    for sym, e in t["symbols"].items():
        if e["class"] not in CLASSES:
            raise ClassificationError(f"{sym}: unknown class {e['class']}")
    return t["symbols"]


def classification_check(table: dict[str, dict], symbols: list[str]) -> dict[str, list[str]]:
    """Fail-closed review: every dev-window symbol must be in the table; name-pattern suspects
    that are not explicitly reviewed are reported (the table, not the pattern, decides)."""
    syms = sorted(set(symbols))
    return {
        "unreviewed": [s for s in syms if s not in table],
        "suspect_asset": sorted(
            s for s in syms if SUSPECT.search(s[:-4]) and table.get(s, {}).get("class") == "asset"
        ),
    }


# ---------------------------------------------------------------------------- file scan
@dataclass
class FileScan:
    symbol: str
    interval: str
    month: str
    status: str  # ok | quarantined | absent
    reasons: list[str] = field(default_factory=list)
    warnings: dict[str, int] = field(default_factory=dict)
    rows: int = 0
    missing: int = 0
    candles: list[tuple[int, float, float]] = field(
        default_factory=list
    )  # daily: (ts_ms, close, qv)
    day_volume: dict[int, float] = field(default_factory=dict)  # hourly: day -> sum(base volume)
    first_ts: int | None = None
    last_ts: int | None = None


def read_rows(data: bytes) -> list[list[str]]:
    zf = zipfile.ZipFile(io.BytesIO(data))
    txt = zf.read(zf.namelist()[0]).decode()
    return [ln.split(",") for ln in txt.splitlines() if ln and not ln[0].isalpha()]


def scan_file(rec, data: bytes | None) -> FileScan:
    """Classify one downloaded file. ``rec`` is a pit_fetch.FileRecord."""
    s = FileScan(rec.symbol, rec.interval, rec.month, rec.status)
    if rec.status == "absent":
        return s
    reasons: list[str] = []
    if rec.status == "quarantined" and rec.reason:
        reasons.append(rec.reason)
    rows: list[list[str]] = []
    if data is not None:
        try:
            rows = read_rows(data)
        except (zipfile.BadZipFile, KeyError, IndexError, UnicodeDecodeError, ValueError):
            reasons.append("malformed_row")
    rep = da.check_candles(rows, rec.interval, rec.month) if not reasons else None
    if rep is not None:
        reasons += [k for k in rep.findings if k in FATAL_REASONS or k == "extra_rows"]
        s.warnings = {k: n for k, n in rep.findings.items() if k not in FATAL_REASONS}
        s.rows, s.missing = rep.rows, rep.missing_candles
    fatal = sorted({r for r in reasons if r in FATAL_REASONS})
    s.reasons = sorted(set(reasons))
    if fatal:
        s.status = "quarantined"
        return s
    s.status = "ok"
    if not rows:
        return s
    ts = [da.to_ms(int(r[0])) for r in rows]
    s.first_ts, s.last_ts = min(ts), max(ts)
    if rec.interval == "1d":
        s.candles = sorted((t, float(r[4]), float(r[7])) for t, r in zip(ts, rows, strict=True))
        s.day_volume = {t: float(r[5]) for t, r in zip(ts, rows, strict=True)}
    else:
        for t, r in zip(ts, rows, strict=True):
            d = t - t % DAY
            s.day_volume[d] = s.day_volume.get(d, 0.0) + float(r[5])
    return s


# ---------------------------------------------------------------------------- identity epochs
@dataclass(frozen=True)
class Epoch:
    symbol: str
    k: int
    start: int
    start_reason: str  # first_candle | gap | jump_up | jump_down
    end: int  # last candle seen in the data given
    n: int

    @property
    def eid(self) -> str:
        return f"{self.symbol}#{self.k}"


def _mi(ts: int) -> int:
    from datetime import UTC, datetime

    d = datetime.fromtimestamp(ts / 1000, UTC)
    return d.year * 12 + d.month - 1


def build_epochs(
    symbol: str, candles: list[tuple[int, float, float]]
) -> tuple[list[Epoch], list[int]]:
    """Epochs and, per candle, its epoch index. Breaks use only the candle at which they appear:
    >= GAP_MONTHS whole calendar months without a candle before it, or a close ratio to the previous
    candle >= JUMP or <= 1/JUMP. Whether a jump is a crash, redenomination, migration or ticker reuse
    cannot be decided from candles; all are treated conservatively as a new epoch (fresh history)."""
    epochs: list[Epoch] = []
    idx: list[int] = []
    cur_start = cur_n = 0
    reason = "first_candle"
    for i, (t, c, _qv) in enumerate(candles):
        brk = None
        if i:
            pt, pc, _ = candles[i - 1]
            if _mi(t) - _mi(pt) - 1 >= GAP_MONTHS:
                brk = "gap"
            elif pc > 0 and c > 0 and (c / pc >= JUMP or c / pc <= 1 / JUMP):
                brk = "jump_up" if c > pc else "jump_down"
        if i == 0 or brk:
            if i:
                epochs.append(
                    Epoch(symbol, len(epochs), cur_start, reason, candles[i - 1][0], cur_n)
                )
            cur_start, cur_n, reason = t, 0, brk or "first_candle"
        cur_n += 1
        idx.append(len(epochs))
    if candles:
        epochs.append(Epoch(symbol, len(epochs), cur_start, reason, candles[-1][0], cur_n))
    return epochs, idx


def truncate(candles: list[tuple[int, float, float]], t_ms: int) -> list[tuple[int, float, float]]:
    """Only candles completed at ``t_ms`` (open + 1 day <= T)."""
    return [c for c in candles if c[0] + DAY <= t_ms]


# ---------------------------------------------------------------------------- eligibility
def eligible_epoch(candles, idx, t_ms: int, thr: float, ts: list[int] | None = None):
    """(epoch index, index of the latest completed candle) if eligible at T, else None.
    Uses completed candles of the latest candle's epoch only."""
    ts = ts if ts is not None else [c[0] for c in candles]
    n = bisect_left(ts, t_ms - DAY + 1)  # candles with open <= T - 1 day (completed at T)
    if n == 0:
        return None
    e = idx[n - 1]
    lo = t_ms - WINDOW_DAYS * DAY
    vols = []
    for j in range(n - 1, -1, -1):
        if candles[j][0] < lo or idx[j] != e:
            break
        vols.append(candles[j][2])
    if len(vols) < MIN_DAYS or statistics.median(vols) < thr:
        return None
    return e, n - 1


def month_starts(first: str = "2017-09", last: str = "2025-06") -> list[str]:
    y, m = map(int, first.split("-"))
    out = []
    while f"{y}-{m:02d}" <= last:
        out.append(f"{y}-{m:02d}")
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def ms_of(ym: str) -> int:
    return da.month_bounds_ms(ym)[0]


def membership(
    series: dict[str, list[tuple[int, float, float]]],
    classes: dict[str, dict],
    dates: list[str],
    thresholds: dict[str, float] = THRESHOLDS,
) -> list[tuple[str, str, str, int]]:
    """Rows (date, threshold, epoch_id, days_since_last_candle) sorted. Non-asset classes never enter."""
    if any(s not in classes for s in series):
        raise ClassificationError("unreviewed symbol in series")
    pre = {
        s: (c, build_epochs(s, c)[1], [x[0] for x in c])
        for s, c in series.items()
        if classes[s]["class"] == "asset"
    }
    rows = []
    for d in dates:
        t = ms_of(d)
        for tn, thr in thresholds.items():
            for s in sorted(pre):
                c, idx, ts = pre[s]
                hit = eligible_epoch(c, idx, t, thr, ts)
                if hit is not None:
                    e, last = hit
                    rows.append((d, tn, f"{s}#{e}", (t - (c[last][0] + DAY)) // DAY))
    return sorted(rows)


# ---------------------------------------------------------------------------- tables, hashes
def csv_text(header: list[str], rows) -> str:
    b = io.StringIO()
    w = csv.writer(b, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return b.getvalue()


def epochs_table(series) -> list[Epoch]:
    out: list[Epoch] = []
    for s in sorted(series):
        out += build_epochs(s, series[s])[0]
    return out


def dataset_hash(parts: dict[str, str], params: dict) -> str:
    return sha(canon({"parts": parts, "params": params}))


def epoch_keys(epochs: list[Epoch], cutoff_ms: int) -> list[tuple]:
    """Epoch facts observable at ``cutoff_ms`` (start, reason; end only for closed epochs)."""
    out = []
    for i, e in enumerate(epochs):
        if e.start + DAY > cutoff_ms:
            continue
        nxt = epochs[i + 1] if i + 1 < len(epochs) and epochs[i + 1].symbol == e.symbol else None
        closed = nxt is not None and nxt.start + DAY <= cutoff_ms
        out.append((e.eid, e.start, e.start_reason, e.end if closed else None))
    return out
