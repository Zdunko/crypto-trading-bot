"""Active-window statistics and layered reporting; reconciliation with the stored Family A evaluation numbers."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantlab.active_stats import active_stats, layered_report, signal_information
from quantlab.risk_v2 import RiskStateMachine, RiskV2Config


FAM = json.loads(
    (
        Path(__file__).resolve().parents[1] / "reports" / "family_a" / "evaluation_result.json"
    ).read_text()
)


def stats_for(name):
    eq, ex = FAM["series_daily"][name], FAM["exposure_daily"][name]
    k = min(len(eq), len(ex))
    return active_stats(eq[:k], ex[:k], 1000.0)


def test_reconciles_the_family_a_figures_that_were_reported_on_different_denominators():
    a1, a0, v0 = stats_for("A1"), stats_for("A0"), stats_for("V0")
    assert a1["trading_window_days"] == pytest.approx(798, abs=5) and a1[
        "invested_days"
    ] == pytest.approx(257, abs=5)
    assert a0["trading_window_days"] == pytest.approx(11, abs=2) and v0[
        "trading_window_days"
    ] == pytest.approx(143, abs=5)
    # exposure over the calendar vs over the trading window (the earlier reports mixed these)
    assert a1["exposure_avg_calendar"] == pytest.approx(0.030, abs=0.002) and a1[
        "exposure_avg_window"
    ] == pytest.approx(0.062, abs=0.004)
    assert a1["time_in_market_calendar"] == pytest.approx(0.156, abs=0.005) and a1[
        "time_in_market_window"
    ] == pytest.approx(0.32, abs=0.02)
    assert a0["exposure_avg_window"] == pytest.approx(0.656, abs=0.1) and v0[
        "exposure_avg_window"
    ] == pytest.approx(0.232, abs=0.02)
    # zero-return days dominate the calendar after the halt
    assert a1["zero_return_share_calendar"] > 0.8 and a0["zero_return_share_calendar"] > 0.99


def test_statistical_power_is_reported_on_the_window_and_on_invested_days_and_never_exceeds_raw_n():
    a1 = stats_for("A1")
    assert (
        a1["window"]["effective_n"] <= a1["window"]["n"]
        and a1["invested"]["effective_n"] <= a1["invested"]["n"]
    )
    assert a1["window"]["min_detectable_sharpe"] == pytest.approx(
        1.68, abs=0.1
    )  # as quoted in the S1 documentation
    assert (
        a1["invested"]["min_detectable_sharpe"] > a1["window"]["min_detectable_sharpe"]
    )  # invested days: conservative
    assert stats_for("A0")["window"]["min_detectable_sharpe"] > 10  # 11 days carry no information


def test_synthetic_cases_by_hand():
    eq = [1000.0] * 5 + [1010.0, 1020.0, 1030.0, 1020.0, 1020.0] + [1020.0] * 10
    ex = [0.0] * 5 + [0.5, 0.5, 0.5, 0.5, 0.0] + [0.0] * 10
    s = active_stats(eq, ex, 1000.0)
    assert (
        s["calendar_days"] == 20
        and s["trading_window_days"] == 10
        and s["idle_days_after_window"] == 10
    )
    assert s["invested_days"] == 5
    assert s["exposure_avg_window"] == pytest.approx(0.2) and s[
        "exposure_avg_calendar"
    ] == pytest.approx(0.1)
    empty = active_stats([1000.0] * 10, [0.0] * 10, 1000.0)
    assert (
        empty["trading_window_days"] == 0
        and empty["invested_days"] == 0
        and empty["exposure_avg_window"] is None
    )


def test_layered_report_keeps_the_four_layers_separate_and_carries_the_risk_flags():
    m = RiskStateMachine.new(RiskV2Config(), 1000.0)
    for i, e in enumerate((1000.0, 840.0)):
        m.step(pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(hours=i), e, e)
    rep = layered_report(stats_for("A1"), m.report(), {"total_cost": 3.4})
    assert set(rep) == {"L1_signal", "L2_portfolio", "L3_execution", "L4_risk"}
    assert (
        rep["L4_risk"]["final_state"] == "FLAT_COOLDOWN"
        and rep["L4_risk"]["safety_disqualified"] is False
    )
    assert (
        rep["L3_execution"] == {"total_cost": 3.4} and "exposure_avg_window" in rep["L2_portfolio"]
    )


def test_signal_information_on_a_known_relationship():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=200, freq="1D")
    score = pd.DataFrame(rng.normal(size=(200, 5)), index=idx, columns=list("ABCDE"))
    ret = score * 0.01 + rng.normal(scale=0.01, size=(200, 5))
    info = signal_information(score, ret)
    assert info["ic"] > 0.3 and info["hit_rate"] > 0.55 and info["n"] == 1000
    assert signal_information(score * 0, ret)["ic"] is None
