"""Tests for the static strategy policy and for the committed strategies."""

from pathlib import Path

import pytest

from quantlab.strategy_policy import check_paths, check_source, main


STRATEGY_DIR = Path(__file__).resolve().parents[1] / "strategies"


def _strategy(body: str, name: str = "S") -> str:
    return f"from freqtrade.strategy import IStrategy\n\nclass {name}(IStrategy):\n{body}"


def _paths(source: str) -> set[str]:
    return {v.path.split(":", 1)[1] for v in check_source(source)}


def test_clean_strategy_passes():
    assert check_source(_strategy("    stoploss = -0.1\n")) == []


@pytest.mark.parametrize("attr", ["can_short", "position_adjustment_enable"])
@pytest.mark.parametrize("value", ["True", "1", "some_flag"])
def test_forbidden_flags(attr, value):
    src = _strategy(f"    stoploss = -0.1\n    {attr} = {value}\n")
    assert f"S.{attr}" in _paths(src)


@pytest.mark.parametrize("method", ["adjust_trade_position", "leverage"])
def test_forbidden_methods(method):
    src = _strategy(f"    stoploss = -0.1\n    def {method}(self, *a, **k):\n        return 1\n")
    assert f"S.{method}" in _paths(src)


@pytest.mark.parametrize("value", ["-0.5", "0", "0.1", "-0.99", "some_var", "True"])
def test_stoploss_bounds(value):
    assert "S.stoploss" in _paths(_strategy(f"    stoploss = {value}\n"))


def test_missing_stoploss():
    assert "S.stoploss" in _paths(_strategy("    timeframe = '1h'\n"))


def test_benchmark_allowlist_may_use_wide_stop_but_not_zero():
    assert check_source(_strategy("    stoploss = -0.99\n", name="BuyAndHold")) == []
    assert "BuyAndHold.stoploss" in _paths(_strategy("    stoploss = 0\n", name="BuyAndHold"))
    # The exemption is by name only: an arbitrary class does not get it.
    assert "Other.stoploss" in _paths(_strategy("    stoploss = -0.99\n", name="Other"))


@pytest.mark.parametrize(
    "expr", ["df['c'].shift(-1)", "df['c'].shift(periods=-3)", "df.close.shift(-n_const)"]
)
def test_negative_shift_flagged(expr):
    src = _strategy(f"    stoploss = -0.1\n    def f(self, df):\n        return {expr}\n")
    violations = check_source(src.replace("n_const", "5"))
    assert any("negative shift" in v.message for v in violations)


@pytest.mark.parametrize("expr", ["df['c'].shift(1)", "df['c'].shift(periods=24)", "df.c.shift()"])
def test_positive_shift_ok(expr):
    src = _strategy(f"    stoploss = -0.1\n    def f(self, df):\n        return {expr}\n")
    assert check_source(src) == []


def test_non_strategy_classes_are_ignored():
    assert check_source("class Helper:\n    can_short = True\n") == []


def test_committed_strategies_pass_policy():
    assert list(STRATEGY_DIR.glob("*.py")), "no strategies found"
    assert check_paths([str(STRATEGY_DIR)]) == []


def test_cli_exit_codes(tmp_path, capsys):
    good, bad = tmp_path / "good.py", tmp_path / "bad.py"
    good.write_text(_strategy("    stoploss = -0.1\n"))
    bad.write_text(_strategy("    stoploss = -0.1\n    can_short = True\n"))
    assert main([str(good)]) == 0
    assert main([str(bad)]) == 1
    assert "can_short" in capsys.readouterr().err
    assert main([]) == 2
