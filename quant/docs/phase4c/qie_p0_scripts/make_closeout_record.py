"""QIE-P0: build the additive closeout freeze record. Reads ONLY tracked text records (protocol, docs, reports,
journal) and the three QIE-P0 documents; no market data, no network, no holdout. Run from the repository root:
    python quant/docs/phase4c/qie_p0_scripts/make_closeout_record.py
The hash of a file is the sha256 over its LF-normalised bytes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
Q = ROOT / "quant"
OUT = Q / "protocol" / "research_cycle_closeout_freeze_record.json"
SUFFIX = {".json", ".md", ".csv", ".svg", ".py", ".txt", ".tsv"}
NEW = {  # closeout files themselves and living documents are not pinned as historical records
    "quant/docs/phase4c/qie_p0_closeout_audit.md",
    "quant/docs/phase4c/qie_p0_reusable_inventory.md",
    "quant/docs/phase4c/qie_roadmap_design.md",
    "quant/docs/phase4c/s4_limitations_register.md",
    "quant/protocol/research_cycle_closeout_freeze_record.json",
}
HEAD_AT_AUDIT = "8766bf4a4fd47d459f5e1d83c15f9ccec6ff475a"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "quant/protocol", "quant/docs", "quant/reports", "quant/journal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return sorted(f for f in out if Path(f).suffix in SUFFIX and f not in NEW)


def main() -> None:
    pinned = {f: sha(ROOT / f) for f in tracked()}
    docs = {f: sha(ROOT / f) for f in sorted(NEW - {OUT.relative_to(ROOT).as_posix()})}
    budget = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))["state"]
    rec = {
        "id": "research-cycle-closeout-freeze-v1",
        "task": "QIE-P0 (Issue #2, owner approval relayed in comment 7237703953)",
        "kind": "ADDITIVE freeze record: nothing historical is edited, moved or deleted",
        "head_at_audit": HEAD_AT_AUDIT,
        "branch": "claude/freqtrade-trading-system-b82aek",
        "draft_pr": 1,
        "budget": {
            "total_n": budget["total_n"],
            "max_total_n": 52,
            "families_used": 1,
            "families_max": 3,
            "family_ids": [f["id"] for f in budget["further_families"]],
            "reset": False,
            "new_registration": False,
        },
        "frozen_outcomes": {
            "phase3": "all four strategies rejected; holdout not opened (no survivors)",
            "phase4_r1": "rejected on research data",
            "family_a": "not credible (fails T1/T3/T4/T7)",
            "h1": "L1 PASS with volatility confound (rank correlation -0.913 with 28-day volatility); M4 L2 NO-GO; TERMINATED; incremental MAX3 effect unresolved, not disproven",
            "m5_phase1": "synthetic calibration STOP before market access; family h1_vol_control never registered",
            "m6_s0": "claims C1-C4 falsified; overlap = risk overlay; recommendation NO-GO for registration; amendment A20",
        },
        "holdout": "2025-07-01..2026-11-25 never accessed according to every record; not inspected, not even metadata, in this audit",
        "licensing": "research-only data (Binance Vision CC BY-NC-SA 4.0; OKX public data for Phase 3); commercial and operational rights unresolved; licensing inquiry draft never sent; no rights assumed",
        "ci_evidence_final_head_8766bf4": {
            "upstream_jobs": 29,
            "success": 24,
            "skipped": 5,
            "failure": 0,
            "cancelled": 0,
            "run": 46129475243,
            "quant_ci_runs": [156, 157],
            "zizmor": "not read",
        },
        "unresolved": "see quant/docs/phase4c/s4_limitations_register.md (living; not pinned) and qie_p0_closeout_audit.md",
        "documents": docs,
        "pinned_records": pinned,
        "pin_rule": "each pinned file must hash to the recorded value, or to a successor declared by an amendment (tests/amend_chain.py)",
        "not_done": [
            "market data",
            "backtests",
            "holdout access",
            "registration",
            "budget consumption",
            "code or risk-limit changes",
            "paper/live trading",
        ],
    }
    OUT.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"pinned {len(pinned)} records; wrote {OUT}")


if __name__ == "__main__":
    main()
