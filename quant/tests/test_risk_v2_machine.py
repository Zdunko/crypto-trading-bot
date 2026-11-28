"""Risk layer V2 state machine: every transition, boundary, failure mode, property and replay (synthetic only)."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantlab.risk_v2 import (
    FLAT,
    NORMAL,
    REDUCED,
    REENTRY,
    SHUTDOWN,
    RiskStateMachine,
    RiskV2Config,
    risk_budget,
)
from quantlab.validation import evaluate_criteria


CFG = RiskV2Config()
T0 = pd.Timestamp("2024-01-01", tz="UTC")
H = lambda n: T0 + pd.Timedelta(hours=n)  # noqa: E731


class Sim:
    """Drives the machine like a compliant portfolio: gross = cap x equity, zero after a flatten."""

    def __init__(self, cfg=CFG, e0=1000.0, store=None):
        self.m = RiskStateMachine.new(cfg, e0, store)
        self.i = 0
        self.cap_prev = 1.0
        self.gross_override = None
        self.last = None

    def tick(self, equity, alarm=False, gross=None, at=None):
        t = at if at is not None else H(self.i)
        g = (
            gross
            if gross is not None
            else (
                self.gross_override if self.gross_override is not None else self.cap_prev * equity
            )
        )
        self.last = self.m.step(t, equity, g, alarm)
        if self.last.flatten and self.gross_override is None:
            self.cap_prev = 0.0
        else:
            self.cap_prev = self.last.cap
        self.i += 1
        return self.last

    def run(self, equities):
        for e in equities:
            self.tick(e)
        return self.m

    def to(self, state, e=1000.0):
        """Reach a state through the public API only."""
        if state == REDUCED:
            self.run([e, e * 0.89])
        elif state == FLAT:
            self.run([e, e * 0.84])
        elif state == REENTRY:
            self.run([e, e * 0.84])
            self.tick(e * 0.84, at=H(self.i + CFG.cooldown_hours))
        elif state == SHUTDOWN:
            self.run([e, e * 0.81])
        assert self.m.s.state == state
        return self.m


def eq(frac):
    return 1000.0 * frac


# ------------------------------------------------------------------ thresholds and boundaries
@pytest.mark.parametrize(
    "frac,expected",
    [(0.9001, NORMAL), (0.90, REDUCED), (0.8999, REDUCED), (0.8501, REDUCED), (0.85, FLAT)],
)
def test_tier1_and_tier2_boundaries_are_inclusive_at_exactly_the_threshold(frac, expected):
    s = Sim()
    s.run([1000.0, eq(frac)])
    assert s.m.s.state == expected


def test_reduced_returns_to_normal_only_strictly_below_the_exit_threshold():
    s = Sim()
    s.run([1000.0, 899.0])
    assert s.m.s.state == REDUCED
    s.tick(950.0)  # d_L = 5.0 % exactly: not yet
    assert s.m.s.state == REDUCED
    s.tick(950.1)
    assert s.m.s.state == NORMAL


@pytest.mark.parametrize("frac,state", [(0.8201, FLAT), (0.82, SHUTDOWN), (0.8199, SHUTDOWN)])
def test_tier3_floor_boundary_is_equity_at_or_below_hwm_times_one_minus_tier3(frac, state):
    s = Sim()
    s.run([1000.0, eq(frac)])
    assert s.m.s.state == state


def test_caps_per_state():
    s = Sim()
    assert s.tick(1000.0).cap == 1.0
    assert s.tick(895.0).cap == CFG.tier1_cap
    s2 = Sim()
    s2.run([1000.0, 840.0])
    assert s2.last.cap == 0.0 and s2.last.flatten


# ------------------------------------------------------------------ cooldown, re-entry steps, failures
def test_cooldown_is_exact_and_needs_a_flat_portfolio():
    s = Sim()
    s.run([1000.0, 840.0])  # tier 2 at hour 1
    end = H(1 + CFG.cooldown_hours)
    s.tick(840.0, at=end - pd.Timedelta(hours=1))
    assert s.m.s.state == FLAT
    s.tick(840.0, at=end, gross=5.0)  # cooldown over but positions still open
    assert s.m.s.state == FLAT
    s.tick(840.0, at=end + pd.Timedelta(hours=1), gross=0.0)
    assert s.m.s.state == REENTRY


def test_reentry_steps_advance_on_exact_boundaries_and_complete_without_resetting_the_hwm():
    s = Sim()
    s.to(REENTRY)
    t0 = pd.Timestamp(s.m.s.step_start)
    caps = []
    for k, _step in enumerate(CFG.steps):
        s.tick(840.0, at=t0 + pd.Timedelta(hours=CFG.step_hours * k + 1))
        caps.append(s.last.cap)
    assert s.m.s.step == len(CFG.steps) - 1
    assert caps[0] <= CFG.steps[0] and caps == sorted(
        caps
    )  # budget-limited, never above the step cap, non-decreasing
    hwm = s.m.s.hwm
    # recover to a small local drawdown; the final step has been held long enough -> complete
    s.tick(980.0, at=t0 + pd.Timedelta(hours=CFG.step_hours * 3 + 2))
    assert s.m.s.state == NORMAL and s.m.s.hwm == hwm == 1000.0


def test_reentry_stays_at_the_final_step_while_the_local_drawdown_is_still_deep():
    s = Sim()
    s.to(REENTRY)
    t0 = pd.Timestamp(s.m.s.step_start)
    for k in range(1, 6):
        s.tick(840.0, at=t0 + pd.Timedelta(hours=CFG.step_hours * k + 1))
    assert s.m.s.state == REENTRY and s.m.s.step == len(CFG.steps) - 1  # no loop back into tier 2


def later(s, hours=1):
    return pd.Timestamp(s.m.s.last_t) + pd.Timedelta(hours=hours)


# a wider floor than the default so that the re-entry failure rule (not the floor) is what is tested
CFG_F = RiskV2Config(
    tier3_dd=0.40, hard_dd=0.5, reentry_fail_loss=0.01, max_failed_reentries=2, max_flat_cycles=5
)


def test_failed_reentries_escalate_and_a_success_resets_the_counter():
    s = Sim(CFG_F)
    s.to(REENTRY)
    s.tick(840.0 * 0.989, at=later(s))  # first failure: loss > 1 %
    assert s.m.s.state == FLAT and s.m.s.failed_reentries == 1
    t = pd.Timestamp(s.m.s.cooldown_end) + pd.Timedelta(hours=1)
    s.tick(840.0 * 0.989, at=t, gross=0.0)
    assert s.m.s.state == REENTRY
    s.tick(840.0 * 0.989 * 0.989, at=t + pd.Timedelta(hours=1))  # second consecutive failure
    assert s.m.s.state == SHUTDOWN and s.m.s.shutdown_cause == "reentry_loop"
    s2 = Sim(CFG_F)
    s2.to(REENTRY)
    s2.tick(840.0 * 0.989, at=later(s2))
    t = pd.Timestamp(s2.m.s.cooldown_end) + pd.Timedelta(hours=1)
    s2.tick(840.0 * 0.989, at=t, gross=0.0)
    for k in range(1, 5):  # hold the final step, then complete after recovering
        s2.tick(990.0, at=t + pd.Timedelta(hours=CFG.step_hours * k + 1))
    assert s2.m.s.failed_reentries == 0 and s2.m.s.state in (NORMAL, REDUCED)


def test_with_default_parameters_the_floor_always_precedes_a_second_reentry_failure():
    s = Sim()
    s.run([1000.0, 849.0])  # tier 2 just above the 18 % floor
    t = pd.Timestamp(s.m.s.cooldown_end) + pd.Timedelta(hours=1)
    s.tick(849.0, at=t, gross=0.0)
    s.tick(
        849.0 * 0.969, at=t + pd.Timedelta(hours=1)
    )  # 3.1 % loss: breaches the 18 % floor (822.6 vs 820? no: 822.6 > 820)
    assert s.m.s.state == FLAT
    t2 = pd.Timestamp(s.m.s.cooldown_end) + pd.Timedelta(hours=1)
    s.tick(822.6, at=t2, gross=0.0)
    s.tick(822.6 * 0.969, at=t2 + pd.Timedelta(hours=1))
    assert (
        s.m.s.state == SHUTDOWN and s.m.s.shutdown_cause == "tier3_floor"
    )  # cumulative protection wins


def test_flat_cycle_budget_prevents_endless_halt_reentry_loops():
    cfg = RiskV2Config(
        tier3_dd=0.6, hard_dd=0.7, max_flat_cycles=2, max_failed_reentries=9, reentry_fail_loss=0.01
    )
    s = Sim(cfg)
    s.run([1000.0, 840.0])
    e = 840.0
    for _ in range(4):
        if s.m.s.state == SHUTDOWN:
            break
        t = pd.Timestamp(s.m.s.cooldown_end) + pd.Timedelta(hours=1)
        s.tick(e, at=t, gross=0.0)
        e *= 0.98
        s.tick(e, at=t + pd.Timedelta(hours=1))  # fail again
    assert s.m.s.state == SHUTDOWN and s.m.s.shutdown_cause == "flat_cycles"


# ------------------------------------------------------------------ simultaneous triggers and integrity
def test_simultaneous_triggers_produce_one_transition_with_fixed_precedence_and_an_audit_trail():
    s = Sim()
    s.tick(1000.0)
    n = len(s.m.records)
    d = s.tick(790.0, alarm=True)  # integrity + floor + tier2 + tier1 all true
    assert len(s.m.records) == n + 1 and d.transition["cause"] == "integrity"
    assert set(d.transition["conditions"]) >= {"integrity", "floor", "tier2"}
    s2 = Sim()
    s2.tick(1000.0)
    d2 = s2.tick(790.0)  # floor beats tier 2
    assert d2.transition["cause"] == "tier3_floor"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -5.0])
def test_invalid_equity_is_an_integrity_shutdown(bad):
    s = Sim()
    s.tick(1000.0)
    s.tick(bad)
    assert (
        s.m.s.state == SHUTDOWN
        and s.m.s.shutdown_cause == "integrity"
        and s.m.s.safety_disqualified
    )


def test_clock_regression_is_an_integrity_shutdown_and_the_same_candle_is_idempotent():
    s = Sim()
    s.tick(1000.0, at=H(5))
    d = s.tick(1000.0, at=H(5))
    assert d is s.last and len(s.m.records) == 0
    s.tick(1000.0, at=H(3))
    assert s.m.s.state == SHUTDOWN and s.m.s.shutdown_cause == "integrity"


def test_unliquidated_positions_after_the_alarm_window_trigger_shutdown():
    s = Sim()
    s.gross_override = 300.0  # liquidity never arrives
    s.run([1000.0, 840.0])
    for _ in range(CFG.liquidity_alarm_candles):
        s.tick(840.0)
    assert s.m.s.state == SHUTDOWN and s.m.s.shutdown_cause == "liquidation_unavailable"
    ok, why = s.m.authorize(H(s.i), 840.0, 300.0, {})
    assert not ok


# ------------------------------------------------------------------ gaps are not covered by the 18 % threshold
def test_a_gap_through_the_floor_is_reported_as_overshoot_not_hidden():
    s = Sim()
    s.tick(1000.0)
    d = s.tick(700.0)  # -30 % in one candle
    assert s.m.s.state == SHUTDOWN
    assert d.transition["d_global"] == pytest.approx(0.30)
    assert d.transition["d_global"] > CFG.tier3_dd  # the 18 % threshold is not a maximum loss
    assert s.m.report()["safety_events"][0]["equity"] == 700.0


def test_a_gap_during_reentry_can_breach_the_epoch_floor_and_the_hard_limit():
    s = Sim()
    s.run([1000.0, 810.0])  # shutdown at 19 %
    ok, _ = s.m.authorize(H(10), 810.0, 0.0, approval(s.m, H(10), loss=0.05, cap=1.0))
    assert ok
    d = s.tick(500.0, at=H(11))  # gap far below even the hard floor
    assert s.m.s.state == SHUTDOWN and d.transition["cause"] == "epoch_floor"
    assert d.transition["d_global"] > CFG.hard_dd


# ------------------------------------------------------------------ risk budget mathematics
def test_risk_budget_formula_with_fees_slippage_and_residual_exposure():
    phi = CFG.stress_gap + CFG.exit_cost
    b = risk_budget(1000.0, 820.0, 0.0, CFG)  # R = 180
    assert b["R"] == 180.0 and b["phi"] == pytest.approx(phi)
    assert b["allowed_total"] == pytest.approx(180.0 / (phi + CFG.entry_cost))
    b2 = risk_budget(1000.0, 820.0, 300.0, CFG)  # existing exposure uses part of the budget
    assert b2["allowed_total"] == pytest.approx(
        300.0 + (180.0 - phi * 300.0) / (phi + CFG.entry_cost)
    )
    b3 = risk_budget(
        1000.0, 820.0, 700.0, CFG
    )  # residual exposure above the budget: must shrink to R/phi
    assert b3["allowed_total"] == pytest.approx(180.0 / phi)
    assert b3["allowed_total"] < 700.0
    assert (
        risk_budget(1000.0, 1000.0, 0.0, CFG)["cap"] == 0.0
        and risk_budget(900.0, 1000.0, 0.0, CFG)["R"] == 0.0
    )
    # worst-case identity: stress loss on the allowed exposure plus entry costs never exceeds R
    for x_open in (0.0, 100.0, 250.0):
        a = risk_budget(1000.0, 820.0, x_open, CFG)["allowed_total"]
        assert phi * a + CFG.entry_cost * (a - x_open) <= 180.0 + 1e-9


def test_budget_caps_the_reentry_exposure_in_the_machine():
    s = Sim()
    s.to(REENTRY)  # equity 840, floor 820 -> R = 20
    cap = s.last.cap
    assert (
        cap == pytest.approx(risk_budget(840.0, 820.0, s.cap_prev * 840.0, CFG)["cap"], abs=0.02)
        and cap < 0.25
    )


# ------------------------------------------------------------------ manual authorisation
def approval(m, t, loss=0.03, cap=0.5, **over):
    d = {"shutdown_id": m.s.shutdown_id, "approver": "owner", "exposure_cap": cap, "epoch_loss_limit": loss,
         "approval_id": "ap-1", "issued_at": str(t)}  # fmt: skip
    d.update(over)
    return d


def shut(e_end=810.0):
    s = Sim()
    s.run([1000.0, e_end])
    assert s.m.s.state == SHUTDOWN
    return s


def test_authorised_restart_does_not_retrigger_tier3_and_keeps_the_hwm_and_the_disqualification():
    s = shut()
    t = H(20)
    ok, why = s.m.authorize(t, 810.0, 0.0, approval(s.m, t))
    assert ok, why
    assert (
        s.m.s.state == REENTRY
        and s.m.s.hwm == 1000.0
        and s.m.s.epoch == 1
        and s.m.s.safety_disqualified
    )
    d = s.tick(810.0, at=H(21))  # still 19 % below the HWM: the epoch floor, not tier 3, governs
    assert s.m.s.state == REENTRY and d.cap <= 0.5
    floor = s.m.floor()
    assert floor == pytest.approx(max(810.0 * 0.97, 1000.0 * 0.75))
    s.tick(floor + 0.01, at=H(22))
    assert s.m.s.state == REENTRY
    s.tick(floor - 0.01, at=H(23))
    assert (
        s.m.s.state == SHUTDOWN
        and s.m.s.shutdown_cause == "epoch_floor"
        and s.m.s.safety_disqualified
    )


def test_cumulative_protection_survives_repeated_authorisations_via_the_hard_limit():
    s = shut(790.0)
    for k, e in enumerate((790.0, 760.0)):
        t = H(100 + 50 * k)
        ok, why = s.m.authorize(t, e, 0.0, approval(s.m, t, approval_id=f"ap-{k}"))
        assert ok, why
        s.tick(
            e * 0.9, at=t + pd.Timedelta(hours=1)
        )  # 10 % loss in the new epoch -> shutdown again
        assert s.m.s.state == SHUTDOWN
    t = H(400)
    ok, why = s.m.authorize(
        t, 740.0, 0.0, approval(s.m, t, approval_id="ap-9")
    )  # 740 <= 1000 * 0.75
    assert not ok and "hard drawdown" in why
    assert s.m.s.hwm == 1000.0 and s.m.s.safety_disqualified and len(s.m.s.safety_events) >= 3


@pytest.mark.parametrize(
    "over,fragment",
    [({"shutdown_id": "nope"}, "mismatch"), ({"approver": " "}, "approver"), ({"exposure_cap": 0}, "exposure_cap"),
     ({"exposure_cap": 1.5}, "exposure_cap"), ({"exposure_cap": float("nan")}, "exposure_cap"), ({"epoch_loss_limit": 0.06}, "epoch_loss_limit"),
     ({"epoch_loss_limit": 0}, "epoch_loss_limit"), ({"issued_at": "2024-01-01T00:00:00"}, "timezone"),
     ({"issued_at": "2023-12-31T00:00:00+00:00"}, "older"), ({"issued_at": "2024-02-01T00:00:00+00:00"}, "future"),
     ({"approval_id": ""}, "approval id"), ({"approval_id": None}, "approval id")],
)  # fmt: skip
def test_invalid_approvals_are_rejected_and_leave_the_machine_untouched(over, fragment):
    s = shut()
    before = json.dumps(s.m.report(), sort_keys=True, default=str)
    t = H(20)
    ok, why = s.m.authorize(t, 810.0, 0.0, approval(s.m, t, **over))
    assert not ok and fragment in why
    assert (
        json.dumps(s.m.report(), sort_keys=True, default=str) == before and s.m.s.state == SHUTDOWN
    )


def test_stale_duplicate_malformed_and_wrong_state_approvals():
    s = shut()
    ok, why = s.m.authorize(H(1000), 810.0, 0.0, approval(s.m, H(2)))
    assert not ok and "stale" in why
    ok, _ = s.m.authorize(H(20), 810.0, 0.0, approval(s.m, H(20)))
    assert ok
    ok, why = s.m.authorize(H(21), 810.0, 0.0, approval(s.m, H(21)))
    assert not ok and "not in SHUTDOWN" in why
    s.tick(810.0 * 0.5, at=H(22))  # second shutdown, new id
    again = approval(s.m, H(23))  # same approval id as the first approval
    ok, why = s.m.authorize(H(23), 405.0, 0.0, again)
    assert not ok  # duplicate id (and also beyond the hard limit); either way never accepted
    ok, why = s.m.authorize(H(23), 810.0, 0.0, {"approver": "x"})
    assert not ok and "malformed" in why
    ok, why = s.m.authorize(H(23), 810.0, 0.0, "/nonexistent/approval.json")
    assert not ok and "malformed" in why


def test_duplicate_approval_replay_is_rejected_even_when_everything_else_is_valid():
    s = shut(805.0)
    ok, _ = s.m.authorize(H(20), 805.0, 0.0, approval(s.m, H(20)))
    assert ok
    s.tick(805.0 * 0.96, at=H(21))  # epoch floor breach -> SHUTDOWN
    assert s.m.s.state == SHUTDOWN
    ok, why = s.m.authorize(
        H(30), 805.0 * 0.96, 0.0, approval(s.m, H(30))
    )  # same approval_id "ap-1"
    assert not ok and "duplicate" in why


def test_approval_file_roundtrip(tmp_path):
    s = shut()
    p = tmp_path / "approval.json"
    p.write_text(json.dumps(approval(s.m, H(20))))
    ok, why = s.m.authorize(H(21), 810.0, 0.0, p)
    assert ok, why
    p.write_text("{not json")
    s.tick(810.0 * 0.5, at=H(22))
    ok, why = s.m.authorize(H(23), 405.0, 0.0, p)
    assert not ok and "malformed" in why


# ------------------------------------------------------------------ SAFETY_DISQUALIFIED is independent of T4
def test_safety_disqualification_is_permanent_and_t4_is_computed_from_equity_only():
    s = shut()
    assert s.m.s.safety_disqualified
    ok, _ = s.m.authorize(H(20), 810.0, 0.0, approval(s.m, H(20)))
    for k in range(1, 8):  # long recovery through re-entry to the end
        s.tick(900.0 + 10 * k, at=H(20) + pd.Timedelta(hours=CFG.step_hours * k))
    assert ok and s.m.s.safety_disqualified and s.m.report()["safety_disqualified"] is True
    crit = {"T1": {"min_trades": 200, "max_pair_profit_share": 0.3}, "T2": {"min_net_return_exclusive": 0.0},
            "T3": {}, "T4": {"max_drawdown": 0.20, "also_not_above_benchmark": True}, "T5": {"min_profit_factor": 1.3},
            "T6": {"min_profit_factor": 1.0, "requires_positive_net_return": True},
            "T7": {"min_positive_window_share": 0.6, "max_window_profit_share": 0.5},
            "T8": {"min_regime_trades": 30, "min_profit_factor": 0.8}, "T9": {"min_positive_variant_share": 0.75},
            "T10": {}}  # fmt: skip

    def t4(dd):
        m = {"base": {"trades": 300, "net_return": 0.1, "max_drawdown": dd, "sortino": 2.0, "profit_factor": 2.0},
             "pair_share_max": 0.1, "bench": {"sortino": 1.0, "max_drawdown": 0.9},
             "stress": {"net_return": 0.1, "profit_factor": 2.0}, "windows": [], "regimes": {}, "variants": [],
             "bias_clean": True}  # fmt: skip
        return next(r for r in evaluate_criteria(m, crit) if r["id"] == "T4")["passed"]

    assert t4(0.18) is True and t4(0.2001) is False  # a tier-3 event at 18 % is not a T4 breach


# ------------------------------------------------------------------ property tests (seeded, deterministic)
def random_path(seed, n=1500, vol=0.02):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, vol, n)
    r[rng.integers(0, n, 3)] -= rng.uniform(0.0, 0.25, 3)  # occasional gaps
    return 1000.0 * np.exp(np.cumsum(r))


@pytest.mark.parametrize("seed", range(40))
def test_invariants_hold_on_random_paths(seed):
    cfg = RiskV2Config()
    s = Sim(cfg)
    path = random_path(seed)
    prev_hwm, seen_max = 1000.0, 1000.0
    flat_run = 0
    for e in path:
        n_before = len(s.m.records)
        flag_before = s.m.s.safety_disqualified
        s.tick(float(e))
        seen_max = max(seen_max, e)
        st = s.m.s
        assert st.hwm == pytest.approx(seen_max)  # I1: HWM is the running maximum, never reset
        assert st.hwm >= prev_hwm
        assert len(s.m.records) - n_before <= 1  # I2: at most one transition per candle
        assert st.safety_disqualified or not flag_before  # I3: the flag never clears
        assert 0.0 <= s.last.cap <= 1.0 and (
            s.last.cap == 0.0 or st.state not in (FLAT, SHUTDOWN)
        )  # I4
        if st.epoch == 0 and e <= st.hwm * (1 - cfg.tier3_dd):
            assert st.state == SHUTDOWN  # I5: floor breach in epoch 0 always ends in SHUTDOWN
        flat_run = flat_run + 1 if st.state == FLAT else 0
        assert flat_run <= cfg.cooldown_hours + 2  # I6: no lock-in: FLAT lasts at most the cooldown
        prev_hwm = st.hwm
    # I7: replay determinism
    s2 = Sim(cfg)
    for e in path:
        s2.tick(float(e))
    assert [r["hash"] for r in s.m.records] == [r["hash"] for r in s2.m.records]


def test_flat_cycles_are_bounded_on_adversarial_oscillating_paths():
    cfg = RiskV2Config()
    s = Sim(cfg)
    e = 1000.0
    for k in range(4000):
        e *= 0.985 if (k // 40) % 2 == 0 else 1.016  # slow bleed / rally oscillation
        s.tick(e)
    flats = sum(1 for r in s.m.records if r["to"] == FLAT)
    assert flats <= cfg.max_flat_cycles + 1 and s.m.s.state in (
        SHUTDOWN,
        NORMAL,
        REDUCED,
        REENTRY,
        FLAT,
    )


# ------------------------------------------------------------------ the complete transition table
def test_every_allowed_transition_is_reachable_and_nothing_else_happens():
    seen = set()

    def collect(sim):
        for r in sim.m.records:
            seen.add((r["from"], r["to"]))

    s = Sim()
    s.run([1000.0, 895.0, 960.0])  # NORMAL->REDUCED, REDUCED->NORMAL
    s.run([860.0, 840.0])  # NORMAL->REDUCED->FLAT? (REDUCED->FLAT)
    collect(s)
    s = Sim()
    s.run([1000.0, 840.0])  # NORMAL->FLAT
    t = pd.Timestamp(s.m.s.cooldown_end) + pd.Timedelta(hours=1)
    s.tick(840.0, at=t, gross=0.0)  # FLAT->REENTRY
    for k in range(1, 4):
        s.tick(840.0, at=t + pd.Timedelta(hours=CFG.step_hours * k + 1))  # REENTRY->REENTRY (steps)
    s.tick(990.0, at=t + pd.Timedelta(hours=CFG.step_hours * 4 + 1))  # REENTRY->NORMAL
    s.tick(840.0 * 0.9, at=t + pd.Timedelta(hours=CFG.step_hours * 5))  # NORMAL->SHUTDOWN (floor)
    collect(s)
    s = Sim(CFG_F)
    s.to(REENTRY)
    s.tick(840.0 * 0.98, at=later(s))  # REENTRY->FLAT
    s.tick(500.0, at=later(s))  # FLAT->SHUTDOWN (floor at 60 % of the HWM)
    collect(s)
    s = Sim()
    s.to(REENTRY)
    s.tick(500.0, at=later(s))  # REENTRY->SHUTDOWN
    collect(s)
    s = shut()
    s.m.authorize(H(30), 810.0, 0.0, approval(s.m, H(30)))  # SHUTDOWN->REENTRY
    collect(s)
    s = Sim()
    s.tick(1000.0)
    s.tick(1000.0, alarm=True)  # NORMAL->SHUTDOWN (integrity)
    collect(s)
    s = Sim()
    s.run([1000.0, 895.0, 700.0])  # REDUCED->SHUTDOWN
    collect(s)
    expected = {(NORMAL, REDUCED), (REDUCED, NORMAL), (REDUCED, FLAT), (NORMAL, FLAT), (FLAT, REENTRY), (REENTRY, REENTRY),
                (REENTRY, NORMAL), (NORMAL, SHUTDOWN), (REENTRY, FLAT), (FLAT, SHUTDOWN), (REENTRY, SHUTDOWN), (SHUTDOWN, REENTRY),
                (REDUCED, SHUTDOWN)}  # fmt: skip
    assert (
        seen == expected
    )  # SHUTDOWN has no other exit; REENTRY->REDUCED shares the code path with REENTRY->NORMAL


# ------------------------------------------------------------------ deterministic replay across processes
def test_replay_hash_is_identical_in_a_separate_process(tmp_path):
    path = random_path(7, n=800)
    s = Sim()
    for e in path:
        s.tick(float(e))
    mine = hashlib.sha256(json.dumps([r["hash"] for r in s.m.records]).encode()).hexdigest()
    script = tmp_path / "child.py"
    root = Path(__file__).resolve().parents[1]
    script.write_text(
        f"import sys, json, hashlib\nsys.path.insert(0, {str(root)!r}); sys.path.insert(0, {str(root / 'tests')!r})\n"
        "from test_risk_v2_machine import Sim, random_path\n"
        "s = Sim()\n[s.tick(float(e)) for e in random_path(7, n=800)]\n"
        "print(hashlib.sha256(json.dumps([r['hash'] for r in s.m.records]).encode()).hexdigest())\n"
    )
    out = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == mine
