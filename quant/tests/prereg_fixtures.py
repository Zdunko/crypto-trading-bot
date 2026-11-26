"""Pre-registration fixtures: a synthetic example that must pass the gate and Family A as recorded."""

from __future__ import annotations

import copy

from quantlab import feasibility as f


TH = f.thresholds()
LONG = "A substantive statement of more than forty characters about the economic mechanism."


def p(name, value, kind="convention", source="documented convention, fixed before any result"):
    return {"name": name, "value": value, "kind": kind, "source": source}


def base() -> dict:
    return {
        "schema": "prereg-v1",
        "family": {
            "id": "SYN-1",
            "family_key": "synthetic_example",
            "title": "Synthetic example family",
            "version": 1,
        },
        "economic": {
            "hypothesis": LONG,
            "rationale": LONG + " Rationale.",
            "counterparty": LONG + " Counterparty.",
            "expected_failure_modes": [
                "Crowding erodes the effect in liquid assets.",
                "Regime change removes the premium.",
            ],
            "falsifiable_prediction": LONG + " Prediction.",
        },
        "strategy": {
            "configurations": [
                {
                    "id": "S1",
                    "role": "primary",
                    "description": "primary",
                    "parameters": [p("lookback_days", 90, "free", "")],
                },
                {
                    "id": "S0",
                    "role": "descriptive",
                    "description": "component",
                    "parameters": [p("lookback_days", 90, "free", "")],
                },
            ],
            "indicators": [
                {"name": "momentum", "window": 90, "input": "completed_candles", "interval": "1d"}
            ],
            "decision_time": "daily_close_completed",
            "signal_inputs": ["close"],
        },
        "data": {
            "dataset_hash": TH["dataset_hash"],
            "interval": "1d",
            "universe": {"threshold": "1M", "max_stale_days": 3},
            "warmup_days": 91,
            "evaluation": {"start": "2021-01-01", "end_exclusive": "2025-07-01"},
        },
        "execution": {
            "engine": "quantlab.execution",
            "fill": "next_candle_open",
            "costs": {"fee": 0.001, "slippage": 0.0005, "stress_multiple": 2.0},
            "max_participation": 0.1,
            "min_notional": 5.0,
        },
        "risk": {
            "layer": "risk_v2",
            "config_sha256": TH["risk_config_sha256"],
            "universe_guard": True,
            "spot_only": True,
            "leverage": False,
            "shorting": False,
            "averaging": False,
            "position_adjustment": False,
        },
        "expected": {
            "assets": {"lo": 60, "hi": 120},
            "entries_per_asset_year": {"lo": 3.0, "hi": 6.0},
            "active_day_share": {"lo": 0.85, "hi": 0.95},
            "cluster_size": {"lo": 2, "hi": 6},
            "rho": {"lo": 0.3, "hi": 0.6},
            "serial_rho": {"lo": 0.0, "hi": 0.05},
        },
        "hypotheses": [
            {
                "id": "H1",
                "statement": "net annualised Sharpe of the primary configuration is above zero",
            }
        ],
        "benchmarks": list(TH["required_benchmarks"]),
        "budget": {"new_configurations": 2},
        "declarations": {
            "results_seen": False,
            "prior_looks": 0,
            "holdout_access": False,
            "holdout_metadata_acknowledged": list(f.HOLDOUT_ACK),
        },
    }


def synthetic_example() -> dict:
    return copy.deepcopy(base())


def family_a_as_specified() -> dict:
    """Family A with the numbers recorded in its evaluation: 8 pairs, 14 closed episodes in 4.5 years, 15.6 %
    of days invested (257 of 1 642). Everything else follows its protocol v5 (rejected family key)."""
    d = base()
    d["family"] = {
        "id": "A",
        "family_key": "trend_vol_scaled_basket",
        "title": "Trend-filtered volatility-scaled basket",
        "version": 5,
    }
    conv = [
        p("trend_window_fast", 50),
        p("trend_window_mid", 100),
        p("trend_window_slow", 200),
        p("vol_window", 30),
        p("sigma_target", 0.4),
        p("band", 0.05),
    ]
    d["strategy"]["configurations"] = [
        {
            "id": "A1",
            "role": "primary",
            "description": "trend + volatility scaling",
            "parameters": conv,
        },
        {"id": "A0", "role": "descriptive", "description": "trend only", "parameters": conv[:3]},
        {
            "id": "V0",
            "role": "descriptive",
            "description": "volatility scaling only",
            "parameters": conv[3:],
        },
    ]
    d["strategy"]["indicators"] = [
        {"name": "sma", "window": 200, "input": "completed_candles", "interval": "1d"}
    ]
    d["data"]["warmup_days"] = 201
    d["expected"] = {
        "assets": {"lo": 8, "hi": 8},
        "entries_per_asset_year": {"lo": 0.3, "hi": 0.5},
        "active_day_share": {"lo": 0.10, "hi": 0.20},
        "cluster_size": {"lo": 1.5, "hi": 2.5},
        "rho": {"lo": 0.5, "hi": 0.8},
        "serial_rho": {"lo": 0.0, "hi": 0.2},
    }
    d["budget"]["new_configurations"] = 3
    d["hypotheses"] = [
        {"id": "H1", "statement": "A1 net Sharpe > 0"},
        {"id": "H2", "statement": "A1 beats unscaled B1"},
    ]
    return d
