"""
Validation of downloaded OHLCV candles before any research uses them.

Checks are structural (gaps, duplicates, impossible candles) and never look at returns for
performance purposes. Every pair gets a canonical sha256 computed over the candles inside the
frozen window only, so a later run can prove that it analysed identical data even though the
files on disk keep growing.

CLI::

    python -m quantlab.data_validation --datadir user_data/data/okx \\
        --config quant/configs/base.json --start 2020-01-01 --end 2026-11-25 [--expect-hash FILE]

Exits 1 if any pair has a blocking problem (see ``BLOCKING``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


MAX_MISSING_FRACTION = 0.001  # more than 0.1 % missing candles is blocking
MAX_GAP_HOURS = 48  # a single gap longer than this is blocking
EXTREME_MOVE = 0.5  # |close/prev close - 1| above this is reported (warning only)
ZERO_VOLUME_WARN = 0.01
COLUMNS = ["open", "high", "low", "close", "volume"]
_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


@dataclass
class PairReport:
    pair: str
    first: str | None = None
    last: str | None = None
    candles_in_window: int = 0
    expected: int = 0
    missing: int = 0
    missing_fraction: float = 0.0
    gaps: int = 0
    max_gap_hours: int = 0
    duplicates: int = 0
    non_monotonic: int = 0
    nan_cells: int = 0
    ohlc_violations: int = 0
    non_positive_prices: int = 0
    negative_volume: int = 0
    zero_volume_fraction: float = 0.0
    extreme_moves: int = 0
    sha256: str = ""
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _epoch_seconds(dates: pd.Series) -> np.ndarray:
    return ((dates - _EPOCH) // pd.Timedelta("1s")).to_numpy(dtype="int64")


def canonical_hash(df: pd.DataFrame) -> str:
    """sha256 over (epoch seconds, o, h, l, c, v) of the rows, sorted by time."""
    ordered = df.sort_values("date")
    h = hashlib.sha256()
    h.update(_epoch_seconds(ordered["date"]).tobytes())
    h.update(ordered[COLUMNS].to_numpy(dtype="float64").tobytes())
    return h.hexdigest()


def validate_pair(
    df: pd.DataFrame, pair: str, start: pd.Timestamp, end: pd.Timestamp
) -> PairReport:
    """Validate hourly candles of one pair inside [start, end) (UTC)."""
    rep = PairReport(pair=pair)
    if df.empty:
        rep.problems.append("no data")
        return rep

    dates = pd.to_datetime(df["date"], utc=True)
    df = df.assign(date=dates)
    rep.non_monotonic = int((dates.diff().dropna() < pd.Timedelta(0)).sum())
    rep.duplicates = int(dates.duplicated().sum())

    win = df[(df["date"] >= start) & (df["date"] < end)].drop_duplicates("date").sort_values("date")
    rep.candles_in_window = len(win)
    if win.empty:
        rep.problems.append("no candles inside the window")
        return rep
    rep.first, rep.last = str(win["date"].iloc[0]), str(win["date"].iloc[-1])

    step = pd.Timedelta("1h")
    span = (win["date"].iloc[-1] - win["date"].iloc[0]) // step + 1
    rep.expected = int(span)
    rep.missing = int(span - len(win))
    rep.missing_fraction = rep.missing / rep.expected
    diffs = win["date"].diff().dropna()
    gap_hours = ((diffs // step) - 1)[diffs > step]
    rep.gaps = len(gap_hours)
    rep.max_gap_hours = int(gap_hours.max()) if len(gap_hours) else 0

    values = win[COLUMNS]
    rep.nan_cells = int(values.isna().sum().sum())
    o, h, low, c, v = (win[k] for k in COLUMNS)
    rep.ohlc_violations = int(((h < np.maximum(o, c)) | (low > np.minimum(o, c)) | (h < low)).sum())
    rep.non_positive_prices = int((win[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    rep.negative_volume = int((v < 0).sum())
    rep.zero_volume_fraction = float((v == 0).mean())
    rep.extreme_moves = int((c.pct_change().abs() > EXTREME_MOVE).sum())
    rep.sha256 = canonical_hash(win)

    for flag, text in [
        (rep.duplicates > 0, f"{rep.duplicates} duplicate timestamps"),
        (rep.non_monotonic > 0, f"{rep.non_monotonic} out-of-order timestamps"),
        (rep.nan_cells > 0, f"{rep.nan_cells} NaN cells"),
        (rep.ohlc_violations > 0, f"{rep.ohlc_violations} impossible OHLC candles"),
        (rep.non_positive_prices > 0, f"{rep.non_positive_prices} non-positive prices"),
        (rep.negative_volume > 0, f"{rep.negative_volume} negative volumes"),
        (
            rep.missing_fraction > MAX_MISSING_FRACTION,
            f"missing fraction {rep.missing_fraction:.4%} > {MAX_MISSING_FRACTION:.2%}",
        ),
        (rep.max_gap_hours > MAX_GAP_HOURS, f"gap of {rep.max_gap_hours} h > {MAX_GAP_HOURS} h"),
    ]:
        if flag:
            rep.problems.append(text)
    if rep.zero_volume_fraction > ZERO_VOLUME_WARN:
        rep.warnings.append(f"{rep.zero_volume_fraction:.2%} zero-volume candles")
    if rep.extreme_moves:
        rep.warnings.append(f"{rep.extreme_moves} hourly moves above {EXTREME_MOVE:.0%}")
    return rep


def pair_file(datadir: Path, pair: str, timeframe: str = "1h") -> Path:
    return datadir / f"{pair.replace('/', '_')}-{timeframe}.feather"


def validate_all(
    datadir: Path, pairs: list[str], start: pd.Timestamp, end: pd.Timestamp
) -> list[PairReport]:
    reports = []
    for pair in pairs:
        path = pair_file(datadir, pair)
        if not path.exists():
            rep = PairReport(pair=pair)
            rep.problems.append(f"file missing: {path.name}")
            reports.append(rep)
            continue
        reports.append(validate_pair(pd.read_feather(path), pair, start, end))
    return reports


def dataset_hash(reports: list[PairReport]) -> str:
    """One hash over all per-pair hashes (sorted by pair) - the identity of the dataset."""
    h = hashlib.sha256()
    for rep in sorted(reports, key=lambda r: r.pair):
        h.update(f"{rep.pair}:{rep.sha256}\n".encode())
    return h.hexdigest()


def to_markdown(reports: list[PairReport], digest: str) -> str:
    lines = [
        (
            "| Pair | First candle | Last candle | Candles | Missing | Max gap h | Zero-vol "
            "| Problems | Warnings |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r.pair} | {(r.first or '-')[:16]} | {(r.last or '-')[:16]} "
            f"| {r.candles_in_window} | {r.missing} ({r.missing_fraction:.3%}) "
            f"| {r.max_gap_hours} | {r.zero_volume_fraction:.2%} "
            f"| {'; '.join(r.problems) or 'none'} | {'; '.join(r.warnings) or '-'} |"
        )
    lines.append("")
    lines.append(f"Dataset sha256 (window only): `{digest}`")
    return "\n".join(lines)


def _pairs_from_config(path: str) -> list[str]:
    from freqtrade.configuration.load_config import load_from_files

    return list(load_from_files([path])["exchange"]["pair_whitelist"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--datadir", required=True)
    ap.add_argument(
        "--config", required=True, help="Freqtrade config whose pair_whitelist is the universe"
    )
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="exclusive")
    ap.add_argument("--expect-hash", default=None, help="fail if the dataset hash differs")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    start, end = pd.Timestamp(args.start, tz="UTC"), pd.Timestamp(args.end, tz="UTC")
    reports = validate_all(Path(args.datadir), _pairs_from_config(args.config), start, end)
    digest = dataset_hash(reports)
    md = to_markdown(reports, digest)
    print(md)
    payload = {
        "window": [str(start), str(end)],
        "dataset_sha256": digest,
        "pairs": [asdict(r) for r in reports],
    }
    print("DATA_REPORT_JSON_BEGIN")
    print(json.dumps(payload))
    print("DATA_REPORT_JSON_END")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=1))

    bad = [r for r in reports if not r.ok]
    if bad:
        print(f"DATA VALIDATION FAILED for {[r.pair for r in bad]}", file=sys.stderr)
        return 1
    if args.expect_hash and args.expect_hash != digest:
        print(f"DATASET HASH MISMATCH: expected {args.expect_hash}, got {digest}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
