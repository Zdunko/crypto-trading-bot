"""M6-S0 (synthetic only): estimator causality/units, sizing rules, determinism, reconciliation, pinned results and
the exposure-rule equivalence used in the overlap audit. Research outcomes (claims falsified) are PINNED as recorded
facts, not asserted as desirable; a correct SHUTDOWN is not a software failure."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantlab import lv_sleeve_harness as h
from quantlab.costs import BASE
from quantlab.execution import ExecConfig, History, PriceData, _liq, run
from quantlab.risk_v2 import RiskStateMachine, RiskV2Config
from quantlab.risk_v3 import RiskManagedStrategyV3, RiskV3Config


Q = Path(__file__).resolve().parents[1]
SLEEVE = h.load_freeze()["common"]["sleeve"]
RES = json.loads(h.RESULTS.read_text(encoding="utf-8"))


def flat_daily_feed(daily_prices: np.ndarray, pairs: list[str]) -> PriceData:
    """Hourly candles whose close equals the day's price for all 24 hours (daily samples = the given series)."""
    n = len(daily_prices) * 24
    idx = pd.date_range("2022-01-01", periods=n, freq="1h", tz="UTC")
    px = np.repeat(daily_prices, 24)
    df = pd.DataFrame({"date": idx, "open": px, "high": px, "low": px, "close": px, "volume": 1e9})
    return PriceData({p: df.copy() for p in pairs}, idx)


def sigma_at(d: PriceData, i: int, pairs: list[str], w: int = 60) -> float:
    return h.basket_vol(History(d, i), pairs, w)


def test_units_and_annualisation_match_an_independent_computation():
    pairs = h.PAIRS[:3]
    r = 0.02 * (-1.0) ** np.arange(61)  # alternating +-2 % daily returns
    px = 100.0 * np.cumprod(1.0 + np.concatenate([[0.0], r]))[:62]
    d = flat_daily_feed(px, pairs)
    got = sigma_at(d, len(d.index), pairs)
    sample = px[-61:]
    ret = sample[1:] / sample[:-1] - 1.0
    assert got == pytest.approx(np.std(ret, ddof=1) * math.sqrt(365.0), rel=1e-12)
    assert 0.34 < got < 0.40  # about 2 % x sqrt(365) = 0.382


def test_prefix_invariance_future_candles_do_not_change_the_estimate():
    pairs = h.PAIRS[:4]
    rng = np.random.default_rng(3)
    px = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 100)))
    d1 = flat_daily_feed(px, pairs)
    i = 70 * 24
    base = sigma_at(d1, i, pairs)
    px2 = px.copy()
    px2[70:] *= rng.uniform(0.2, 5.0, 30)  # mutate everything at or after the decision time
    assert sigma_at(flat_daily_feed(px2, pairs), i, pairs) == base


def test_zero_missing_and_short_history_are_fail_closed_or_capped_without_errors():
    pairs = h.PAIRS[:3]
    flat = flat_daily_feed(np.full(80, 100.0), pairs)
    assert sigma_at(flat, 70 * 24, pairs) == 0.0
    assert (
        h.target_exposure("LV-1", 0.0, 0.15, 0.10) == 0.15
    )  # zero volatility: the cap binds, no division
    short = flat_daily_feed(np.full(30, 100.0), pairs)
    assert math.isnan(sigma_at(short, 30 * 24, pairs))
    assert h.target_exposure("LV-1", float("nan"), 0.15, 0.10) == 0.0
    assert h.target_exposure("LV-2", float("nan"), 0.15, 0.10) == 0.0
    px = np.full(80, 100.0)
    d = flat_daily_feed(px, pairs)
    d.close[65 * 24 - 5, 0] = np.nan  # a missing close inside the window
    assert math.isnan(sigma_at(d, 70 * 24, pairs))


def test_target_exposure_rules():
    assert (
        h.target_exposure("LV-1", 0.28, 0.15, 0.10) == 0.15
    )  # cap binds (attainable volatility < target)
    assert h.target_exposure("LV-1", 1.0, 0.15, 0.10) == pytest.approx(0.10)
    assert h.target_exposure("LV-2", 1.0, 0.15, 0.10) == 0.15
    assert h.target_exposure("LV-1", -1.0, 0.15, 0.10) == 0.0


def test_v3_is_active_and_unchanged_in_the_harness():
    cfg = RiskV3Config()
    assert cfg.v2 == RiskV2Config() and cfg.v2.tier3_dd == 0.18 and cfg.v2.tier2_dd == 0.15
    assert cfg.gate_recovery == 0.0
    assert issubclass(RiskManagedStrategyV3, object)
    src = (Q / "quantlab/lv_sleeve_harness.py").read_text(encoding="utf-8")
    assert "RiskManagedStrategyV3(inner, m, cfg, feed)" in src and "breaker=False" not in src


def _row(fid: str, cfg: str) -> dict:
    return next(r for r in RES["runs"] if r["fixture"].startswith(fid) and r["config"] == cfg)


