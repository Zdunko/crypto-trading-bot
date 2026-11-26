"""Persistence, restarts, interrupted writes, tampering and fail-closed behaviour of the risk state."""

import hashlib
import json
import os

import pandas as pd
import pytest
from test_risk_v2_machine import CFG, H, Sim, approval, random_path

from quantlab.risk_v2 import NORMAL, REENTRY, SHUTDOWN, RiskStateMachine, StateError, StateStore


def mk(tmp_path):
    return StateStore(tmp_path / "risk_state.json")


def run_with_store(store, path, upto=None):
    s = Sim(store=store)
    for e in path[:upto]:
        s.tick(float(e))
    return s


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_state_round_trips_exactly_and_resume_continues_like_an_uninterrupted_run(tmp_path):
    path = random_path(3, n=900)
    store = mk(tmp_path)
    first = run_with_store(store, path, 400)
    m2 = RiskStateMachine.resume(CFG, store)  # simulated process restart
    assert m2.s == first.m.s and m2.records == first.m.records
    cont = Sim(store=None)
    cont.m = m2
    cont.i, cont.cap_prev = first.i, first.cap_prev
    for e in path[400:]:
        cont.tick(float(e))
    full = run_with_store(StateStore(tmp_path / "full.json"), path)
    assert [r["hash"] for r in cont.m.records] == [r["hash"] for r in full.m.records]
    assert cont.m.s.hwm == full.m.s.hwm and cont.m.s.state == full.m.s.state


def test_new_run_refuses_to_overwrite_an_existing_state_file(tmp_path):
    store = mk(tmp_path)
    RiskStateMachine.new(CFG, 1000.0, store)
    with pytest.raises(StateError, match="refusing"):
        RiskStateMachine.new(CFG, 1000.0, store)
    RiskStateMachine.new(CFG, 1000.0, store, overwrite=True)  # only by an explicit decision


