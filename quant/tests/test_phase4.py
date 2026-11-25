"""Phase 4 engine pieces: recosted stress, exposure profile, benchmark rule, v3 protocol, report."""

import json

import numpy as np
import pandas as pd
import pytest

from quantlab import protocol as proto_mod
from quantlab.costs import BASE, STRESS, apply_costs, apply_costs_consistent, apply_costs_recosted
from quantlab.metrics import exposure_profile
from quantlab.phase4 import (
    ABLATION_FLAGS,
    ablation_source,
    annualized,
    bench_threshold,
    mark_t9_not_evaluated,
    parse_halts,
)
from quantlab.report4 import render


IDX = pd.date_range("2024-01-01", periods=48, freq="h", tz="UTC")


def trades(n=2, stop=False):
    rows = []
    for i in range(n):
        rows.append(
            {
                "pair": f"P{i}/USDT",
                "open_date": IDX[2 + i],
                "close_date": IDX[20 + i],
                "amount": 5.0,
                "open_rate": 100.0,
                "close_rate": 90.0 if stop else 110.0,
                "fee_open": BASE.fee,
                "fee_close": BASE.fee,
                "exit_reason": "stop_loss" if stop else "exit_signal",
            }
        )
    return pd.DataFrame(rows)


def test_recosted_keeps_positions_and_equals_apply_costs_on_scaled_amounts():
    base = apply_costs_consistent(trades(3, stop=True), BASE, 1000.0)
    stressed = apply_costs_recosted(base, STRESS)
    assert np.allclose(stressed["amount"], base["amount"])  # identical positions
    assert (stressed["profit_abs"] < base["profit_abs"]).all()  # costlier
    direct = apply_costs(base.assign(fee_open=STRESS.fee, fee_close=STRESS.fee), STRESS)
    assert np.allclose(stressed["profit_abs"], direct["profit_abs"])
    assert np.allclose(stressed["size_scale"], base["size_scale"])


def test_recosted_with_base_scenario_is_the_identity():
    base = apply_costs_consistent(trades(2), BASE, 1000.0)
    again = apply_costs_recosted(base, BASE)
    assert np.allclose(again["profit_abs"], base["profit_abs"])


def test_exposure_profile_is_cost_over_equity_and_peaks_when_positions_overlap():
    t = apply_costs(trades(2), BASE)
    eq = pd.Series(1000.0, index=IDX)
    prof = exposure_profile(t, eq)
    one = float(t["open_value"].iloc[0])
    assert prof["peak_gross_exposure"] == pytest.approx(2 * one / 1000.0, rel=0.01)
    assert 0 < prof["avg_gross_exposure"] < prof["peak_gross_exposure"]
    assert exposure_profile(t.iloc[0:0], eq)["peak_gross_exposure"] == 0.0


def test_benchmark_rule_takes_best_sortino_and_lowest_drawdown():
    stats = {
        "B1": {"sortino": 1.8, "max_drawdown": 0.90},
        "B4": {"sortino": 1.1, "max_drawdown": 0.77},
        "B3": {"sortino": 2.3, "max_drawdown": 0.80},
    }
    assert bench_threshold(stats) == {"sortino": 2.3, "max_drawdown": 0.77}


def test_annualized_and_parse_halts():
    assert annualized(1.0, 365.0) == pytest.approx(1.0)
    assert annualized(-1.0, 100.0) == -1.0
    assert np.isnan(annualized(0.5, 0))
    log = "x\nRISK_HALT 2022-05-12 dd=0.2100 equity=790.00 id=abc\ny"
    assert len(parse_halts(log)) == 1


def test_ablation_sources_are_valid_python_with_exactly_one_flag_off():
    assert len(ABLATION_FLAGS) == 6
    for flag in ABLATION_FLAGS.values():
        name, src = ablation_source("TrendEmaCrossR1", "trend_ema_cross_r1", flag)
        compile(src, name, "exec")
        assert src.count("=False") == 1 and f"{flag}=False" in src


def test_t9_is_reported_as_not_evaluated_and_never_as_validation():
    res = {
        "criteria": [
            {"id": "T2", "passed": True},
            {"id": "T9", "passed": False, "value": float("nan")},
            {"id": "T4", "passed": False},
        ]
    }
    mark_t9_not_evaluated(res)
    assert res["criteria"][1]["passed"] is None
    assert res["verdict"]["failed"] == ["T4"]
    assert res["verdict"]["validated_on_evaluation"] is False


