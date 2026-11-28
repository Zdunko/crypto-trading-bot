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


def _write(tmp_path, config: dict):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(config))
    return str(path)


@pytest.mark.parametrize(
    "env,path",
    [
        ("FREQTRADE__DRY_RUN", "dry_run"),
        ("FREQTRADE__TRADING_MODE", "trading_mode"),
        ("FREQTRADE__MARGIN_MODE", "margin_mode"),
        ("FREQTRADE__POSITION_ADJUSTMENT_ENABLE", "position_adjustment_enable"),
        ("FREQTRADE__FORCE_ENTRY_ENABLE", "force_entry_enable"),
        ("FREQTRADE__MAX_OPEN_TRADES", "max_open_trades"),
    ],
)
def test_env_overrides_cannot_bypass_policy(tmp_path, monkeypatch, env, path):
    values = {
        "FREQTRADE__DRY_RUN": "false",
        "FREQTRADE__TRADING_MODE": "futures",
        "FREQTRADE__MARGIN_MODE": "isolated",
        "FREQTRADE__POSITION_ADJUSTMENT_ENABLE": "true",
        "FREQTRADE__FORCE_ENTRY_ENABLE": "true",
        "FREQTRADE__MAX_OPEN_TRADES": "500",
    }
    cfg = _write(tmp_path, _valid())
    assert check_files([cfg]) == []
    monkeypatch.setenv(env, values[env])
    assert path in {v.path for v in check_files([cfg])}
    # Opting out of the overlay only inspects the files themselves.
    assert check_files([cfg], include_env=False) == []


def test_runtime_secrets_from_environment_are_allowed(tmp_path, monkeypatch):
    cfg = _write(tmp_path, _valid())
    monkeypatch.setenv("FREQTRADE__TELEGRAM__TOKEN", "123:ABC")
    assert check_files([cfg]) == []


def test_env_overlay_matches_freqtrade_resolution(tmp_path, monkeypatch):
    """Guard against drift: our overlay must resolve the way Freqtrade's loader does."""
    from freqtrade.configuration.environment_vars import environment_vars_to_dict
    from freqtrade.misc import deep_merge_dicts

    monkeypatch.setenv("FREQTRADE__DRY_RUN", "false")
    file_cfg = _valid()
    effective = deep_merge_dicts(environment_vars_to_dict(), dict(file_cfg))
    assert effective["dry_run"] is False
