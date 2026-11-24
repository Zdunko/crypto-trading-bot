"""Tests for the hard safety policy and the committed project configs."""

import json
from pathlib import Path

import pytest

from quantlab.safety import MAX_OPEN_TRADES_CAP, check_config, check_files, main


CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"
ALL_CONFIGS = sorted(CONFIG_DIR.glob("*.json"))


def _valid() -> dict:
    return {
        "dry_run": True,
        "trading_mode": "spot",
        "max_open_trades": 3,
        "tradable_balance_ratio": 0.99,
        "exchange": {"name": "binance", "key": "", "secret": ""},
        "telegram": {"enabled": False, "token": "", "chat_id": ""},
    }


def _paths(config: dict) -> set[str]:
    return {v.path for v in check_config(config)}


def test_valid_config_has_no_violations():
    assert check_config(_valid()) == []


@pytest.mark.parametrize("value", [False, None, "true", 1])
def test_dry_run_must_be_literal_true(value):
    cfg = _valid()
    cfg["dry_run"] = value
    assert "dry_run" in _paths(cfg)


def test_missing_dry_run_is_violation():
    cfg = _valid()
    del cfg["dry_run"]
    assert "dry_run" in _paths(cfg)


@pytest.mark.parametrize("mode", ["futures", "margin"])
def test_non_spot_trading_mode_rejected(mode):
    cfg = _valid()
    cfg["trading_mode"] = mode
    assert "trading_mode" in _paths(cfg)


def test_margin_mode_rejected():
    cfg = _valid()
    cfg["margin_mode"] = "isolated"
    assert "margin_mode" in _paths(cfg)


@pytest.mark.parametrize("key", ["position_adjustment_enable", "force_entry_enable"])
def test_forbidden_features(key):
    cfg = _valid()
    cfg[key] = True
    assert key in _paths(cfg)


@pytest.mark.parametrize("value", [-1, 0, MAX_OPEN_TRADES_CAP + 1, 2.5, True, None])
def test_max_open_trades_bounds(value):
    cfg = _valid()
    cfg["max_open_trades"] = value
    assert "max_open_trades" in _paths(cfg)


@pytest.mark.parametrize("value", [0, 1.0, -0.1])
def test_tradable_balance_ratio_bounds(value):
    cfg = _valid()
    cfg["tradable_balance_ratio"] = value
    assert "tradable_balance_ratio" in _paths(cfg)


@pytest.mark.parametrize("value", [-0.5, 0, 0.1])
def test_stoploss_bounds(value):
    cfg = _valid()
    cfg["stoploss"] = value
    assert "stoploss" in _paths(cfg)


def test_reasonable_stoploss_accepted():
    cfg = _valid()
    cfg["stoploss"] = -0.08
    assert check_config(cfg) == []


@pytest.mark.parametrize(
    "path,patch",
    [
        ("exchange.key", {"exchange": {"key": "abc123"}}),
        ("exchange.secret", {"exchange": {"secret": "s3cr3t"}}),
        ("exchange.password", {"exchange": {"password": "pw"}}),
        ("telegram.token", {"telegram": {"token": "123:ABC"}}),
        ("api_server.jwt_secret_key", {"api_server": {"jwt_secret_key": "x"}}),
        ("api_server.ws_token", {"api_server": {"ws_token": "x"}}),
        ("api_server.password", {"api_server": {"password": "x"}}),
        ("discord.webhook_url", {"discord": {"webhook_url": "https://discord.com/api/x"}}),
    ],
)
def test_secrets_rejected(path, patch):
    cfg = _valid()
    for section, values in patch.items():
        cfg.setdefault(section, {}).update(values)
    assert path in _paths(cfg)


def test_non_secret_keys_not_flagged():
    cfg = _valid()
    cfg["telegram"]["chat_id"] = "12345"
    cfg["pairlists"] = [{"method": "VolumePairList", "sort_key": "quoteVolume"}]
    assert check_config(cfg) == []


@pytest.mark.parametrize("path", ALL_CONFIGS, ids=lambda p: p.name)
def test_committed_configs_are_valid_json(path):
    json.loads(path.read_text())


def test_committed_config_stack_passes_policy():
    assert ALL_CONFIGS, "no configs found"
    assert check_files([str(p) for p in ALL_CONFIGS]) == []


def test_committed_config_stack_passes_freqtrade_schema():
    from freqtrade.configuration.config_validation import validate_config_schema
    from freqtrade.configuration.load_config import load_from_files
    from freqtrade.enums import RunMode

    config = load_from_files([str(p) for p in ALL_CONFIGS])
    config["runmode"] = RunMode.BACKTEST
    validate_config_schema(config, preliminary=True)


def test_cli_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_valid()))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**_valid(), "dry_run": False}))

    assert main([str(good)]) == 0
    assert main([str(bad)]) == 1
    assert "dry_run" in capsys.readouterr().err
    assert main([]) == 2