def test_determinism_and_reconciliation_on_a_stored_fixture():
    fr = h.load_freeze()
    fx = next(f for f in fr["fixtures"] if f["id"].startswith("F06"))
    a = h.run_fixture(fx, "LV-2", fr)
    assert a == h.run_fixture(
        fx, "LV-2", fr
    )  # same platform: bit-identical replay (hashes included)
    stored = _row("F06", "LV-2")
    # The stored hashes were produced on Linux; floating-point hashes are platform specific (macOS CI showed
    # identical behaviour and different hashes), so across platforms only the behavioural fields are compared.
    platform_specific = {"order_hash", "equity_series_hash"}
    assert a.keys() == stored.keys()
    for k in a.keys() - platform_specific:
        if isinstance(a[k], float):
            assert a[k] == pytest.approx(stored[k], rel=1e-9)
        else:
            assert a[k] == stored[k], k
    d = h.build_feed(fx, fr["common"])
    cfg = RiskV3Config()
    s = RiskManagedStrategyV3(
        h.SleeveInner("LV-2", fr["common"]["sleeve"]),
        RiskStateMachine.new(cfg.v2, 1000.0),
        cfg,
        None,
    )
    res = run(s, d, ExecConfig(wallet=1000.0, costs=BASE))
    pos = sum(
        _liq(p.qty, float(d.close_ff[-1, d.col[k]]), BASE) for k, p in res.state.positions.items()
    )
    assert res.state.cash + pos == pytest.approx(float(res.equity.iloc[-1]), rel=1e-9)


def test_f13_repeats_are_identical():
    rows = [r for r in RES["runs"] if r["fixture"].startswith("F13")]
    assert len(rows) == 4
    for cfg in ("LV-1", "LV-2"):
        a, b = [r for r in rows if r["config"] == cfg]
        assert (
            a["order_hash"] == b["order_hash"]
            and a["equity_series_hash"] == b["equity_series_hash"]
        )


def test_results_are_pinned_against_the_frozen_file_and_budget_is_unchanged():
    fr = h.load_freeze()
    assert RES["freeze"].endswith("m6_s0_fixtures_freeze.json") and RES["synthetic_only"] is True
    corr = json.loads(h.CORRECTIONS.read_text(encoding="utf-8"))
    ids = [f["id"] for f in [*fr["fixtures"], *corr["replacement_fixtures"]]]
    got = sorted({r["fixture"] for r in RES["runs"]})
    assert got == sorted(ids)
    b = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))
    assert b["state"]["total_n"] == 45
    assert [f["id"] for f in b["state"]["further_families"]] == ["h1_lottery_max3"]
    h_ = hashlib.sha256((Q / "protocol/m6_s0_fixtures_freeze.json").read_bytes()).hexdigest()
    rec = json.loads((Q / "protocol/m6_s0_record.json").read_text(encoding="utf-8"))
    assert rec["freeze_sha256"] == h_ and rec["freeze_commit"] == "b5907a5"
    for key, name in (
        ("report_sha256", rec["report"]),
        ("results_sha256", "docs/phase4c/m6_s0_results.json"),
        ("defect_corrections_sha256", "protocol/m6_s0_defect_corrections.json"),
    ):
        assert rec[key] == hashlib.sha256((Q / name).read_bytes()).hexdigest()
    assert rec["registration"] is False and rec["market_data"] is False


def test_recorded_claim_outcomes():
    c = RES["claims"]
    assert c["C1"]["status"] == "FALSIFIED" and c["C2"]["status"] == "FALSIFIED"
    assert c["C3"]["status"] == "FALSIFIED" and c["C4"]["status"] == "FALSIFIED"
    assert c["C5"]["falsified_by"] == []
    sh = {
        (r["fixture"][:3], r["config"]): r["shutdown"]["cause"]
        for r in RES["runs"]
        if r["shutdown"]
    }
    assert sh[("F05", "LV-1")] == "tier3_floor" and sh[("F03", "LV-2")] == "tier3_floor"
    assert sh[("F09", "LV-1")] == "integrity" and sh[("F10", "LV-2")] == "integrity"
    assert (
        "F03",
        "LV-1",
    ) not in sh  # LV-1 survived the repeated partial losses (still tier transitions)


def test_overlap_exposure_rule_equivalence_with_family_a_v0():
    sig = np.linspace(0.10, 3.0, 2000)
    v0 = np.minimum(1.0, 0.40 / sig)  # Family A V0 per-asset rule (target 40 %, cap 1)
    lv1 = np.array([h.target_exposure("LV-1", s, 0.15, 0.10) for s in sig])
    uncapped = sig >= 2.0 / 3.0
    assert np.allclose(lv1[uncapped], 0.25 * v0[uncapped], rtol=0, atol=1e-12)  # exactly 0.25 x V0
    rank = lambda x: pd.Series(x).rank().to_numpy()  # noqa: E731
    assert (
        np.corrcoef(rank(v0), rank(lv1))[0, 1] > 0.80
    )  # same inverse-volatility ordering above the caps
    assert np.all(np.diff(lv1) <= 1e-15) and np.all(
        np.diff(v0) <= 1e-15
    )  # both non-increasing in volatility
