"""The five pre-evaluation checks required by the owner, as executable tests."""

import dataclasses
import inspect
import json

import numpy as np
import pandas as pd

from quantlab import phase4
from quantlab import protocol as P
from quantlab.costs import BASE, STRESS
from quantlab.execution import History, PriceData
from quantlab.family_a import (
    FamilyAConfig,
    FamilyAStrategy,
    exec_config,
    score_and_vol,
    target_weight,
)


SPEC = json.loads((P.QUANT_DIR / "protocol" / "protocol_v5_family_a.json").read_text())
IDX = pd.date_range("2023-01-01", periods=300 * 24, freq="1h", tz="UTC")


def candles(listing_day=0, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, len(IDX))))
    df = pd.DataFrame(
        {
            "date": IDX,
            "open": np.r_[100.0, c[:-1]],
            "high": c * 1.002,
            "low": c * 0.998,
            "close": c,
            "volume": 100.0,
        }
    )
    return df.iloc[listing_day * 24 :].reset_index(drop=True)


# 1. no future information in execution or liquidity decisions -> tests/test_liquidity.py, test_family_a.py
def test_check1_liquidity_source_reads_only_indices_before_the_executing_candle():
    from quantlab import execution

    src = inspect.getsource(execution.run)
    assert "data.volume[i - LIQ_LOOKBACK : i, j]" in src and "data.volume[i," not in src
    assert execution.LIQ_LOOKBACK == 24 and exec_config().max_participation == 0.10


# 2. daily signals use completed candles only
def test_check2_signals_are_computed_at_midnight_from_completed_days_and_ignore_the_current_candle():
    data = PriceData({"A": candles()}, IDX)
    strat = FamilyAStrategy(FamilyAConfig(), 1)
    i = 250 * 24  # a midnight candle
    from quantlab.execution import PortfolioView

    view = PortfolioView(IDX[i], 1000.0, 1000.0, {}, False, 0.0, 1.0)
    base = strat.on_candle(IDX[i], History(data, i), view)
    spoiled = {
        "A": candles().assign(
            close=lambda d: np.where(np.arange(len(d)) >= i, 1e-3, d["close"]),
            open=lambda d: np.where(np.arange(len(d)) >= i, 1e-3, d["open"]),
        )
    }
    again = strat.on_candle(IDX[i], History(PriceData(spoiled, IDX), i), view)
    assert [(o.pair, o.side, round(o.notional, 9)) for o in base] == [
        (o.pair, o.side, round(o.notional, 9)) for o in again
    ] and base
    assert (
        strat.on_candle(IDX[i + 5], History(data, i + 5), view) == []
    )  # not at midnight: no decision


# 3. warm-up and missing history follow the frozen specification (fail closed)
def test_check3_young_assets_get_zero_weight_until_their_filters_exist():
    cfg = FamilyAConfig()
    young = pd.Series(
        np.linspace(100, 130, 40), index=pd.date_range("2023-01-01", periods=40, freq="1D")
    )
    score, sigma = score_and_vol(young, cfg)
    assert (
        score == 0.0 and np.isfinite(sigma) and target_weight(score, sigma, 8, cfg) == 0.0
    )  # A1/A0 stay in cash
    s_v0, sig_v0 = score_and_vol(young, FamilyAConfig(trend=False))
    assert (
        target_weight(s_v0, sig_v0, 8, FamilyAConfig(trend=False)) > 0
    )  # V0 needs only 31 days of volatility
    assert "SMA(200) needs 200 completed days" in SPEC["universe"]["warmup"]
    assert target_weight(1.0, float("nan"), 8, cfg) == 0.0


# 4. comparable execution and cost assumptions
def test_check4_variants_and_stress_share_every_assumption_except_the_stated_one():
    a, s = exec_config(), exec_config(costs=STRESS)
    diff = {f.name for f in dataclasses.fields(a) if getattr(a, f.name) != getattr(s, f.name)}
    assert (
        diff == {"costs"}
        and a.costs == BASE
        and s.costs.fee == 2 * BASE.fee
        and s.costs.slippage == 2 * BASE.slippage
    )
    assert "BASE" in inspect.getsource(
        phase4.benchmark_set
    )  # benchmarks: same fee/slippage rates ...
    # ... but NOT the same liquidity and breaker constraints: disclosed, definitions unchanged
    disclosed = json.dumps(SPEC)
    assert "benchmark" in disclosed.lower() and "breaker" in disclosed.lower()


# 5. manifests and implementation hashes
def test_check5_all_freezes_and_amendments_verify():
    assert P.verify_all() == []
