"""The frozen protocol: owner-mandated thresholds, internal consistency and tamper detection."""

import json
import shutil
from pathlib import Path

import pytest

from quantlab import protocol as P


QUANT = Path(__file__).resolve().parents[1]


@pytest.fixture
def copy(tmp_path):
    dst = tmp_path / "quant"
    for sub in ("strategies", "configs", "protocol"):
        shutil.copytree(QUANT / sub, dst / sub)
    return dst


def test_committed_protocol_is_consistent_and_frozen():
    assert P.consistency_errors() == []
    assert P.verify_manifest() == [], "a frozen file changed: re-freeze only via a reviewed commit"


def test_owner_thresholds_are_in_force():
    c = P.load_protocol()["criteria"]
    assert c["T1"]["min_trades"] == 200
    assert c["T4"]["max_drawdown"] == 0.20 and c["T4"]["also_not_above_benchmark"] is True
    assert c["T5"]["min_profit_factor"] == 1.3


def test_holdout_is_disjoint_from_evaluation_and_bias_periods():
    p = P.load_protocol()
    ev, ho = p["periods"]["evaluation"], p["periods"]["holdout"]
    assert ev["end_exclusive"] == ho["start"]
    assert all(end <= ho["start"] for _, end in p["bias_periods"])
    assert len(p["bias_periods"]) >= 5


@pytest.mark.parametrize(
    "rel",
    [
        "strategies/trend_ema_cross.py",
        "strategies/quant_common.py",
        "configs/backtest.json",
        "protocol/protocol.json",
    ],
)
def test_any_change_to_a_frozen_file_is_detected(copy, rel):
    assert P.verify_manifest(copy) == []
    (copy / rel).write_text((copy / rel).read_text() + "\n# tweak\n")
    assert any(rel in e for e in P.verify_manifest(copy))


def test_new_strategy_after_freeze_is_detected(copy):
    (copy / "strategies" / "extra.py").write_text("x = 1\n")
    assert any("NEW file" in e for e in P.verify_manifest(copy))


def test_crlf_checkout_hashes_identically(copy):
    f = copy / "strategies" / "buy_and_hold.py"
    f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
    assert P.verify_manifest(copy) == []


@pytest.mark.parametrize(
    "mutate,fragment",
    [
        (lambda p: p["criteria"]["T1"].update(min_trades=100), "T1.min_trades"),
        (lambda p: p["criteria"]["T4"].update(max_drawdown=0.30), "T4.max_drawdown"),
        (lambda p: p["criteria"]["T5"].update(min_profit_factor=1.2), "T5.min_profit_factor"),
        (lambda p: p["criteria"]["T7"].update(min_positive_window_share=0.5), "T7 changed"),
        (lambda p: p["costs"]["base"].update(fee=0.0015), "double-count"),
        (lambda p: p["periods"]["holdout"].update(start="2025-01-01"), "holdout must start"),
        (lambda p: p["bias_periods"].append(["2025-06-01", "2025-09-01"]), "leaves the evaluation"),
        (lambda p: p["robustness"].pop("MomentumRoc"), "robustness ranges"),
    ],
)
def test_inconsistent_protocol_is_rejected(mutate, fragment):
    p = json.loads((QUANT / "protocol" / "protocol.json").read_text())
    mutate(p)
    assert any(fragment in e for e in P.consistency_errors(p))


def test_freeze_cli_roundtrip(copy, monkeypatch):
    monkeypatch.setattr(P, "QUANT_DIR", copy)
    monkeypatch.setattr(P, "MANIFEST_PATH", copy / "protocol" / "frozen_manifest.json")
    monkeypatch.setattr(P, "PROTOCOL_PATH", copy / "protocol" / "protocol.json")
    (copy / "protocol" / "frozen_manifest.json").unlink(missing_ok=True)
    assert P.verify_manifest(copy) == ["frozen_manifest.json is missing"]
    manifest = P.build_manifest(copy)
    (copy / "protocol" / "frozen_manifest.json").write_text(json.dumps(manifest))
    assert P.verify_manifest(copy) == []


def test_manifest_keys_are_posix_paths_on_every_platform():
    """Windows CI failed once because keys were built with backslashes."""
    assert all("\\" not in k for k in P.build_manifest()["files"])
    assert all("\\" not in k for k in json.loads(P.MANIFEST_PATH.read_text())["files"])
