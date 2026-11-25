"""Offline end-to-end test of the assessment/report pipeline on synthetic candles and trades."""

import copy
import importlib
import json

import numpy as np
import pandas as pd
import pytest
from synth import random_walk_ohlcv

from quantlab import phase3
from quantlab.costs import SCENARIOS
from quantlab.equity import buy_and_hold, close_matrix, hourly_index
from quantlab.protocol import load_protocol
from quantlab.report import render
from quantlab.validation import daily_regimes


PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


@pytest.fixture(scope="module")
def world():
    proto = copy.deepcopy(load_protocol())
    proto["pairs"] = PAIRS
    proto["bootstrap"].update(n=60, block_days=5)
    proto["periods"]["evaluation"] = {"start": "2021-01-01", "end_exclusive": "2022-07-01"}
    candles = {
        p: random_walk_ohlcv(24 * 800, seed=i + 1, vol=0.008, start="2020-06-01")
        for i, p in enumerate(PAIRS)
    }
    index = hourly_index("2021-01-01", "2022-07-01")
    closes = close_matrix(candles, index)
    bench, pairs = {}, []
    for name, scen in SCENARIOS.items():
        bench[name], pairs = buy_and_hold(candles, index, 1000.0, scen)
    bench["btc_base"], _ = buy_and_hold(candles, index, 1000.0, SCENARIOS["base"], ["BTC/USDT"])
    regimes = daily_regimes(candles["BTC/USDT"])
    ctx = phase3.Context(proto, candles, index, closes, regimes, bench, pairs, bias=None)
    return proto, ctx


