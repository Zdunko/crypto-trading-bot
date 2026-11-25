"""Offline dry run of the evaluation runner on synthetic data (the CI run must not fail on code)."""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from quantlab import family_a_eval as fe
from quantlab import protocol as P


PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]


def synthetic(n_days=620, seed=0):
    idx = pd.date_range("2021-06-01", periods=n_days * 24, freq="1h", tz="UTC")
    out = {}
    for k, pair in enumerate(PAIRS):
        rng = np.random.default_rng(seed + k)
        daily = rng.normal(0.002, 0.03, n_days)
        c = 100 * np.exp(np.cumsum(np.repeat(daily / 24, 24) + rng.normal(0, 0.002, len(idx))))
        o = np.r_[100.0, c[:-1]]
        out[pair] = pd.DataFrame({"date": idx, "open": o, "high": np.maximum(o, c) * 1.002,
                                  "low": np.minimum(o, c) * 0.998, "close": c, "volume": rng.uniform(5, 50, len(idx))})  # fmt: skip
    return out


@pytest.fixture(scope="module")
def result():
    proto = copy.deepcopy(P.load_protocol())
    proto["periods"]["evaluation"] = {"start": "2022-06-01", "end_exclusive": "2022-10-01"}
    proto["walk_forward"] = {"months": 2, "min_tail_months": 1}
    proto["bootstrap"].update(n=60, block_days=5)
    spec = json.loads((P.QUANT_DIR / "protocol" / "protocol_v5_family_a.json").read_text())
    cuts = {
        "mutation": ("2022-07-15", "2022-09-01"),
        "volume": "2022-08-01",
        "restart": "2022-08-15",
    }
    return fe.run_all(proto, spec, candles=synthetic(), cuts=cuts)


def test_runner_produces_every_requested_section_for_all_variants(result):
    assert set(result["variants"]) == {"A1", "A0", "V0", "A1_stress"}
    for name in ("A1", "A0", "V0"):
        v = result["variants"][name]
        for key in ("stats", "annualised_return", "exposure_avg", "monthly", "windows", "regimes_trades", "regime_daily",
                    "costs", "breaker", "credibility", "criteria", "sharpe_ci95"):  # fmt: skip
            assert key in v, (name, key)
        ids = {r["id"] for r in v["criteria"]}
        assert {"T1a", "T1b", "T2", "T3", "T4", "T5", "T6", "T7a", "T7b", "T8", "T9", "T10"} <= ids
        t9 = next(r for r in v["criteria"] if r["id"] == "T9")
        assert t9["passed"] is None
    assert (
        next(r for r in result["variants"]["A0"]["criteria"] if r["id"] == "T6")["passed"] is None
    )
    assert (
        next(r for r in result["variants"]["A1"]["criteria"] if r["id"] == "T6")["passed"]
        is not None
    )
    assert set(result["benchmarks"]) == {"B1 equal-weight all 8", "B2 equal-weight ex-SOL", "B3 BTC+ETH", "B4 BTC", "B5 equal-weight monthly rebalanced"}  # fmt: skip
    assert len(result["hypotheses"]["holm_reject"]) == 2 and result["trials"] == 43


def test_causality_checks_run_for_each_variant_and_are_clean_on_synthetic_data(result):
    for name in ("A1", "A0", "V0"):
        c = result["causality"][name]
        assert len(c["checks"]) == 4 and c["clean"], c


def test_series_for_charts_cover_variants_and_benchmarks(result):
    keys = set(result["series_daily"])
    assert {"A1", "A0", "V0", "A1_stress"} <= keys and any(k.startswith("B1") for k in keys)
    assert len(result["series_daily"]["A1"]) == len(result["exposure_daily"]["A1"]) > 100


def test_loader_refuses_nothing_but_cuts_every_candle_at_or_after_the_holdout(
    tmp_path, monkeypatch
):
    proto = P.load_protocol()
    cut = pd.Timestamp(proto["periods"]["evaluation"]["end_exclusive"], tz="UTC")
    df = pd.DataFrame({"date": pd.date_range(cut - pd.Timedelta("5h"), periods=10, freq="1h", tz="UTC"),
                       "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0})  # fmt: skip
    monkeypatch.setattr(fe, "load_candles", lambda p: {"BTC/USDT": df})
    out = fe.load_research_candles(proto)["BTC/USDT"]
    assert pd.to_datetime(out["date"], utc=True).max() < cut and len(out) == 5
