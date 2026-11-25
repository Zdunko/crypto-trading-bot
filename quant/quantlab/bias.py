"""
Parsing and evaluation of Freqtrade's ``lookahead-analysis`` / ``recursive-analysis`` output.

Fail-closed: anything that cannot be positively read as "clean" counts as NOT clean.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path


CLEAN_LOOKAHEAD_INDICATORS = "No lookahead bias on indicators found."


def parse_recursive(text: str) -> dict:
    """
    Return ``{"own_column": "<header>", "variance": {indicator: float | None | nan}}`` where the
    values come from the strategy's own startup column ("... (from strategy)"). ``None`` means
    Freqtrade printed ``-`` (no variance). Variance is a fraction (0.001 == 0.1 %).
    """
    lines = text.splitlines()
    out: dict = {
        "own_column": None,
        "variance": {},
        "indicator_lookahead_clean": CLEAN_LOOKAHEAD_INDICATORS in text,
        "table_found": False,
    }
    header_idx = next((i for i, ln in enumerate(lines) if "Indicators" in ln and "┃" in ln), None)
    if header_idx is None:
        return out
    headers = [h.strip() for h in lines[header_idx].strip().strip("┃").split("┃")]
    own = next((i for i, h in enumerate(headers) if "(from strategy)" in h), None)
    if own is None:
        return out
    out["own_column"], out["table_found"] = headers[own], True
    for ln in lines[header_idx + 1 :]:
        if ln.lstrip().startswith("└"):
            break
        if not ln.lstrip().startswith("│"):
            continue
        cells = [c.strip() for c in ln.strip().strip("│").split("│")]
        if len(cells) <= own:
            continue
        raw = cells[own]
        if raw == "-":
            value: float | None = None
        else:
            m = re.fullmatch(r"(-?\d+(?:\.\d+)?)%|nan%", raw)
            value = float("nan") if m is None or raw == "nan%" else float(m.group(1)) / 100.0
        out["variance"][cells[0]] = value
    return out


def recursive_ok(parsed: dict, tolerance: float) -> tuple[bool, float]:
    """Clean iff indicator lookahead is confirmed clean and every variance <= tolerance."""
    values = [v for v in parsed["variance"].values() if v is not None]
    if any(math.isnan(v) for v in values):
        return False, float("nan")
    worst = max((abs(v) for v in values), default=0.0)
    return bool(parsed["indicator_lookahead_clean"]) and worst <= tolerance, worst


def parse_lookahead_csv(path: Path) -> dict[str, dict]:
    """``{strategy: {"has_bias": bool, "signals": int, ...}}`` from Freqtrade's export."""
    if not path.exists():
        return {}
    rows = {}
    with path.open() as fh:
        for r in csv.DictReader(fh):
            rows[r["strategy"]] = {
                "has_bias": r["has_bias"].strip().lower() == "true",
                "signals": int(float(r.get("total_signals", 0) or 0)),
                "biased_entry": int(float(r.get("biased_entry_signals", 0) or 0)),
                "biased_exit": int(float(r.get("biased_exit_signals", 0) or 0)),
                "biased_indicators": r.get("biased_indicators", "") or "",
            }
    return rows


def summarize_bias(
    strategies: list[str],
    lookahead: dict[str, dict[str, dict]],
    recursive: dict[str, dict[str, tuple[bool, float]]],
    min_periods: int,
) -> dict:
    """
    ``lookahead[period][strategy]`` from :func:`parse_lookahead_csv` (missing = not evaluated),
    ``recursive[strategy]["period|pair"] = (ok, worst_variance)``.
    """
    out: dict = {"strategies": {}, "min_evaluated_periods": min_periods}
    for s in strategies:
        evaluated = biased = 0
        per_period = {}
        for period, rows in lookahead.items():
            row = rows.get(s)
            if row is None:
                per_period[period] = "not_evaluated"
            elif row["has_bias"]:
                per_period[period], biased = "BIAS", biased + 1
            else:
                per_period[period], evaluated = "clean", evaluated + 1
        rec = recursive.get(s, {})
        rec_bad = {k: v for k, v in rec.items() if not v[0]}
        out["strategies"][s] = {
            "lookahead": per_period,
            "lookahead_evaluated": evaluated,
            "lookahead_biased": biased,
            "recursive_checks": len(rec),
            "recursive_failed": {k: v[1] for k, v in rec_bad.items()},
            "recursive_worst_variance": max((v[1] for v in rec.values()), default=float("nan")),
            "clean": biased == 0 and evaluated >= min_periods and bool(rec) and not rec_bad,
        }
    return out
