"""M2: the registered L1 rules on SYNTHETIC panels only: formula, direction, ties, missing data, epochs, causality,
return definition, statistics, disguise check, decision logic, and the PIT-dataset adapter (fake archive)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synth_pit import build

from quantlab import l1_max3 as m
from quantlab import pit_loader as pl
from quantlab.gate_audit import _hac_t


Q = Path(__file__).resolve().parents[1]
SPEC = json.loads((Q / "protocol/h1_l1_preregistration.json").read_text(encoding="utf-8"))
W = 28


def panel(t_n=900, s_n=40, seed=1, kappa=0.0, jump_p=0.04, jump=0.15):
    """Synthetic daily panel. Asset i has lottery propensity lam_i: more upward jumps and (if kappa > 0) a lower drift."""
    rng = np.random.default_rng(seed)
    lam = rng.uniform(0.0, 1.0, s_n)
    r = rng.normal(0.0, 0.03, (t_n, s_n))
    pj = jump_p * (0.2 + 2 * lam)
    v = rng.random(
        (t_n, s_n)
    )  # symmetric jumps: lottery-like assets jump up AND down equally often (zero mean)
    r += (v < pj) * jump - ((v >= pj) & (v < 2 * pj)) * jump
    r -= kappa * (lam - lam.mean()) * 0.01  # planted premium: lottery-like assets earn less
    close = 100 * np.exp(np.cumsum(r, axis=0))
    open_ = np.vstack([np.full((1, s_n), 100.0), close[:-1]])
    dates = pd.date_range("2021-01-01", periods=t_n, freq="1D", tz="UTC")
    return m.Panel(
        dates,
        [f"S{i}USDT" for i in range(s_n)],
        open_,
        close,
        np.ones((t_n, s_n), bool),
        np.zeros((t_n, s_n), int),
    )


def spec_for(p: m.Panel, h: int = 7) -> dict:
    s = json.loads(json.dumps(SPEC))
    s["evaluation"].update(
        panel_first_candle_open=str(p.dates[0].date()),
        first_signal_date=str(p.dates[W + 2].date()),
        last_candle_open=str(p.dates[-1].date()),
        subperiods={
            "P1": [str(p.dates[W + 2].date()), str(p.dates[len(p.dates) // 2].date())],
            "P2": [str(p.dates[len(p.dates) // 2 + 1].date()), str(p.dates[-1].date())],
        },
    )
    s["evaluation"]["regime"]["reference_symbol"] = p.symbols[0]
    s["statistics"].update(
        min_assets_per_day=10, min_valid_ic_days=200, min_mean_assets=10, bootstrap_draws=199
    )
    return s


# ------------------------------------------------------------------ signal formula, direction, missing data, epochs
def test_max3_is_minus_the_mean_of_the_three_largest_daily_returns_in_the_28_day_window():
    t_n = 60
    ret = np.zeros((t_n, 2))
    ret[40, 0], ret[41, 0], ret[35, 0], ret[39, 0] = (
        0.30,
        0.20,
        0.10,
        0.05,
    )  # asset 0: top3 = 0.30, 0.20, 0.10
    ret[40, 1] = 0.60  # asset 1: a single huge day, the other two of the top 3 are 0
    close = 100 * np.cumprod(1 + ret, axis=0)
    s = m.max3(close, np.zeros((t_n, 2), int), W, 3)
    assert s[45, 0] == pytest.approx(-(0.30 + 0.20 + 0.10) / 3, rel=1e-9)
    assert s[45, 1] == pytest.approx(-0.60 / 3, rel=1e-9)
    ret[40, 1] = 0.90
    s2 = m.max3(100 * np.cumprod(1 + ret, axis=0), np.zeros((t_n, 2), int), W, 3)
    assert s2[45, 1] < s[45, 1]  # a more lottery-like asset gets a LOWER score (it is avoided)
    assert (
        np.isnan(s[W - 1]).all() and np.isfinite(s[W]).all()
    )  # first valid day: a full window exists


def test_max3_window_drops_old_spikes_and_needs_a_complete_window():
    t_n = 80
    ret = np.zeros((t_n, 1))
    ret[30, 0] = 0.5
    close = 100 * np.cumprod(1 + ret, axis=0)
    es = np.zeros((t_n, 1), int)
    s = m.max3(close, es, W, 3)
    assert s[30 + W - 1, 0] < 0  # day 57 still contains day 30
    assert s[30 + W, 0] == pytest.approx(0.0)  # day 58: out of the window
    miss = close.copy()
    miss[50, 0] = np.nan
    s = m.max3(miss, es, W, 3)
    assert np.isnan(s[50:79, 0]).all() or (
        np.isnan(s[50, 0]) and np.isnan(s[51, 0])
    )  # any missing day invalidates
    assert np.isnan(s[50 : 50 + W, 0]).all()


def test_identity_epoch_break_invalidates_windows_that_cross_it():
    t_n = 100
    close = 100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0, 0.02, (t_n, 1)), axis=0))
    es = np.zeros((t_n, 1), int)
    es[60:] = 60  # a new identity epoch starts on day 60
    s = m.max3(close, es, W, 3)
    assert np.isnan(s[60 : 60 + W, 0]).all() and np.isfinite(s[60 + W, 0]) and np.isfinite(s[59, 0])
    assert np.isnan(m.max3(close, np.full((t_n, 1), -1), W, 3)).all()  # no epoch = no signal


def test_signal_is_causal_prefix_invariant_and_ignores_future_perturbation():
    p = panel(t_n=300, seed=5)
    full = m.max3(p.close, p.epoch_start, W, 3)
    for cut in (120, 200, 299):
        part = m.max3(p.close[: cut + 1], p.epoch_start[: cut + 1], W, 3)
        assert np.array_equal(part, full[: cut + 1], equal_nan=True)
    pert = p.close.copy()
    pert[151:] *= np.random.default_rng(9).uniform(0.2, 5.0, pert[151:].shape)
    assert np.array_equal(m.max3(pert, p.epoch_start, W, 3)[:151], full[:151], equal_nan=True)


# ------------------------------------------------------------------ forward returns, ties, missing exits
def test_forward_return_is_open_to_open_from_the_day_after_the_signal():
    o = np.array([[10.0], [11.0], [12.0], [15.0], [16.0], [20.0]])
    c = o + 0.5
    r = m.forward_returns(o, c, 2)
    assert r[0, 0] == pytest.approx(
        o[3, 0] / o[1, 0] - 1
    )  # signal day 0 -> entry open[1], exit open[3]
    assert r[2, 0] == pytest.approx(o[5, 0] / o[3, 0] - 1) and np.isnan(r[3:, 0]).all()


def test_missing_exit_uses_the_last_observed_close_and_zero_recovery_is_only_a_sensitivity():
    o = np.array([[10.0], [10.0], [10.0], [np.nan], [np.nan], [np.nan], [np.nan]])
    c = np.array([[10.0], [10.0], [8.0], [np.nan], [np.nan], [np.nan], [np.nan]])
    r = m.forward_returns(o, c, 3)
    assert r[0, 0] == pytest.approx(
        8.0 / 10.0 - 1
    )  # delisted inside the horizon: last observed close, no invented recovery
    rz = m.forward_returns(o, c, 3, delist_return=-1.0)
    assert rz[0, 0] == -1.0  # the sensitivity: zero recovery
    gap = np.array([[10.0], [10.0], [np.nan], [12.0], [13.0]])
    assert m.forward_returns(gap, gap, 2)[0, 0] == pytest.approx(
        12.0 / 10.0 - 1
    )  # exit candle exists
    noentry = np.array([[10.0], [np.nan], [10.0], [10.0]])
    assert np.isnan(m.forward_returns(noentry, noentry, 2)[0, 0])  # no entry candle: no observation


def test_rank_ic_handles_ties_constant_cross_sections_and_minimum_assets():
    x = np.array([1.0, 1.0, 2.0, 3.0, 3.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    mask = np.ones(5, bool)
    ic, n = m.rank_ic(x, y, mask, 3)
    rx = pd.Series(x).rank().to_numpy()
    assert n == 5 and ic == pytest.approx(np.corrcoef(rx, pd.Series(y).rank().to_numpy())[0, 1])
    assert np.isnan(m.rank_ic(np.ones(5), y, mask, 3)[0])  # constant cross-section: no IC
    assert np.isnan(m.rank_ic(x, y, mask, 6)[0])  # fewer than the minimum
    assert m.rank_ic(x, y, np.array([1, 1, 1, 0, 0], bool), 3)[1] == 3  # only members count


# ------------------------------------------------------------------ statistics
def test_newey_west_matches_the_audited_hac_and_holm_is_correct():
    rng = np.random.default_rng(2)
    x = (
        rng.normal(0.01, 0.1, 800)
        + np.convolve(rng.normal(0, 0.05, 807), np.ones(8) / 8, "valid")[:800]
    )
    mean, se, _ = m.newey_west(x, 14)
    assert mean / se == pytest.approx(_hac_t(x[None, :], lag=14)[0], rel=1e-9)
    assert m.holm([0.01, 0.04]) == pytest.approx([0.02, 0.04])
    assert m.holm([0.03, 0.02]) == pytest.approx([0.04, 0.04])  # monotone adjustment
    assert all(a <= 1 for a in m.holm([0.9, 0.8, 0.7]))
    t1, t2 = m.test_series(x, 14, 99, 7), m.test_series(x, 14, 99, 7)
    assert (
        t1 == t2 and t1["effective_n_days"] < t1["n_days"] * 1.5 and 0 < t1["p_one_sided_raw"] < 1
    )


def test_planted_lottery_effect_is_detected_and_the_null_is_not():
    spec = spec_for(panel())
    big = panel(t_n=900, s_n=60, seed=11, kappa=6.0)
    null = panel(t_n=900, s_n=60, seed=12, kappa=0.0)
    r_big = m.evaluate(big, spec_for(big), 7)
    r_null = m.evaluate(null, spec_for(null), 7)
    assert r_big["mean_ic"] > 0.02 and r_big["p_one_sided_raw"] < 0.01
    assert r_null["p_one_sided_raw"] > 0.01 and abs(r_null["t_hac"]) < 3
    assert (
        r_big["horizon_days"] == 7
        and r_big["hac_lag"] == 14
        and m.evaluate(big, spec_for(big), 28)["hac_lag"] == 56
    )
    assert 0.8 <= r_big["coverage"]["coverage_ratio"] <= 1.0 and set(r_big["subperiods"]) == {
        "P1",
        "P2",
    }
    assert spec["statistics"]["hac_lag_multiplier"] == 2


def test_evaluation_never_uses_returns_beyond_the_last_candle():
    p = panel(t_n=400, s_n=30, seed=4, kappa=3.0)
    s = spec_for(p)
    r = m.evaluate(p, s, 28)
    assert r["last_signal_index"] == len(p.dates) - 1 - (1 + 28)
    q = m.Panel(p.dates, p.symbols, p.open.copy(), p.close.copy(), p.member, p.epoch_start)
    q.open[-5:] *= (
        3.0  # perturbing the final candles must not change IC of signal days whose exit is earlier
    )
    r2 = m.evaluate(q, s, 7)
    assert r2["last_signal_index"] == len(p.dates) - 1 - 8


# ------------------------------------------------------------------ disguise check
def test_disguise_check_flags_a_momentum_or_reversal_signal_and_passes_an_unrelated_one():
    p = panel(t_n=300, s_n=40, seed=6)
    ref = m.reference_signals(p.close)
    cfg = SPEC["disguise"]
    assert set(ref) >= {
        "trailing_return_7d",
        "trailing_return_28d",
        "rsi14_cutler",
        "donchian20_position",
        "ema12_26_gap",
    }
    copy_of_28d = -ref["trailing_return_28d"]  # a "signal" that is just reversal
    res = m.disguise(copy_of_28d, p.close, p.member, 40, 10, cfg["bound"])
    assert res["passes"] is False and res["max_abs_mean_rank_corr_gating"] > 0.99
    rng = np.random.default_rng(1)
    res2 = m.disguise(rng.normal(size=p.close.shape), p.close, p.member, 40, 10, cfg["bound"])
    assert res2["passes"] is True
    real = m.max3(p.close, p.epoch_start, W, 3)
    assert (
        m.disguise(real, p.close, p.member, 40, 10, cfg["bound"])["max_abs_mean_rank_corr_gating"]
        < 1.0
    )


# ------------------------------------------------------------------ decision logic
def fake(h, mean, p, sub=(0.01, 0.01), n_days=1500, assets=40.0, cov=0.95):
    return {"horizon_days": h, "mean_ic": mean, "p_one_sided_raw": p, "n_days": n_days,
            "subperiods": {"P1": {"mean_ic": sub[0]}, "P2": {"mean_ic": sub[1]}},
            "cross_section": {"mean_assets_per_valid_day": assets}, "coverage": {"coverage_ratio": cov}}  # fmt: skip


def test_decision_requires_every_criterion_and_reports_both_configurations():
    ok = {"passes": True}
    thr7 = SPEC["criteria"]["practical_threshold_per_day_ic"] * math.sqrt(7)
    good = m.decide(
        SPEC, {"H1-h7": fake(7, thr7 * 2, 0.001), "H1-h28": fake(28, 0.0, 0.5)}, ok, True
    )
    assert good["L1_PASS"] is True and set(good["configurations"]) == {"H1-h7", "H1-h28"}
    assert good["configurations"]["H1-h7"]["p_holm"] == pytest.approx(0.002)
    base = {"H1-h7": fake(7, thr7 * 2, 0.001), "H1-h28": fake(28, 0.0, 0.5)}
    cases = {
        "holm": {
            "H1-h7": fake(7, thr7 * 2, 0.04),
            "H1-h28": fake(28, 0.0, 0.5),
        },  # raw 0.04 -> Holm 0.08
        "practical": {"H1-h7": fake(7, thr7 * 0.5, 0.001), "H1-h28": fake(28, 0.0, 0.5)},
        "subperiod": {
            "H1-h7": fake(7, thr7 * 2, 0.001, sub=(0.02, -0.001)),
            "H1-h28": fake(28, 0.0, 0.5),
        },
        "sample": {"H1-h7": fake(7, thr7 * 2, 0.001, n_days=500), "H1-h28": fake(28, 0.0, 0.5)},
        "coverage": {"H1-h7": fake(7, thr7 * 2, 0.001, cov=0.5), "H1-h28": fake(28, 0.0, 0.5)},
    }
    for name, res in cases.items():
        out = m.decide(SPEC, res, ok, True)
        assert out["L1_PASS"] is False and out["decision"].startswith("NO-GO"), name
    assert m.decide(SPEC, base, {"passes": False}, True)["L1_PASS"] is False  # disguise terminates
    assert (
        m.decide(SPEC, base, ok, False)["L1_PASS"] is False
    )  # causality / reproducibility failure terminates


# ------------------------------------------------------------------ loader adapter (fake archive, no network)
def test_panel_adapter_reads_only_through_the_verified_loader_and_refuses_the_holdout(tmp_path):
    out, store, freeze = build(tmp_path, "base")
    ds = pl.PitDataset.open(out, store, freeze)
    s = json.loads(json.dumps(SPEC))
    s["evaluation"].update(
        panel_first_candle_open="2020-10-01",
        first_signal_date="2020-12-01",
        last_candle_open="2021-01-20",
    )
    s["evaluation"]["regime"]["reference_symbol"] = "AAAUSDT"
    s["universe"].update(threshold="1M")
    p = m.load_panel(ds, s)
    assert p.symbols == ["AAAUSDT", "BBBUSDT"] and p.close.shape == (
        len(p.dates),
        2,
    )  # leveraged token excluded
    assert p.member[p.dates.get_loc(pd.Timestamp("2020-12-05", tz="UTC")), 0]
    assert not p.member[
        p.dates.get_loc(pd.Timestamp("2021-01-05", tz="UTC")), 1
    ]  # BBB stopped printing: stale, not a member
    assert np.isnan(p.close[p.dates.get_loc(pd.Timestamp("2021-01-10", tz="UTC")), 1])
    assert (p.epoch_start[:, 0] == 0).all() and p.close[0, 0] == pytest.approx(1.0)
    s["evaluation"]["last_candle_open"] = "2025-06-30"  # as_of would be the holdout cutoff
    with pytest.raises(pl.HoldoutError):
        m.load_panel(ds, s)


def test_registered_spec_is_internally_consistent():
    assert (
        SPEC["signal"]["window_days"] == 28
        and SPEC["signal"]["top_k"] == 3
        and SPEC["horizons_days"] == [7, 28]
    )
    assert [c["id"] for c in SPEC["configurations"]] == ["H1-h7", "H1-h28"] and len(
        SPEC["configurations"]
    ) == 2
    assert (
        SPEC["statistics"]["hac_lag_multiplier"] == 2 and SPEC["criteria"]["alpha_family"] == 0.05
    )
    assert pd.Timestamp(SPEC["evaluation"]["last_candle_open"]) < pd.Timestamp(
        "2025-06-30"
    )  # strictly before the holdout
    assert SPEC["criteria"]["practical_threshold_per_day_ic"] == pytest.approx(0.003522504892367907)
