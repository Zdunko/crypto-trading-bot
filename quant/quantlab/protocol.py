"""
Frozen validation protocol: loading, consistency checks and the integrity manifest.

``protocol/protocol.json`` states WHAT is tested and WHEN a strategy passes. The manifest pins
the sha256 of that file, of every strategy, of ``quant_common.py`` and of every config. Any change
to them after the freeze makes :func:`verify_manifest` (and therefore the CI test and the
research runner) fail until a new manifest is committed - a visible, reviewable act.

    python -m quantlab.protocol freeze   # write protocol/frozen_manifest.json
    python -m quantlab.protocol verify   # exit 1 on any mismatch or inconsistency
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


QUANT_DIR = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = QUANT_DIR / "protocol" / "protocol.json"
MANIFEST_PATH = QUANT_DIR / "protocol" / "frozen_manifest.json"

# The three thresholds the owner changed on 2026-11-25; asserted independently of protocol.json.
OWNER_REQUIRED = {"T1.min_trades": 200, "T4.max_drawdown": 0.20, "T5.min_profit_factor": 1.3}


def load_protocol(path: Path = PROTOCOL_PATH) -> dict:
    return json.loads(path.read_text())


def _norm_hash(path: Path) -> str:
    """sha256 of the file with CRLF normalised, so Windows checkouts hash identically."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def frozen_files(quant_dir: Path = QUANT_DIR) -> list[Path]:
    files = sorted((quant_dir / "strategies").glob("*.py"))
    files += sorted((quant_dir / "configs").glob("*.json"))
    files.append(quant_dir / "protocol" / "protocol.json")
    return files


def build_manifest(quant_dir: Path = QUANT_DIR) -> dict:
    return {
        "note": "Regenerate only through a reviewed commit; see quantlab/protocol.py",
        "files": {str(p.relative_to(quant_dir)): _norm_hash(p) for p in frozen_files(quant_dir)},
    }


def verify_manifest(quant_dir: Path = QUANT_DIR) -> list[str]:
    manifest_path = quant_dir / "protocol" / "frozen_manifest.json"
    if not manifest_path.exists():
        return ["frozen_manifest.json is missing"]
    frozen = json.loads(manifest_path.read_text())["files"]
    current = build_manifest(quant_dir)["files"]
    errors = [
        f"CHANGED after freeze: {k}" for k in frozen if k in current and frozen[k] != current[k]
    ]
    errors += [f"MISSING since freeze: {k}" for k in frozen if k not in current]
    errors += [f"NEW file not in freeze: {k}" for k in current if k not in frozen]
    return errors


def _config_errors(p: dict, quant_dir: Path) -> list[str]:
    from freqtrade.configuration.load_config import load_from_files

    errs: list[str] = []
    cfg = load_from_files(
        [str(quant_dir / "configs" / "base.json"), str(quant_dir / "configs" / "backtest.json")]
    )
    if list(cfg["exchange"]["pair_whitelist"]) != p["pairs"]:
        errs.append("protocol pairs differ from configs/base.json whitelist")
    if cfg.get("fee") != p["costs"]["base"]["fee"]:
        errs.append(
            f"configs fee {cfg.get('fee')} != protocol base fee {p['costs']['base']['fee']}: "
            "a lumped fee would double-count slippage"
        )
    if cfg["max_open_trades"] != p["max_open_trades"]:
        errs.append("max_open_trades differs between protocol and config")
    if cfg["dry_run_wallet"] != p["initial_wallet"]:
        errs.append("dry_run_wallet differs between protocol and config")
    if cfg["timeframe"] != p["timeframe"] or cfg["exchange"]["name"] != "binance":
        errs.append("unexpected timeframe/exchange in base config (exchange is overridden by env)")
    return errs


def _threshold_errors(c: dict) -> list[str]:
    errs = []
    for key, expected in OWNER_REQUIRED.items():
        t, field = key.split(".")
        if c[t][field] != expected:
            errs.append(f"{key} = {c[t][field]} but the owner requires {expected}")
    unchanged = {
        "T2": {"min_net_return_exclusive": 0.0},
        "T6": {"min_profit_factor": 1.0, "requires_positive_net_return": True},
        "T7": {"min_positive_window_share": 0.6, "max_window_profit_share": 0.5},
        "T8": {"min_regime_trades": 30, "min_profit_factor": 0.8},
        "T9": {"min_positive_variant_share": 0.75},
    }
    errs += [
        f"{t} changed from v1 although the owner said to keep it: {c[t]}"
        for t, vals in unchanged.items()
        if c[t] != vals
    ]
    return errs


def _period_errors(p: dict) -> list[str]:
    errs = []
    ev, ho = p["periods"]["evaluation"], p["periods"]["holdout"]
    if ev["end_exclusive"] != ho["start"]:
        errs.append("holdout must start exactly where the evaluation period ends")
    if ho["end_exclusive"] != p["data"]["end_exclusive"]:
        errs.append("holdout must end at the end of the frozen dataset")
    for start, end in p["bias_periods"]:
        if not (ev["start"] <= start < end <= ev["end_exclusive"]):
            errs.append(f"bias period {start}..{end} leaves the evaluation period")
    if set(p["robustness"]) - {"method"} != set(p["strategies"]):
        errs.append("robustness ranges must exist for exactly the strategies under test")
    return errs


def consistency_errors(proto: dict | None = None, quant_dir: Path = QUANT_DIR) -> list[str]:
    """Cross-checks between protocol.json, the configs and the owner's required thresholds."""
    p = proto or load_protocol(quant_dir / "protocol" / "protocol.json")
    return _config_errors(p, quant_dir) + _threshold_errors(p["criteria"]) + _period_errors(p)


def main(argv: list[str] | None = None) -> int:
    cmd = (argv or sys.argv[1:] or [""])[0]
    if cmd == "freeze":
        errs = consistency_errors()
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 1
        MANIFEST_PATH.write_text(json.dumps(build_manifest(), indent=1, sort_keys=True) + "\n")
        print(f"wrote {MANIFEST_PATH}")
        return 0
    if cmd == "verify":
        errs = consistency_errors() + verify_manifest()
        print("\n".join(errs) if errs else "protocol frozen and consistent")
        return 1 if errs else 0
    print("usage: python -m quantlab.protocol freeze|verify", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
