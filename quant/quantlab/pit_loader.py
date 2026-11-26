"""S5 infrastructure: causal, fail-closed access to the frozen S4 point-in-time dataset.

Nothing here touches the network. A :class:`PitDataset` refuses to open unless the dataset tables match
the freeze record, and every read is checked against the manifest-pinned sha256 of the stored file.
Strict point-in-time rules: only COMPLETED candles (open + interval <= as_of) are returned, files of
months after ``as_of`` are never opened, quarantined/absent/altered data raise, and nothing at or after
the cutoff (2025-07-01) is ever served. No exception is swallowed into an empty result.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quantlab import pit_universe as pu
from quantlab.pit_fetch import DEV_END, Store


QUANT = Path(__file__).resolve().parents[1]
FREEZE = QUANT / "protocol/s4_freeze_record.json"
FIRST_DATE = "2017-09"
STEP = {"1d": 86_400_000, "1h": 3_600_000}


class PitError(Exception):
    """Base class: every failure mode of the loader is an explicit, specific exception."""


class FreezeMismatch(PitError): ...


class HoldoutError(PitError): ...


class UnknownSymbol(PitError): ...


class DataQuarantined(PitError): ...


class DataMissing(PitError): ...


class IntegrityError(PitError): ...


class StaleData(PitError): ...


def _norm_sha(b: bytes) -> str:
    return hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest()


def _gz_text(p: Path) -> str:
    with gzip.open(p, "rt", encoding="utf-8", newline="") as f:
        return f.read()


def _ts(as_of) -> pd.Timestamp:
    t = pd.Timestamp(as_of)
    if t.tzinfo is None:
        raise PitError("as_of must be timezone-aware (UTC)")
    return t.tz_convert("UTC")


def _month(t: pd.Timestamp) -> str:
    return f"{t.year}-{t.month:02d}"


def _cutoff_check(t: pd.Timestamp) -> None:
    if _month(t) >= DEV_END or t >= pd.Timestamp(DEV_END + "-01", tz="UTC"):
        raise HoldoutError(f"as_of {t} is at or after the holdout cutoff {DEV_END}-01")
    if _month(t) < FIRST_DATE:
        raise PitError(f"as_of {t} precedes the dataset ({FIRST_DATE})")


@dataclass
class PitDataset:
    dataset_dir: Path
    store: Store | None
    manifest: dict
    files: dict[tuple[str, str, str], dict]
    members: dict[tuple[str, str], list[tuple[str, int]]]
    listing: dict[str, list[str]]
    _daily_cache: dict

    @classmethod
    def open(
        cls,
        dataset_dir: str | Path,
        store_root: str | Path | None = None,
        freeze: dict | None = None,
    ) -> PitDataset:
        d = Path(dataset_dir)
        freeze = freeze if freeze is not None else json.loads(FREEZE.read_text(encoding="utf-8"))
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        # 1. tables hash to the manifest, the manifest hashes to the freeze record
        parts = {
            "files": pu.sha(_gz_text(d / "files.csv.gz")),
            "epochs": pu.sha(_gz_text(d / "epochs.csv.gz")),
            "membership": pu.sha(_gz_text(d / "membership.csv.gz")),
            "classification": _norm_sha((d / "asset_classification.json").read_bytes()),
        }
        if parts != man["parts"] or pu.dataset_hash(parts, man["params"]) != man["dataset_hash"]:
            raise FreezeMismatch("dataset tables do not match their manifest")
        if man["dataset_hash"] != freeze["dataset_hash"]:
            raise FreezeMismatch("dataset hash differs from the freeze record")
        for name, h in freeze.get("files", {}).items():
            if _norm_sha((d / name).read_bytes()) != h:
                raise FreezeMismatch(f"{name} differs from the freeze record")
        files = {
            (r["interval"], r["symbol"], r["month"]): r
            for r in csv.DictReader(_gz_text(d / "files.csv.gz").splitlines())
        }
        members: dict[tuple[str, str], list[tuple[str, int]]] = {}
        for r in csv.DictReader(_gz_text(d / "membership.csv.gz").splitlines()):
            members.setdefault((r["date"], r["threshold"]), []).append(
                (r["epoch_id"], int(r["days_since_last_candle"]))
            )
        listing = json.loads((d / "dev_window_listing.json").read_text(encoding="utf-8"))
        return cls(d, Store(store_root) if store_root else None, man, files, members, listing, {})

    # ------------------------------------------------------------------ universe
    def universe_at(self, as_of, threshold: str = "1M", max_stale_days: int = 3) -> list[str]:
        """Symbols eligible at the latest month start <= as_of, dropping members whose last completed
        candle was already more than ``max_stale_days`` old at that month start (point-in-time)."""
        t = _ts(as_of)
        _cutoff_check(t)
        m = _month(t)
        if threshold not in self.manifest["params"]["thresholds"]:
            raise PitError(f"unknown threshold {threshold}")
        rows = self.members.get(
            (m, threshold), []
        )  # no rows = nobody qualified that month (empty universe)
        return sorted(e.split("#")[0] for e, stale in rows if stale <= max_stale_days)

    def _symbol(self, symbol: str) -> list[str]:
        if symbol not in self.listing:
            raise UnknownSymbol(symbol)
        return self.listing[symbol]

    def candles(
        self, symbol: str, interval: str, as_of, start=None, allow_gaps: bool = False
    ) -> pd.DataFrame:
        """Completed candles of ``symbol`` with open >= start and open + interval <= as_of."""
        t = _ts(as_of)
        _cutoff_check(t)
        months = self._symbol(symbol)
        if self.store is None:
            raise DataMissing("no raw store attached")
        lo = _ts(start) if start is not None else None
        first, last = months[0], months[-1]
        step = STEP[interval]
        out: list[pd.DataFrame] = []
        m = first if lo is None else max(first, _month(lo))
        end_m = min(last, _month(t))
        while m <= end_m:  # months after as_of's month are never touched
            key = (interval, symbol, m)
            row = self.files.get(key)
            if row is None or m not in months:
                if allow_gaps:
                    m = _next(m)
                    continue
                raise DataMissing(f"{symbol} {interval} {m} is not in the dataset")
            if row["status"] == "quarantined":
                raise DataQuarantined(f"{symbol} {interval} {m}: {row['reasons']}")
            if row["status"] != "ok":
                raise DataMissing(f"{symbol} {interval} {m}: {row['status']}")
            out.append(self._read(symbol, interval, m, row))
            m = _next(m)
        if not out:
            return pd.DataFrame(
                columns=["date", "open", "high", "low", "close", "volume", "quote_volume"]
            )
        df = pd.concat(out, ignore_index=True).sort_values("date").reset_index(drop=True)
        done = df["date"] + pd.Timedelta(milliseconds=step) <= t
        df = df[done]
        if lo is not None:
            df = df[df["date"] >= lo]
        return df.reset_index(drop=True)

    def _read(self, symbol: str, interval: str, month: str, row: dict) -> pd.DataFrame:
        if self.store is None:
            raise DataMissing("no raw store attached")
        z = self.store.paths(symbol, interval, month)[0]
        if not z.exists():
            raise DataMissing(f"stored file missing: {z.name}")
        data = z.read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise IntegrityError(f"{z.name}: sha256 differs from the manifest")
        rows = pu.read_rows(data)
        from quantlab import data_audit as da

        ts = [da.to_ms(int(r[0])) for r in rows]
        return pd.DataFrame(
            {
                "date": pd.to_datetime(ts, unit="ms", utc=True),
                "open": [float(r[1]) for r in rows],
                "high": [float(r[2]) for r in rows],
                "low": [float(r[3]) for r in rows],
                "close": [float(r[4]) for r in rows],
                "volume": [float(r[5]) for r in rows],
                "quote_volume": [float(r[7]) for r in rows],
            }
        )

    # ------------------------------------------------------------------ freshness
    def last_daily_age(self, symbol: str, as_of) -> int:
        """Whole days between ``as_of`` and the end of the last completed daily candle (fail closed:
        no data at all raises)."""
        t = _ts(as_of)
        key = (symbol, t.normalize())
        if key not in self._daily_cache:
            start = t - pd.Timedelta(days=45)
            df = self.candles(symbol, "1d", t, start=start, allow_gaps=True)
            self._daily_cache[key] = None if df.empty else df["date"].iloc[-1]
        last = self._daily_cache[key]
        if last is None:
            raise StaleData(f"{symbol}: no completed daily candle in the 45 days before {t}")
        return int((t - (last + pd.Timedelta(days=1))).total_seconds() // 86_400)

    def tradable(
        self, symbol: str, as_of, threshold: str = "1M", max_stale_days: int = 3
    ) -> tuple[bool, str]:
        """(ok, reason) for opening a position: member at the month start AND a fresh candle now."""
        self._symbol(
            symbol
        )  # unknown symbols raise UnknownSymbol instead of looking like "not a member"
        if symbol not in self.universe_at(as_of, threshold, max_stale_days):
            return False, "not_member"
        try:
            age = self.last_daily_age(symbol, as_of)
        except StaleData:
            return False, "stale"
        return (age <= max_stale_days, "ok" if age <= max_stale_days else "stale")


def _next(m: str) -> str:
    y, mo = map(int, m.split("-"))
    return f"{y + (mo == 12)}-{1 if mo == 12 else mo + 1:02d}"


def pair_of(symbol: str) -> str:
    return f"{symbol[:-4]}/USDT"


def symbol_of(pair: str) -> str:
    return pair.replace("/", "")


def to_price_data(ds: PitDataset, symbols: list[str], interval: str, start, end):
    """Stage 0 engine input built only from candles completed at ``end``."""
    from quantlab.execution import PriceData

    idx = pd.date_range(
        _ts(start), _ts(end), freq={"1h": "h", "1d": "D"}[interval], inclusive="left"
    )
    candles = {
        pair_of(s): ds.candles(s, interval, end, start=start, allow_gaps=True) for s in symbols
    }
    return PriceData(candles, idx)
