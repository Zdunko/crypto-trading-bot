"""Bias parsers are tested on tables copied verbatim from the real GitHub Actions log (run 45553021957)."""

import math

import pytest

from quantlab.bias import (
    parse_lookahead_csv,
    parse_recursive,
    recursive_ok,
    summarize_bias,
)


TREND = """
2026-11-25 05:23:16,467 - freqtrade.optimize.analysis.recursive - INFO - No lookahead bias on indicators found.
                              Recursive Analysis
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ Indicators ┃    199 ┃     399 ┃ 400 (from strategy) ┃    599 ┃     999 ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│   ema_fast │ 0.000% │       - │                   - │      - │       - │
│   ema_slow │ 0.054% │ -0.002% │             -0.002% │ 0.000% │ -0.000% │
└────────────┴────────┴─────────┴─────────────────────┴────────┴─────────┘
"""
MOMENTUM = """
2026-11-25 05:23:27,124 - freqtrade.optimize.analysis.recursive - INFO - No lookahead bias on indicators found.
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Indicators ┃    199 ┃     399 ┃    599 ┃ 600 (from strategy) ┃    999 ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│        roc │   nan% │       - │      - │                   - │      - │
│  ema_trend │ 0.392% │ -0.085% │ 0.024% │              0.024% │ 0.000% │
└────────────┴────────┴─────────┴────────┴─────────────────────┴────────┘
"""


def test_parse_real_table_reads_only_the_strategys_own_column():
    p = parse_recursive(TREND)
    assert p["own_column"] == "400 (from strategy)"
    assert p["variance"] == {"ema_fast": None, "ema_slow": pytest.approx(-0.00002)}
    ok, worst = recursive_ok(p, 0.001)
    assert ok and worst == pytest.approx(0.00002)


def test_nan_in_other_columns_is_ignored_but_variance_above_tolerance_fails():
    p = parse_recursive(MOMENTUM)  # roc is nan% only at startup 199, not at its own column
    assert p["variance"]["roc"] is None
    assert recursive_ok(p, 0.001)[0] is True
    assert recursive_ok(p, 0.0001)[0] is False  # 0.024 % > 0.01 %


def test_nan_in_own_column_and_missing_confirmation_fail_closed():
    bad = MOMENTUM.replace("│                   - │", "│               nan% │")
    assert recursive_ok(parse_recursive(bad), 0.001)[0] is False
    unconfirmed = TREND.replace("No lookahead bias on indicators found.", "")
    assert recursive_ok(parse_recursive(unconfirmed), 0.001)[0] is False
    nothing = parse_recursive("no table here")
    assert nothing["table_found"] is False and nothing["variance"] == {}


def test_csv_parsing(tmp_path):
    f = tmp_path / "l.csv"
    f.write_text(
        "filename,strategy,has_bias,total_signals,biased_entry_signals,biased_exit_signals,biased_indicators\n"
        "a.py,A,False,20,0,0,\nb.py,B,True,20,3,0,rsi\n"
    )
    r = parse_lookahead_csv(f)
    assert r["A"]["has_bias"] is False and r["A"]["signals"] == 20
    assert r["B"]["has_bias"] is True and r["B"]["biased_indicators"] == "rsi"
    assert parse_lookahead_csv(tmp_path / "missing.csv") == {}


def _la(biased=False):
    return {
        "has_bias": biased,
        "signals": 20,
        "biased_entry": 0,
        "biased_exit": 0,
        "biased_indicators": "",
    }


def test_summary_requires_enough_evaluated_periods_no_bias_and_clean_recursion():
    la = {f"p{i}": {"A": _la()} for i in range(3)}
    rec = {"A": {"p0|BTC": (True, 0.0), "p1|BTC": (True, 0.0002)}}
    assert summarize_bias(["A"], la, rec, 3)["strategies"]["A"]["clean"] is True
    # too few evaluated periods
    assert summarize_bias(["A"], {**la, "p2": {}}, rec, 3)["strategies"]["A"]["clean"] is False
    # any bias at all
    assert (
        summarize_bias(["A"], {**la, "p2": {"A": _la(True)}}, rec, 3)["strategies"]["A"]["clean"]
        is False
    )
    # recursive failure
    bad = {"A": {"p0|BTC": (False, 0.01)}}
    s = summarize_bias(["A"], la, bad, 3)["strategies"]["A"]
    assert s["clean"] is False and s["recursive_failed"] == {"p0|BTC": 0.01}
    # no recursive evidence at all is not clean
    assert summarize_bias(["A"], la, {}, 3)["strategies"]["A"]["clean"] is False
    assert math.isnan(
        summarize_bias(["A"], la, {}, 3)["strategies"]["A"]["recursive_worst_variance"]
    )
