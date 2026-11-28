"""
Static safety policy for Freqtrade strategy source files (AST based, nothing is executed).

Rejects, for every class deriving ``IStrategy``:

* ``can_short`` / ``position_adjustment_enable`` set to anything but literal ``False``,
* ``adjust_trade_position`` (position averaging) and ``leverage`` (margin) overrides,
* missing or unbounded ``stoploss`` (must be a literal in [MIN_STOPLOSS, 0));
  only classes in ``BENCHMARK_ALLOWLIST`` may use a wider stop.

And in every file: ``.shift()`` with a negative period, the classic look-ahead.

This is a heuristic guard-rail, not a proof: dynamic tricks (``setattr``, exec) are not
detected. The authoritative bias checks are ``freqtrade lookahead-analysis`` /
``recursive-analysis`` and the causality tests in ``quant/tests``.

Usage: ``python -m quantlab.strategy_policy quant/strategies`` (exit 1 on any violation).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

from quantlab.safety import MIN_STOPLOSS, Violation


# Benchmark-only classes that may use a stoploss wider than MIN_STOPLOSS (still must be < 0).
BENCHMARK_ALLOWLIST = frozenset({"BuyAndHold"})
FORBIDDEN_METHODS = {
    "adjust_trade_position": "position averaging is forbidden",
    "leverage": "leverage is forbidden (spot only)",
}
BENCHMARK_MIN_STOPLOSS = -0.99


def _is_istrategy(base: ast.expr) -> bool:
    return (isinstance(base, ast.Name) and base.id == "IStrategy") or (
        isinstance(base, ast.Attribute) and base.attr == "IStrategy"
    )


def _literal(node: ast.expr) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return _NOT_LITERAL


_NOT_LITERAL = object()


def _class_assignments(cls: ast.ClassDef) -> dict[str, ast.expr]:
    found: dict[str, ast.expr] = {}
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = stmt.value
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.value is not None
        ):
            found[stmt.target.id] = stmt.value
    return found


def _check_class(cls: ast.ClassDef, where: str) -> list[Violation]:
    out: list[Violation] = []
    attrs = _class_assignments(cls)

    for name in ("can_short", "position_adjustment_enable"):
        if name in attrs and _literal(attrs[name]) is not False:
            out.append(Violation(f"{where}:{cls.name}.{name}", "must be literal False"))

    for stmt in cls.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            stmt.name in FORBIDDEN_METHODS
        ):
            out.append(Violation(f"{where}:{cls.name}.{stmt.name}", FORBIDDEN_METHODS[stmt.name]))

    floor = BENCHMARK_MIN_STOPLOSS if cls.name in BENCHMARK_ALLOWLIST else MIN_STOPLOSS
    if "stoploss" not in attrs:
        out.append(Violation(f"{where}:{cls.name}.stoploss", "must be set explicitly"))
    else:
        value = _literal(attrs["stoploss"])
        valid = (
            isinstance(value, (int, float)) and not isinstance(value, bool) and floor <= value < 0
        )
        if not valid:
            out.append(
                Violation(
                    f"{where}:{cls.name}.stoploss",
                    f"must be a literal in [{floor}, 0), got {ast.unparse(attrs['stoploss'])}",
                )
            )
    return out


def _is_negative_number(node: ast.expr) -> bool:
    value = _literal(node)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0


def _check_shifts(tree: ast.AST, where: str) -> list[Violation]:
    out: list[Violation] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "shift"
        ):
            args = list(node.args[:1]) + [k.value for k in node.keywords if k.arg == "periods"]
            if any(_is_negative_number(a) for a in args):
                out.append(
                    Violation(f"{where}:{node.lineno}", "negative shift() reads future candles")
                )
    return out


def check_source(source: str, where: str = "<string>") -> list[Violation]:
    tree = ast.parse(source, filename=where)
    violations = _check_shifts(tree, where)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(_is_istrategy(b) for b in node.bases):
            violations.extend(_check_class(node, where))
    return violations


def check_paths(paths: list[str]) -> list[Violation]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        files.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    violations: list[Violation] = []
    for file in files:
        violations.extend(check_source(file.read_text(), str(file)))
    return violations


def main(argv: list[str] | None = None) -> int:
    paths = list(sys.argv[1:] if argv is None else argv)
    if not paths:
        print("usage: python -m quantlab.strategy_policy PATH [PATH ...]", file=sys.stderr)
        return 2
    violations = check_paths(paths)
    for violation in violations:
        print(f"STRATEGY VIOLATION {violation}", file=sys.stderr)
    if violations:
        return 1
    print(f"OK: {', '.join(paths)} pass the strategy policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
