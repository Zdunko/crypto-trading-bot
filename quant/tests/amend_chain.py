"""Helpers for tests that pin files which an owner-approved amendment later changed (A11: H1 registration).

A pinned hash stays valid; the successor hash is accepted ONLY if an amendment in the chain records exactly
from == pinned (or the current chain value) and to == the new value. Historical records are never edited."""

from __future__ import annotations

from pathlib import Path

from quantlab.protocol import load_amendments


Q = Path(__file__).resolve().parents[1]


def successor_hash(name: str, pinned: str) -> str:
    cur = pinned
    for a in load_amendments():
        for ch in a.get("changes", []):
            if ch["file"] == name and ch["from"] == cur:
                cur = ch["to"]
    return cur


def accepted(name: str, pinned: str) -> set[str]:
    return {pinned, successor_hash(name, pinned)}


def accepted_budget_states(recorded: dict) -> list[dict]:
    """The recorded (historical) state, plus the state declared by amendments that follow it."""
    out = [recorded]
    for a in load_amendments():
        if "budget_state_after" in a:
            out.append(a["budget_state_after"])
    return out


def accepted_approvals(recorded: list) -> list[list]:
    out = [recorded]
    for a in load_amendments():
        if "approvals_after" in a:
            out.append(a["approvals_after"])
    return out


def accepted_registry_ids(recorded: list) -> list[list]:
    out = [recorded]
    for a in load_amendments():
        if "registry_family_ids_after" in a:
            out.append(a["registry_family_ids_after"])
    return out