# ---------------------------------------------------------------- protocol v3
def test_protocol_v3_is_consistent_with_code_and_frozen():
    assert proto_mod.consistency_errors_v3() == []
    assert proto_mod.verify_manifest_v3() == []


def test_v3_detects_a_changed_r1_parameter(tmp_path):
    import shutil

    q = tmp_path / "quant"
    shutil.copytree(
        proto_mod.QUANT_DIR, q, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache")
    )
    p = q / "protocol" / "protocol_v3.json"
    v3 = json.loads(p.read_text())
    v3["R1"]["risk_per_trade"] = 0.01
    p.write_text(json.dumps(v3))
    assert any("risk_per_trade" in e for e in proto_mod.consistency_errors_v3(q))
    assert any("CHANGED after v3 freeze" in e for e in proto_mod.verify_manifest_v3(q))


def test_v3_keeps_every_v2_threshold():
    v2 = proto_mod.load_protocol()
    assert v2["criteria"]["T1"]["min_trades"] == 200
    assert v2["criteria"]["T4"]["max_drawdown"] == 0.20
    assert v2["criteria"]["T5"]["min_profit_factor"] == 1.3


def test_holdout_is_not_loaded_by_phase4():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1].joinpath("quantlab", "phase4.py").read_text()
    assert '"holdout"' not in src.replace("holdout untouched", "")


# ---------------------------------------------------------------- report
def _stats(net, dd=0.3):
    return {
        "net_return": net, "max_drawdown": dd, "sharpe": 1.0, "sortino": 1.5, "profit_factor": 1.2,
        "trades": 300, "win_rate": 0.3, "time_in_market": 0.5, "avg_open_positions": 1.5, "days": 1642,
    }  # fmt: skip


def _res():
    crit = [
        {"id": f"T{i}", "criterion": "c", "value": 1.0, "threshold": ">= 1", "passed": i % 2 == 0}
        for i in range(1, 11)
    ]
    return {
        "stats": {"base": _stats(2.0), "stress": _stats(1.0)},
        "annualized_return": {"base": 0.3, "stress": 0.2},
        "gross_exposure": {"avg_gross_exposure": 0.3, "peak_gross_exposure": 0.6},
        "windows": [{"start": "2021-01-01", "end": "2021-07-01", "return": 0.1, "profit": 100.0}],
        "regimes": {"bull": {"trades": 10, "profit_factor": 1.1}},
        "pair_profit_share": {"BTC/USDT": 0.4},
        "monthly": {"2021-01": 0.1, "2021-02": -0.05},
        "criteria": crit,
        "overlay": {"accepted": 5, "denied": {"regime_bear": 3}},
        "halt_events": [],
    }  # fmt: skip


def test_report_renders_all_requested_sections():
    ref = {"stats": {"base": _stats(5.0, 0.7), "stress": _stats(2.0, 0.7)}, "monthly": {"2021-01": 0.2},
           "regimes": {"bull": {"trades": 20, "profit_factor": 1.0}}, "pair_profit_share": {"BTC/USDT": 0.3}}  # fmt: skip
    ablation = {"net_return": 1.0, "max_drawdown": 0.3, "sortino": 1.0, "profit_factor": 1.1, "trades": 200,
                "time_in_market": 0.4, "stress_net_return": 0.5, "halt_events": 0}  # fmt: skip
    out = {
        "protocol_version": 3, "period": {"start": "2021-01-01", "end_exclusive": "2025-07-01"}, "backtests": 14,
        "benchmarks": {"B1": _stats(18.0, 0.9)}, "bench_threshold": {"sortino": 1.8, "max_drawdown": 0.77},
        "bias": {"strategies": {"TrendEmaCrossR1": {"clean": True, "lookahead_evaluated": 6, "lookahead_biased": 0,
                                                   "recursive_checks": 18, "recursive_failed": {}}}},
        "r0": {"strategies": {"TrendEmaCross": ref}},
        "strategies": {"TrendEmaCross": {"R1": _res(), "ablations": {"no_vol_sizing": ablation}}},
    }  # fmt: skip
    md = render(out)
    for needle in ("annualised return", "Sharpe", "profit factor", "time in market", "gross exposure",
                   "stress net return", "monthly returns", "max pair share", "Regimes", "Ablations", "T10",
                   "NOT validation", "no_vol_sizing"):  # fmt: skip
        assert needle in md, needle
