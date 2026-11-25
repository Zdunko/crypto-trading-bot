"""Tests for OHLCV validation: each defect class must be detected, clean data must pass."""

import pandas as pd
import pytest
from synth import random_walk_ohlcv

from quantlab.data_validation import (
    MAX_GAP_HOURS,
    canonical_hash,
    dataset_hash,
    main,
    pair_file,
    validate_pair,
)


START = pd.Timestamp("2024-01-01", tz="UTC")
END = pd.Timestamp("2024-03-01", tz="UTC")  # 60 days = 1440 hourly candles


def _clean(n: int = 1440) -> pd.DataFrame:
    return random_walk_ohlcv(n, seed=1)


def _problems(df: pd.DataFrame) -> str:
    return "; ".join(validate_pair(df, "X/USDT", START, END).problems)


def test_clean_data_passes():
    rep = validate_pair(_clean(), "X/USDT", START, END)
    assert rep.ok, rep.problems
    assert rep.candles_in_window == 1440
    assert rep.missing == 0
    assert len(rep.sha256) == 64


def test_missing_candles_and_gap_detected():
    df = _clean().drop(index=range(100, 100 + MAX_GAP_HOURS + 5)).reset_index(drop=True)
    rep = validate_pair(df, "X/USDT", START, END)
    assert rep.missing == MAX_GAP_HOURS + 5
    assert rep.gaps == 1
    assert rep.max_gap_hours == MAX_GAP_HOURS + 5
    assert "missing fraction" in "; ".join(rep.problems)
    assert "gap of" in "; ".join(rep.problems)


def test_small_gap_below_tolerance_is_not_blocking():
    df = _clean().drop(index=[500]).reset_index(drop=True)  # 1 of 1440 = 0.07 %
    rep = validate_pair(df, "X/USDT", START, END)
    assert rep.missing == 1 and rep.ok


def test_duplicates_detected():
    df = pd.concat([_clean(), _clean().iloc[[10]]], ignore_index=True)
    assert "duplicate" in _problems(df)


def test_out_of_order_detected():
    df = _clean()
    df.loc[[20, 21], "date"] = df.loc[[21, 20], "date"].to_numpy()
    assert "out-of-order" in _problems(df)


def test_impossible_ohlc_detected():
    df = _clean()
    df.loc[30, "high"] = df.loc[30, "low"] * 0.5
    assert "impossible OHLC" in _problems(df)


@pytest.mark.parametrize(
    "col,value,text",
    [("close", float("nan"), "NaN"), ("open", 0.0, "non-positive"), ("volume", -1.0, "negative")],
)
def test_bad_values_detected(col, value, text):
    df = _clean()
    df.loc[40, col] = value
    assert text in _problems(df)


def test_empty_and_out_of_window():
    assert "no data" in _problems(_clean().iloc[0:0])
    late = _clean().assign(date=lambda d: d["date"] + pd.Timedelta(days=400))
    assert "no candles inside the window" in _problems(late)


def test_hash_is_stable_and_only_covers_window():
    base = _clean(1600)  # extends 160 candles beyond END
    h1 = validate_pair(base, "X/USDT", START, END).sha256
    h2 = validate_pair(base.iloc[:1500], "X/USDT", START, END).sha256  # still covers the window
    assert h1 == h2, "candles after the window must not change the hash"
    changed = base.copy()
    changed.loc[5, "close"] += 0.01
    assert validate_pair(changed, "X/USDT", START, END).sha256 != h1


def test_canonical_hash_independent_of_row_order():
    df = _clean(50)
    assert canonical_hash(df) == canonical_hash(df.sample(frac=1.0, random_state=3))


def test_dataset_hash_depends_on_every_pair():
    a = validate_pair(_clean(), "A/USDT", START, END)
    b = validate_pair(random_walk_ohlcv(1440, seed=2), "B/USDT", START, END)
    assert dataset_hash([a, b]) == dataset_hash([b, a])
    b2 = validate_pair(random_walk_ohlcv(1440, seed=3), "B/USDT", START, END)
    assert dataset_hash([a, b]) != dataset_hash([a, b2])


def test_cli_end_to_end(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"exchange": {"pair_whitelist": ["A/USDT", "B/USDT"]}}')
    for pair in ("A/USDT", "B/USDT"):
        _clean().to_feather(pair_file(tmp_path, pair))
    args = [
        "--datadir",
        str(tmp_path),
        "--config",
        str(cfg),
        "--start",
        "2024-01-01",
        "--end",
        "2024-03-01",
    ]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "DATA_REPORT_JSON_BEGIN" in out and "Dataset sha256" in out
    digest = out.split("Dataset sha256 (window only): `")[1].split("`")[0]
    assert main([*args, "--expect-hash", digest]) == 0
    assert main([*args, "--expect-hash", "0" * 64]) == 1
    pair_file(tmp_path, "B/USDT").unlink()
    assert main(args) == 1  # missing file is blocking