def _raw_trades(ctx, fee: float, n: int = 260, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        pair = PAIRS[rng.integers(len(PAIRS))]
        i0 = int(rng.integers(0, len(ctx.index) - 200))
        i1 = i0 + int(rng.integers(3, 120))
        px = ctx.closes[pair].to_numpy()
        rows.append(
            {
                "pair": pair,
                "open_date": ctx.index[i0],
                "close_date": ctx.index[i1],
                "amount": 100.0 / px[i0],
                "open_rate": px[i0],
                "close_rate": px[i1],
                "fee_open": fee,
                "fee_close": fee,
                "exit_reason": ["exit_signal", "stop_loss", "force_exit"][int(rng.integers(3))],
            }
        )
    return pd.DataFrame(rows)


def test_assess_strategy_produces_complete_judged_result_and_report(world):
    proto, ctx = world
    raw = {k: _raw_trades(ctx, s.fee) for k, s in SCENARIOS.items()}
    res = phase3.assess_strategy("Synthetic", raw, [0.1, -0.1, 0.2, 0.3], ctx)

    assert {
        "stats",
        "benchmark",
        "windows",
        "regimes",
        "criteria",
        "verdict",
        "uncertainty",
    } <= set(res)
    assert res["stats"]["base"]["trades"] == 260
    assert res["stats"]["stress"]["net_return"] <= res["stats"]["base"]["net_return"]  # costs bite
    ids = [c["id"] for c in res["criteria"]]
    assert ids == ["T1a", "T1b", "T2", "T3", "T4", "T5", "T6", "T7a", "T7b", "T8", "T9", "T10"]
    assert res["verdict"]["validated_on_evaluation"] is False  # T10: no bias evidence supplied
    assert "T10" in res["verdict"]["failed"]
    assert len(res["windows"]) == 3  # 18 months = three 6-month windows
    assert res["uncertainty"]["profit_factor_ci"][0] < res["uncertainty"]["profit_factor_ci"][1]

    results = {
        "protocol_version": 2,
        "period": "evaluation",
        "range": proto["periods"]["evaluation"],
        "bench_pairs": ctx.bench_pairs,
        "benchmarks": {k: phase3.summarize(v, None, 1000.0) for k, v in ctx.bench.items()},
        "strategies": {
            "Synthetic": {**res, "variants": [{"param": "p", "value": 1, "net_return": 0.1}]}
        },
    }
    md = render(results, proto)
    for needle in (
        "## 1. Comparison",
        "## 2. Criteria",
        "## 3. Uncertainty",
        "Equal-weight",
        "REJECTED",
        "Survivorship",
    ):
        assert needle in md


def test_assessment_is_deterministic(world):
    _, ctx = world
    raw = {k: _raw_trades(ctx, s.fee) for k, s in SCENARIOS.items()}
    a = phase3.assess_strategy("S", raw, [0.1], ctx, judge=False)
    b = phase3.assess_strategy("S", raw, [0.1], ctx, judge=False)
    assert a["uncertainty"] == b["uncertainty"] and a["stats"] == b["stats"]


def test_zero_trades_does_not_crash_and_fails_criteria(world):
    _, ctx = world
    empty = {k: _raw_trades(ctx, s.fee, n=1).iloc[0:0] for k, s in SCENARIOS.items()}
    res = phase3.assess_strategy("Idle", empty, [], ctx)
    assert res["stats"]["base"]["trades"] == 0
    assert res["verdict"]["validated_on_evaluation"] is False
    assert {"T1a", "T2", "T5"} <= set(res["verdict"]["failed"])


def test_bias_evidence_flows_into_t10(world):
    _, ctx = world
    ctx2 = phase3.Context(**{**ctx.__dict__, "bias": {"strategies": {"S": {"clean": True}}}})
    raw = {k: _raw_trades(ctx, s.fee) for k, s in SCENARIOS.items()}
    ids = {c["id"]: c["passed"] for c in phase3.assess_strategy("S", raw, [0.1], ctx2)["criteria"]}
    assert ids["T10"] is True


def test_double_counting_is_impossible_through_the_pipeline(world):
    _, ctx = world
    wrong = {k: _raw_trades(ctx, 0.0015) for k in SCENARIOS}  # lumped fee from the old config
    with pytest.raises(ValueError, match="double-counting"):
        phase3.assess_strategy("S", wrong, [], ctx)


# ---------------------------------------------------------------- variants
def test_variant_generation_overrides_one_parameter_and_widens_warmup(tmp_path):
    name = phase3.make_variant("MomentumRoc", "ema_trend_period", 300, tmp_path)
    assert name == "MomentumRoc__ema_trend_period__300"
    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        cls = getattr(importlib.import_module(name), name)
    finally:
        sys.path.remove(str(tmp_path))
    assert cls.ema_trend_period == 300 and cls.roc_lookback == 240  # others untouched
    assert cls.startup_candle_count == 900  # 3 x 300 > base 600
    thr = phase3.make_variant("MomentumRoc", "roc_threshold", 0.02, tmp_path)
    assert (
        thr.endswith("0p02") and "startup_candle_count" not in (tmp_path / f"{thr}.py").read_text()
    )


def test_variants_cover_both_range_ends_for_every_strategy():
    proto = load_protocol()
    total = 0
    for s in proto["strategies"]:
        v = phase3.variants_of(s, proto["robustness"][s])
        total += len(v)
        assert len(v) == 2 * len(proto["robustness"][s])
        assert phase3.strategy_module(s)
    assert total == 22


def test_mixed_time_resolutions_like_real_feather_and_freqtrade_data(world):
    """Real candles are ms/us resolution and Freqtrade trades us; results must not change."""
    _, ctx = world
    ms = {
        p: df.assign(date=df["date"].astype("datetime64[ms, UTC]")) for p, df in ctx.candles.items()
    }
    index = ctx.index
    closes_ms = close_matrix(ms, index)
    pd.testing.assert_frame_equal(closes_ms, ctx.closes)
    assert daily_regimes(ms["BTC/USDT"]).equals(ctx.regimes)

    raw = {k: _raw_trades(ctx, s.fee) for k, s in SCENARIOS.items()}
    us = {
        k: v.assign(open_date=v["open_date"].astype("datetime64[us, UTC]"),
                    close_date=v["close_date"].astype("datetime64[us, UTC]"))
        for k, v in raw.items()
    }  # fmt: skip
    a = phase3.assess_strategy("S", raw, [0.1], ctx, judge=False)
    b = phase3.assess_strategy("S", us, [0.1], ctx, judge=False)

    def same(x, y):  # NaN-safe comparison
        return json.dumps(x, sort_keys=True, default=str) == json.dumps(
            y, sort_keys=True, default=str
        )

    assert same(a["stats"], b["stats"]) and same(a["regimes"], b["regimes"])
    bench_ms, _ = buy_and_hold(ms, index, 1000.0, SCENARIOS["base"])
    pd.testing.assert_series_equal(bench_ms, ctx.bench["base"])


def test_backtest_export_directory_exists_before_freqtrade_runs(tmp_path, monkeypatch):
    """First CI run failed: Freqtrade cannot store results in a directory that does not exist."""
    seen = {}

    def fake_ft(args, check=True):
        outdir = args[args.index("--backtest-directory") + 1]
        seen["exists"] = __import__("os").path.isdir(outdir)
        seen["fee"] = args[args.index("--fee") + 1]
        return ""

    monkeypatch.setattr(phase3, "USER_DATA", tmp_path)
    monkeypatch.setattr(phase3, "ft", fake_ft)
    monkeypatch.setattr(
        "freqtrade.data.btanalysis.load_backtest_data", lambda *a, **k: pd.DataFrame()
    )
    phase3.backtest_trades("TrendEmaCross", "quant/strategies", "20210101-20250701", 0.001, "x")
    assert seen == {"exists": True, "fee": "0.001"}
