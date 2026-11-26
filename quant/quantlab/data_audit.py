"""S3 data-feasibility audit primitives (pure, synthetic-testable, no network or evaluation).

Kline row layout (Binance Vision): open_time, open, high, low, close, volume, close_time,
quote_volume, trades, taker_base, taker_quote, ignore. Rows are lists of strings.

Everything here uses only data strictly before the date it reports on (no look-ahead) and never
loads holdout months: :func:`assert_dev_month` is the single guard.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any


DEV_END_EXCLUSIVE = "2025-07"  # YYYY-MM; months >= this are holdout and must never be read
MS = {"1d": 86_400_000, "1h": 3_600_000}
FATAL = frozenset(
    {
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
    }
)
# warnings: missing candles (gaps) and zero-volume candles are reported but not fatal on their own
WARN = frozenset({"gap", "zero_volume", "flat_candle", "extra_rows"})


def assert_dev_month(ym: str) -> None:
    if ym >= DEV_END_EXCLUSIVE:
        raise ValueError(f"holdout guard: month {ym} is not a development month")


def to_ms(ts: int) -> int:
    """Normalise a kline timestamp to milliseconds (13 digits = ms, 16 digits = microseconds)."""
    n = len(str(abs(ts)))
    if n == 13:
        return ts
    if n == 16:
        return ts // 1000
    raise ValueError(f"unrecognised timestamp unit ({n} digits): {ts}")


def month_bounds_ms(ym: str) -> tuple[int, int]:
    import calendar
    from datetime import UTC, datetime

    y, m = map(int, ym.split("-"))
    a = datetime(y, m, 1, tzinfo=UTC)
    b = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=UTC)
    del calendar
    return int(a.timestamp() * 1000), int(b.timestamp() * 1000)


@dataclass
class FileReport:
    rows: int = 0
    expected_rows: int = 0
    findings: dict[str, int] = field(default_factory=dict)
    missing_candles: int = 0  # inside the first..last candle span only
    leading_missing: int = 0
    trailing_missing: int = 0
    zero_volume_share: float = 0.0
    ts_digits: int = 0

    @property
    def fatal(self) -> list[str]:
        return sorted(k for k in self.findings if k in FATAL)

    @property
    def quarantined(self) -> bool:
        return bool(self.fatal)

    def add(self, key: str, n: int = 1) -> None:
        self.findings[key] = self.findings.get(key, 0) + n


def check_candles(rows: list[list[str]], interval: str, ym: str) -> FileReport:  # noqa: C901
    """Audit one monthly kline file. Classifies every defect; never repairs or drops silently."""
    step = MS[interval]
    lo, hi = month_bounds_ms(ym)
    rep = FileReport(expected_rows=(hi - lo) // step)
    if not rows:
        rep.add("empty")
        return rep
    parsed: list[tuple[int, float, float, float, float, float]] = []
    for r in rows:
        try:
            if len(r) < 8:
                raise ValueError("columns")
            ts = int(r[0])
            vals = [float(x) for x in r[1:6]]
            if not all(math.isfinite(v) for v in vals):
                raise ValueError("non-finite")
            parsed.append((ts, *vals))  # type: ignore[arg-type]
        except (ValueError, IndexError):
            rep.add("malformed_row")
    rep.rows = len(rows)
    if not parsed:
        return rep
    rep.ts_digits = len(str(parsed[0][0]))
    ts_ms: list[int] = []
    for p in parsed:
        try:
            ts_ms.append(to_ms(p[0]))
        except ValueError:
            rep.add("bad_timestamp_unit")
            ts_ms.append(-1)
    seen = set()
    prev = None
    for t in ts_ms:
        if t < 0:
            continue
        if t < lo or t >= hi:
            rep.add("outside_month")
        if (t - lo) % step != 0:
            rep.add("misaligned_timestamp")
        if t in seen:
            rep.add("duplicate_timestamp")
        seen.add(t)
        if prev is not None and t < prev:
            rep.add("out_of_order")
        prev = t
    if len(parsed) > rep.expected_rows:
        # exact repetition of the whole file (e.g. 4x blocks) is a distinct, named defect
        n = len(parsed) // max(1, rep.expected_rows)
        if (
            n >= 2
            and len(parsed) == n * rep.expected_rows
            and parsed[: len(parsed) // n] * n == parsed
        ):
            rep.add("repeated_block")
        else:
            rep.add("extra_rows", len(parsed) - rep.expected_rows)
    zero = 0
    for _ts, o, h, low, c, v in parsed:
        if min(o, h, low, c) <= 0:
            rep.add("nonpositive_price")
        if v < 0:
            rep.add("negative_volume")
        if h < max(o, c) - 1e-12 * h or low > min(o, c) + 1e-12 * max(low, 1e-300) or low > h:
            rep.add("ohlc_inconsistent")
        if v == 0:
            zero += 1
        if h == low and v == 0:
            rep.add("flat_candle")
    rep.zero_volume_share = zero / len(parsed)
    if zero:
        rep.add("zero_volume", zero)
    uniq = sorted({t for t in ts_ms if lo <= t < hi and (t - lo) % step == 0})
    if uniq:
        # leading/trailing absence = partial month (listing/delisting inside it), not a gap
        rep.leading_missing = (uniq[0] - lo) // step
        rep.trailing_missing = (hi - step - uniq[-1]) // step
        rep.missing_candles = max(0, (uniq[-1] - uniq[0]) // step + 1 - len(uniq))
    if rep.missing_candles:
        rep.add("gap", rep.missing_candles)
    return rep


# ---------------------------------------------------------------- point-in-time liquidity
def pit_eligible(
    daily: dict[int, tuple[float, float]],
    as_of_ms: int,
    threshold: float,
    window_days: int = 90,
    min_days: int = 60,
) -> bool:
    """Eligibility at ``as_of_ms`` using only daily candles with open time strictly < as_of_ms.

    ``daily`` maps open-time (ms) -> (close, quote_volume). The median is over candles present in
    the window (S1 rule): >= ``min_days`` of ``window_days`` previous days, median quote volume
    >= ``threshold``.
    """
    day = MS["1d"]
    start = as_of_ms - window_days * day
    vols = [qv for t, (_c, qv) in daily.items() if start <= t < as_of_ms]
    if len(vols) < min_days:
        return False
    return statistics.median(vols) >= threshold


# ---------------------------------------------------------------- identity / structure flags
def coverage_breaks(present_months: list[str], min_gap_months: int = 2) -> list[tuple[str, str]]:
    """Gaps of >= ``min_gap_months`` missing months between first and last present month."""
    if not present_months:
        return []
    ms = sorted(set(present_months))
    out = []
    for a, b in pairwise(ms):
        (y1, m1), (y2, m2) = map(int, a.split("-")), map(int, b.split("-"))
        missing = (y2 - y1) * 12 + (m2 - m1) - 1
        if missing >= min_gap_months:
            out.append((a, b))
    return out


def price_jumps(
    daily: dict[int, tuple[float, float]], ratio: float = 10.0
) -> list[tuple[int, float]]:
    """Consecutive close ratios >= ratio or <= 1/ratio (redenomination/migration signature)."""
    ts = sorted(daily)
    out = []
    for a, b in pairwise(ts):
        if daily[a][0] > 0 and daily[b][0] > 0:
            r = daily[b][0] / daily[a][0]
            if r >= ratio or r <= 1 / ratio:
                out.append((b, r))
    return out


def identity_flags(
    present_months: list[str], daily: dict[int, tuple[float, float]]
) -> dict[str, Any]:
    br = coverage_breaks(present_months)
    pj = price_jumps(daily)
    return {"coverage_breaks": br, "price_jumps": pj, "flagged": bool(br or pj)}


# ---------------------------------------------------------------- regimes (descriptive only)
def regime_label(closes_before: list[float], up: float = 0.30, down: float = -0.20) -> str:
    """Label from trailing closes strictly before the date: last/first - 1 vs fixed bounds."""
    if len(closes_before) < 2 or closes_before[0] <= 0:
        return "unknown"
    r = closes_before[-1] / closes_before[0] - 1
    return "bull" if r >= up else "bear" if r <= down else "sideways"


# ---------------------------------------------------------------- statistics helpers
def wilson_upper(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 1.0
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + margin) / d)


def evaluate_gates(criteria: dict, m: dict[str, Any]) -> dict[str, Any]:
    """Apply the pre-registered criteria (s3_criteria.json) to measurements; no thresholds live here
    except those read from the criteria file."""
    thr = {c["id"]: c for c in criteria["criteria"]}
    res: dict[str, dict[str, Any]] = {}

    def put(cid: str, ok: bool | None, value: Any) -> None:
        res[cid] = {"pass": ok, "value": value}

    put("L1", m["L1_permitted"], m["L1_permitted"])
    put("L2", None, m["L2_note"])
    put("I1", m["checksum_share"] >= thr["I1"]["threshold"], m["checksum_share"])
    put("Q1", m["daily_quarantine_share"] <= thr["Q1"]["threshold"], m["daily_quarantine_share"])
    put("Q2", m["hourly_wilson_upper"] <= thr["Q2"]["threshold"], m["hourly_wilson_upper"])
    put("U1", m["u1_min_eligible_1M"] >= thr["U1"]["threshold"], m["u1_min_eligible_1M"])
    put("U2", m["u2_share_ge30_5M"] >= thr["U2"]["threshold"], m["u2_share_ge30_5M"])
    put(
        "U3",
        m["u3_min_eligible_1M_after_exclusions"] >= thr["U1"]["threshold"],
        m["u3_min_eligible_1M_after_exclusions"],
    )
    put("S1", m["s1_dead_retained_share"] >= thr["S1"]["threshold"], m["s1_dead_retained_share"])
    put("S2", None, m["s2_dead_share_by_cohort"])
    put(
        "R1",
        all(v >= thr["R1"]["threshold"] for v in m["r1_months_by_regime"].values()),
        m["r1_months_by_regime"],
    )
    put("P1", m["p1_identical"], m["p1_identical"])
    put(
        "C1",
        m["c1_storage_gb"] <= 2.0 and m["c1_download_hours"] <= 3.0,
        {"gb": m["c1_storage_gb"], "hours": m["c1_download_hours"]},
    )
    put("T1", None, m["t1"])
    gates = [k for k, v in res.items() if v["pass"] is not None]
    failed = [k for k in gates if not res[k]["pass"]]
    needs_exclusions = bool(m.get("exclusions_required"))
    verdict = "NO_GO" if failed else ("CONDITIONAL_GO" if needs_exclusions else "GO")
    return {"gates": res, "failed": failed, "verdict": verdict}