@pytest.mark.parametrize("damage", ["flip_byte", "truncate", "empty", "garbage", "delete"])
def test_corrupt_or_missing_state_means_shutdown_fail_closed(tmp_path, damage):
    store = mk(tmp_path)
    run_with_store(store, random_path(1, n=300))
    raw = store.path.read_bytes()
    if damage == "flip_byte":
        i = raw.index(b"hwm") + 5
        store.path.write_bytes(raw[:i] + bytes([raw[i] ^ 0x01]) + raw[i + 1 :])
    elif damage == "truncate":
        store.path.write_bytes(raw[: len(raw) // 2])
    elif damage == "empty":
        store.path.write_bytes(b"")
    elif damage == "garbage":
        store.path.write_bytes(b"\x00\xff not json")
    else:
        store.path.unlink()
    m = RiskStateMachine.resume(CFG, store)
    assert (
        m.s.state == SHUTDOWN
        and m.s.shutdown_cause == "state_integrity"
        and m.s.safety_disqualified
        and m.store_error
    )
    d = m.step(H(1000), 1000.0, 0.0)
    assert d.cap == 0.0  # never trades again from this state
    ok, why = m.authorize(H(1001), 1000.0, 0.0, {})
    assert not ok and "state_integrity" in why


def test_edit_without_recomputing_the_hash_is_detected(tmp_path):
    store = mk(tmp_path)
    s = run_with_store(store, [1000.0, 810.0])
    assert s.m.s.state == SHUTDOWN
    raw = json.loads(store.path.read_text())
    raw["body"]["state"]["state"] = NORMAL  # an attacker flips SHUTDOWN to NORMAL
    store.path.write_text(json.dumps(raw))
    assert RiskStateMachine.resume(CFG, store).s.shutdown_cause == "state_integrity"


def test_edit_with_a_recomputed_file_hash_is_caught_by_the_record_chain_or_the_external_anchor(
    tmp_path,
):
    from quantlab.risk_v2 import _canon, _digest

    store = mk(tmp_path)
    s = run_with_store(store, [1000.0, 895.0, 960.0, 840.0])
    anchor = s.m.head
    raw = json.loads(store.path.read_text())
    # (a) forge a transition record and fix the outer hash: the record chain breaks
    raw["body"]["records"][0]["cause"] = "forged"
    raw["head"] = _digest(_canon(raw["body"]))
    store.path.write_text(json.dumps(raw))
    assert RiskStateMachine.resume(CFG, store).s.shutdown_cause == "state_integrity"
    # (b) forge only the state and fix the outer hash: valid chain, but the external anchor catches it
    store2 = StateStore(tmp_path / "second.json")
    s2 = run_with_store(store2, [1000.0, 810.0])
    anchor2 = s2.m.head
    raw = json.loads(store2.path.read_text())
    raw["body"]["state"]["state"] = NORMAL
    raw["body"]["state"]["safety_disqualified"] = False
    raw["head"] = _digest(_canon(raw["body"]))
    store2.path.write_text(json.dumps(raw))
    forged = RiskStateMachine.resume(
        CFG, store2
    )  # no anchor: a determined editor who recomputes the hash is NOT detected
    assert forged.s.state == NORMAL
    anchored = RiskStateMachine.resume(CFG, store2, expected_head=anchor2)  # with the anchor it is
    assert anchored.s.state == SHUTDOWN and anchored.s.shutdown_cause == "state_integrity"
    assert anchor  # (documented limitation: the hash chain is tamper EVIDENCE, the anchor must live outside the file)


def test_rollback_to_an_older_valid_file_is_detected_with_the_anchor(tmp_path):
    store = mk(tmp_path)
    s = run_with_store(store, [1000.0, 895.0])
    old = store.path.read_bytes()
    s.tick(840.0)
    anchor_new = s.m.head
    store.path.write_bytes(old)  # restore an earlier, internally valid state
    assert (
        RiskStateMachine.resume(CFG, store, expected_head=anchor_new).s.shutdown_cause
        == "state_integrity"
    )


def test_interrupted_write_leaves_the_previous_file_complete_and_a_stray_tmp_is_ignored(
    tmp_path, monkeypatch
):
    store = mk(tmp_path)
    s = run_with_store(store, [1000.0, 895.0])
    before = sha(store.path)
    real_replace = os.replace

    def boom(src, dst):
        raise OSError("disk full / killed before rename")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        s.tick(
            840.0
        )  # the state change cannot be persisted: the exception propagates, nothing is silently lost
    monkeypatch.setattr(os, "replace", real_replace)
    assert sha(store.path) == before  # previous file untouched
    assert store.path.with_name(store.path.name + ".tmp").exists()  # the half-written attempt
    m = RiskStateMachine.resume(CFG, store)
    assert m.s.state != SHUTDOWN or m.s.shutdown_cause != "state_integrity"
    assert not store.path.with_name(store.path.name + ".tmp").exists()


def test_partially_written_main_file_is_treated_as_corruption(tmp_path):
    store = mk(tmp_path)
    run_with_store(store, [1000.0, 895.0])
    full = store.path.read_text()
    store.path.write_text(full[: len(full) - 17])  # a non-atomic writer died mid-write
    assert RiskStateMachine.resume(CFG, store).s.shutdown_cause == "state_integrity"


def test_authorisation_and_consumed_approvals_survive_a_restart(tmp_path):
    store = mk(tmp_path)
    s = Sim(store=store)
    s.run([1000.0, 810.0])
    ok, why = s.m.authorize(H(20), 810.0, 0.0, approval(s.m, H(20)))
    assert ok, why
    m = RiskStateMachine.resume(CFG, store)
    assert (
        m.s.state == REENTRY
        and m.s.epoch == 1
        and m.s.consumed_approvals == ["ap-1"]
        and m.s.hwm == 1000.0
    )
    d = m.step(H(21), 810.0, 0.0)
    assert d.state == REENTRY
    m.step(H(22), 810.0 * 0.5, 0.0)  # epoch floor breach -> SHUTDOWN again
    m2 = RiskStateMachine.resume(CFG, store)
    ok, why = m2.authorize(
        H(30), 405.0, 0.0, approval(m2, H(30))
    )  # the same approval id replayed after a restart
    assert not ok and "duplicate" in why


def test_safety_flag_persists_across_restart_and_recovery(tmp_path):
    store = mk(tmp_path)
    s = Sim(store=store)
    s.run([1000.0, 810.0])
    s.m.authorize(H(20), 810.0, 0.0, approval(s.m, H(20)))
    m = RiskStateMachine.resume(CFG, store)
    assert m.s.safety_disqualified and len(m.s.safety_events) == 1
    for k in range(1, 8):
        m.step(H(20) + pd.Timedelta(hours=CFG.step_hours * k), 900.0 + 10 * k, 0.0)
    assert m.s.safety_disqualified  # recovery never erases the historical disqualification


def test_store_files_are_valid_json_with_a_single_head_hash(tmp_path):
    store = mk(tmp_path)
    run_with_store(store, [1000.0, 895.0])
    raw = json.loads(store.path.read_text())
    assert set(raw) == {"body", "head"} and set(raw["body"]) == {"records", "state"}
