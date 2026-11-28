"""Research-budget enforcement (protocol V2 acceptance criterion 4): a run cannot start if the budget is
exhausted. Pure functions over ``protocol/research_budget.json``; ``python -m quantlab.budget check``
runs in ``check.sh`` and cross-checks N against the experiment ledger."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


QUANT = Path(__file__).resolve().parents[1]
BUDGET = QUANT / "protocol/research_budget.json"
LEDGER = QUANT / "protocol/experiment_ledger.json"
STATUSES = {"preregistered", "evaluated_accepted", "evaluated_rejected"}


def violations(b: dict) -> list[str]:
    caps, st = b["caps"], b["state"]
    out: list[str] = []
    fams = st["further_families"]
    if len(fams) > caps["max_further_families"]:
        out.append(f"{len(fams)} further families exceed the cap {caps['max_further_families']}")
    if len({f["id"] for f in fams}) != len(fams):
        out.append("duplicate family id")
    for f in fams:
        if f["status"] not in STATUSES:
            out.append(f"family {f['id']}: unknown status {f['status']}")
        if f["configurations"] > caps["max_configurations_per_family"]:
            out.append(f"family {f['id']}: {f['configurations']} configurations exceed the cap")
        if f["market_runs"] > caps["max_market_runs_per_family"]:
            out.append(f"family {f['id']}: {f['market_runs']} market runs exceed the cap")
    expected_n = 43 + sum(f["configurations"] for f in fams)
    if st["total_n"] > caps["max_total_n"]:
        out.append(f"N={st['total_n']} exceeds the cap {caps['max_total_n']}")
    if st["total_n"] != expected_n:
        out.append(
            f"N={st['total_n']} is inconsistent with the registered families (expected {expected_n})"
        )
    if st["consecutive_rejected_under_v2"] >= caps["stop_after_consecutive_rejected_under_v2"]:
        out.append("stop rule reached: strategy search must stop (owner decides)")
    return out


def can_start_run(b: dict, family_id: str, new_configurations: int = 0) -> tuple[bool, str]:
    """May a market run of ``family_id`` start? New families must fit the caps before they are run."""
    v = violations(b)
    if v:
        return False, "; ".join(v)
    caps, st = b["caps"], b["state"]
    fam = next((f for f in st["further_families"] if f["id"] == family_id), None)
    if fam is None:
        if len(st["further_families"]) + 1 > caps["max_further_families"]:
            return False, "family cap exhausted"
        if new_configurations > caps["max_configurations_per_family"]:
            return False, "configuration cap exceeded"
        if st["total_n"] + new_configurations > caps["max_total_n"]:
            return False, "N cap exceeded"
        return (
            False,
            "family is not registered with a pre-registration (register it before the run)",
        )
    if fam["status"] != "preregistered":
        return False, f"family status is {fam['status']}, not preregistered"
    if fam["market_runs"] + 1 > caps["max_market_runs_per_family"]:
        return False, "market-run cap exhausted for this family"
    return True, "ok"


def ledger_n(ledger: dict) -> int:
    m = re.search(r"N for DSR = (\d+)", ledger["multiple_testing_rule"])
    if not m:
        raise ValueError("ledger does not state N")
    return int(m.group(1))


def check() -> int:
    b = json.loads(BUDGET.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    errs = violations(b)
    if ledger_n(ledger) != 43:
        errs.append(
            f"ledger states N={ledger_n(ledger)}; the budget baseline is 43 (needs an amendment)"
        )
    if errs:
        print("RESEARCH BUDGET VIOLATION:\n" + "\n".join(errs), file=sys.stderr)
        return 1
    st = b["state"]
    print(f"research budget ok: N={st['total_n']}/{b['caps']['max_total_n']}, "
          f"further families {len(st['further_families'])}/{b['caps']['max_further_families']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    raise SystemExit(check() if cmd == "check" else 2)
