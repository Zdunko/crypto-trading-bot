"""
Hard safety policy for every Freqtrade configuration used by this project.

The policy encodes non-negotiable project rules (see AGENTS.md):

* simulated funds only (``dry_run`` must be true),
* spot trading only (no futures, margin or leverage),
* no unbounded position averaging / martingale,
* no secrets committed to the repository,
* bounded portfolio exposure.

Usage (CLI, exits non-zero on any violation)::

    python -m quantlab.safety quant/configs/base.json [more.json ...]

Multiple files are merged with Freqtrade's own loader, so the check runs on the
exact configuration Freqtrade would see.
"""

from __future__ import annotations

import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from freqtrade.configuration.load_config import load_from_files


# Upper bound for concurrently open trades. Raising it requires an explicit,
# documented decision in PROJECT_STATUS.md.
MAX_OPEN_TRADES_CAP = 10
# Most negative stoploss allowed in configuration (-0.25 == -25 %).
MIN_STOPLOSS = -0.25

# Config keys whose values are credentials. Matched against the key name only.
_SECRET_KEY_RE = re.compile(
    r"(^|_)(key|apikey|secret|password|passphrase|token|uid|privatekey|walletaddress)$",
    re.IGNORECASE,
)
# Keys that look like secrets but are not.
_SECRET_KEY_ALLOWLIST = frozenset({"sort_key", "price_key"})
_WEBHOOK_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True)
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def _walk(node: Any, path: str = ""):
    """Yield (path, key, value) for every key in nested dicts/lists."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield child, str(key), value
            yield from _walk(value, child)
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            yield from _walk(value, f"{path}[{idx}]")


def _check_secrets(config: dict[str, Any]) -> list[Violation]:
    violations = []
    for path, key, value in _walk(config):
        if not isinstance(value, str) or value == "":
            continue
        is_secret_key = key.lower() not in _SECRET_KEY_ALLOWLIST and _SECRET_KEY_RE.search(key)
        is_webhook = "webhook" in path.lower() and _WEBHOOK_URL_RE.match(value)
        if is_secret_key or is_webhook:
            violations.append(
                Violation(path, "credential-like value must be empty; inject via env vars")
            )
    return violations


def check_config(config: dict[str, Any], *, check_secrets: bool = True) -> list[Violation]:
    """
    Return all policy violations for an already-merged Freqtrade config.

    ``check_secrets`` should be False for the environment-variable overlay: runtime secrets
    are allowed to arrive through the environment (never through committed files).
    """
    v: list[Violation] = []

    if config.get("dry_run") is not True:
        v.append(Violation("dry_run", "must be true (simulated funds only)"))

    trading_mode = config.get("trading_mode", "spot")
    if trading_mode != "spot":
        v.append(Violation("trading_mode", f"must be 'spot', got {trading_mode!r}"))

    if config.get("margin_mode"):
        v.append(Violation("margin_mode", "margin is forbidden (spot only)"))

    if config.get("position_adjustment_enable"):
        v.append(
            Violation(
                "position_adjustment_enable",
                "position averaging is disabled until a bounded policy is approved",
            )
        )

    if config.get("force_entry_enable"):
        v.append(Violation("force_entry_enable", "manual force entries are forbidden"))

    max_open_trades = config.get("max_open_trades")
    if (
        not isinstance(max_open_trades, int)
        or isinstance(max_open_trades, bool)
        or not 1 <= max_open_trades <= MAX_OPEN_TRADES_CAP
    ):
        v.append(
            Violation(
                "max_open_trades",
                f"must be an integer in [1, {MAX_OPEN_TRADES_CAP}], got {max_open_trades!r}",
            )
        )

    ratio = config.get("tradable_balance_ratio", 0.99)
    if not isinstance(ratio, (int, float)) or not 0 < ratio <= 0.99:
        v.append(Violation("tradable_balance_ratio", f"must be in (0, 0.99], got {ratio!r}"))

    if "stoploss" in config:
        sl = config["stoploss"]
        if not isinstance(sl, (int, float)) or not MIN_STOPLOSS <= sl < 0:
            v.append(Violation("stoploss", f"must be in [{MIN_STOPLOSS}, 0), got {sl!r}"))

    if check_secrets:
        v.extend(_check_secrets(config))
    return v


def check_files(paths: list[str], *, include_env: bool = True) -> list[Violation]:
    """
    Check the configuration exactly as Freqtrade would resolve it.

    Files are merged with Freqtrade's own loader. With ``include_env`` the ``FREQTRADE__*``
    environment variables are overlaid the same way ``Configuration.load_config`` does, so
    e.g. ``FREQTRADE__DRY_RUN=false`` is caught. Secrets are only checked in the files.
    """
    from freqtrade.configuration.environment_vars import environment_vars_to_dict
    from freqtrade.misc import deep_merge_dicts

    file_config = load_from_files(paths)
    violations = check_config(file_config)
    if include_env:
        effective = deep_merge_dicts(environment_vars_to_dict(), deepcopy(file_config))
        seen = {(x.path, x.message) for x in violations}
        violations.extend(
            x
            for x in check_config(effective, check_secrets=False)
            if (x.path, x.message) not in seen
        )
    return violations


def main(argv: list[str] | None = None) -> int:
    paths = list(sys.argv[1:] if argv is None else argv)
    if not paths:
        print("usage: python -m quantlab.safety CONFIG [CONFIG ...]", file=sys.stderr)
        return 2
    violations = check_files(paths)
    for violation in violations:
        print(f"SAFETY VIOLATION {violation}", file=sys.stderr)
    if violations:
        return 1
    print(f"OK: {', '.join(paths)} pass the safety policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
