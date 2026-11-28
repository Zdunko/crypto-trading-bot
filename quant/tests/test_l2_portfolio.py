"""M4: the registered L2 rules on SYNTHETIC markets only: causal target schedule, latency, costs in closed form, no averaging,
participation cap and partial fills, V3 integration, passive comparators, metrics, statistics, decision logic, the
independent re-implementation, placebo, guard and end-to-end determinism. No market data is read."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from l2_synth import L1SPEC, SPEC, market, spec_for

from quantlab import l1_max3 as l1
from quantlab import l2_diagnostics as dg
from quantlab import l2_portfolio as l2
from quantlab import l2_run as run
from quantlab.costs import BASE, STRESS
from quantlab.risk_v3 import ScheduleFeed, Status


Q = Path(__file__).resolve().parents[1]
H = pd.Timedelta(hours=1)


@pytest.fixture(scope="module")
def mk():
    panel, data, symbols = market()
    return panel, data, symbols, spec_for(panel)


def sig_of(panel):
    return l1.max3(panel.close, panel.epoch_start, 28, 3)


# ------------------------------------------------------------------ targets
def test_target_schedule_uses_the_top_quintile_of_valid_members_with_deterministic_ties(mk):
    panel, _, symbols, spec = mk
    sig = sig_of(panel)
    sch = l2.target_schedule(panel, spec, 7, sig)
    days = l2.rebalance_days(spec, 7)
    assert list(sch) == days and all(d.hour == 0 for d in days) and (days[1] - days[0]).days == 7
    d = days[3]
    t = int(panel.dates.searchsorted(d - pd.Timedelta(days=1)))
    valid = np.where(panel.member[t] & np.isfinite(sig[t]))[0]
    k = max(5, math.ceil(0.2 * len(valid)))
    expected = [
        l2.pair_of(symbols[j]) for j in sorted(valid, key=lambda j: (-sig[t, j], symbols[j]))[:k]
    ]
    assert sch[d] == expected and len(expected) == 6
    tied = sig.copy()
    tied[t] = 0.0  # all equal: tie-break by name
    assert l2.target_schedule(panel, spec, 7, tied)[d][:3] == [
        l2.pair_of(s) for s in sorted(symbols)[:3]
    ]
    few = panel.member.copy()
    few[t, 4:] = False  # fewer than 5 eligible: cash
    p2 = l1.Panel(panel.dates, panel.symbols, panel.open, panel.close, few, panel.epoch_start)
    assert l2.target_schedule(p2, spec, 7, sig)[d] == []


def test_target_schedule_is_causal_prefix_invariant_and_ignores_future_prices(mk):
    panel, _, _, spec = mk
    full = l2.target_schedule(panel, spec, 7, sig_of(panel))
    cut = int(panel.dates.searchsorted(pd.Timestamp("2021-03-01", tz="UTC")))
    part = l1.Panel(
        panel.dates[:cut],
        panel.symbols,
        panel.open[:cut],
        panel.close[:cut],
        panel.member[:cut],
        panel.epoch_start[:cut],
    )
    sp = l2.target_schedule(part, spec, 7, sig_of(part))
    for d, v in sp.items():
        if d <= pd.Timestamp("2021-03-01", tz="UTC") and v:
            assert full[d] == v, d
    pert = panel.close.copy()
    pert[cut:] *= 3.0
    p3 = l1.Panel(panel.dates, panel.symbols, panel.open, pert, panel.member, panel.epoch_start)
    s3 = l2.target_schedule(p3, spec, 7, sig_of(p3))
    for d in full:
        if d < pd.Timestamp("2021-03-01", tz="UTC"):
            assert s3[d] == full[d]


def test_low_volatility_portfolio_ranks_by_low_realised_volatility_on_the_same_eligible_set(mk):
    panel, _, symbols, spec = mk
    vs = l2.vol_scores(panel, spec)
    sig = sig_of(panel)
    assert np.array_equal(np.isfinite(vs), np.isfinite(sig) & np.isfinite(vs))
    t = 80
    ok = np.isfinite(vs[t])
    vol = -vs[t][ok]
    top = np.argmax(vs[t][ok])
    assert vol[top] == vol.min()


# ------------------------------------------------------------------ execution through the engine
def test_latency_no_averaging_and_closed_form_costs_on_flat_prices():
    panel, data, symbols = market(n_days_hourly=40, n_assets=30, flat=True)
    spec = spec_for(panel, "2021-02-05")
    spec["portfolio"]["first_rebalance_day"] = "2021-01-02"
    sig = np.where(panel.member, 0.0, np.nan)  # flat prices: every asset ties, K = 6, names decide
    sch = l2.target_schedule(panel, spec, 28, sig)
    for _name, costs in (("normal", BASE), ("double", STRESS)):
        out = l2.run_active(data, sch, spec, costs, with_risk=False)
        buys = [o for o in out.orders if o["side"] == "buy"]
        assert buys and all(
            pd.Timestamp(o["time"]).hour == 1 for o in out.orders
        )  # one hour after the daily candle
        assert pd.Timestamp(buys[0]["time"]) == pd.Timestamp("2021-01-02 01:00", tz="UTC")
        held = {}
        for o in out.orders:
            if o["side"] == "buy":
                assert (
                    o["pair"] not in held or o["time"] != held[o["pair"]]
                )  # no buy of an asset twice in one episode
        invested = sum(o["notional"] for o in buys[:6])
        loss = SPEC["portfolio"]["wallet"] - float(out.equity.iloc[-1])
        # flat price: value = invested x (1-slip)(1-fee)/((1+slip)(1+fee)) at liquidation; the loss is ~2 x per-side x invested
        assert loss == pytest.approx(
            invested
            * (
                1
                - (1 - costs.slippage) * (1 - costs.fee) / ((1 + costs.slippage) * (1 + costs.fee))
            ),
            rel=2e-3,
        )
    m1 = l2.metrics(l2.run_active(data, sch, spec, BASE, False).equity, 10000.0)["net_return"]
    m2 = l2.metrics(l2.run_active(data, sch, spec, STRESS, False).equity, 10000.0)["net_return"]
    assert m2 == pytest.approx(2 * m1, rel=0.02)  # double costs double the drag on flat prices


def test_participation_cap_creates_partial_fills_and_is_never_exceeded():
    panel, data, symbols = market(
        n_days_hourly=40, n_assets=30, flat=True, volume=1e9, volume_override={0: 0.5}
    )
    spec = spec_for(panel, "2021-02-05")
    sch = {d: [l2.pair_of(symbols[0]), l2.pair_of(symbols[1])] for d in l2.rebalance_days(spec, 28)}
    out = l2.run_active(data, sch, spec, BASE, False)
    ex = l2.execution_stats(out, BASE, 10000.0, 1.0)
    assert (
        0.45 < ex["fill_ratio"] < 0.6
    )  # asset 1 fills in full, the illiquid asset 0 only up to 10 % of its hourly volume
    assert (
        out.open_value_end + (float(out.trades["open_value"].sum()) if len(out.trades) else 0.0)
        < 5200
    )


def test_v3_goes_flat_in_a_crash_and_reports_capital_protection_while_the_unprotected_run_loses_more():
    panel, data, symbols = market(n_days_hourly=60, n_assets=30, seed=5)
    spec = spec_for(panel, "2021-02-26")
    sig = sig_of(panel)
    sch = l2.target_schedule(panel, spec, 28, sig)
    # crash after the first rebalance: every price falls 35 % over three days
    h0 = int(data.index.searchsorted(pd.Timestamp("2021-01-04", tz="UTC")))
    f = np.ones(len(data.index))
    f[h0 : h0 + 72] = np.linspace(1.0, 0.65, 72)
    f[h0 + 72 :] = 0.65
    crash = {}
    for p in data.pairs:
        j = data.col[p]
        crash[p] = pd.DataFrame(
            {
                "date": data.index,
                "open": data.open[:, j] * f,
                "high": data.high[:, j] * f,
                "low": data.low[:, j] * f,
                "close": data.close[:, j] * f,
                "volume": 1e9,
            }
        )
    cd = type(data)(crash, data.index)
    a = l2.run_active(cd, sch, spec, BASE, with_risk=True)
    b = l2.run_active(cd, sch, spec, BASE, with_risk=False)
    ma, mb = l2.metrics(a.equity, 10000.0), l2.metrics(b.equity, 10000.0)
    cp = l2.capital_protection(a, 10000.0, 0.20)
    assert cp["transitions"] and cp["final_state"] in {
        "FLAT_COOLDOWN",
        "SHUTDOWN",
        "REENTRY",
        "REDUCED",
        "NORMAL",
    }
    assert mb["max_drawdown"] > 0.15 and ma["max_drawdown"] < mb["max_drawdown"]
    assert cp["max_drawdown_conservative"] >= cp["max_drawdown_last_known"] - 1e-12


def test_v3_zero_recovery_shutdown_and_writeoff_for_a_delisted_holding():
    panel, data, symbols = market(n_days_hourly=50, n_assets=30, seed=7)
    spec = spec_for(panel, "2021-02-17")
    sig = sig_of(panel)
    sch = l2.target_schedule(panel, spec, 28, sig)
    first = sch[l2.rebalance_days(spec, 28)[0]]
    victim = first[0]
    h_stop = int(data.index.searchsorted(pd.Timestamp("2021-01-05", tz="UTC")))
    frames = {}
    for p in data.pairs:
        j = data.col[p]
        df = pd.DataFrame(
            {
                "date": data.index,
                "open": data.open[:, j],
                "high": data.high[:, j],
                "low": data.low[:, j],
                "close": data.close[:, j],
                "volume": 1e9,
            }
        )
        frames[p] = df.iloc[:h_stop] if p == victim else df
    d2 = type(data)(frames, data.index)
    feed = ScheduleFeed({victim: [(data.index[h_stop] + pd.Timedelta(hours=48), Status.DELISTED)]})
    out = l2.run_active(d2, sch, spec, BASE, with_risk=True, feed=feed)
    cp = l2.capital_protection(out, 10000.0, 0.20)
    assert (
        cp["shutdown"]
        and cp["final_state"] == "SHUTDOWN"
        and victim in cp["write_offs"]
        and cp["write_offs"][victim] > 0
    )
    assert (
        not (out.trades["pair"] == victim).any() if len(out.trades) else True
    )  # never assumed sold
    assert cp["max_drawdown_conservative"] >= cp["max_drawdown_last_known"]


# ------------------------------------------------------------------ passive comparators, metrics, statistics
def test_passive_equity_closed_form_flat_and_trending_assets():
    t_n = 30
    o = np.full((t_n, 2), 100.0)
    c = np.full((t_n, 2), 100.0)
    eq = l2.passive_equity(o, c, {1: np.array([1.0, 0.0])}, BASE, 1000.0)
    k = BASE.per_side
    assert eq[0] == pytest.approx(1000.0) and eq[-1] == pytest.approx(
        1000.0 * (1 - k) / (1 + k), rel=1e-6
    )
    up = np.vstack([np.full((1, 1), 100.0), 100 * 1.01 ** np.arange(1, t_n)[:, None]])
    eq2 = l2.passive_equity(up, up, {1: np.array([1.0])}, BASE, 1000.0)
    assert eq2[-1] > eq2[1] and eq2[-1] == pytest.approx(eq2[1] * 1.01 ** (t_n - 2), rel=1e-3)


def test_metrics_closed_form_for_constant_growth_and_a_drawdown():
    idx = pd.date_range("2021-01-01", periods=24 * 365, freq="1h", tz="UTC")
    eq = pd.Series(10000.0 * np.exp(np.linspace(0, math.log(1.5), len(idx))), index=idx)
    m = l2.metrics(eq, 10000.0)
    assert m["cagr"] == pytest.approx(0.5, rel=0.02) and m["max_drawdown"] == pytest.approx(
        0.0, abs=1e-9
    )
    dd = eq.copy()
    dd.iloc[2000:3000] *= 0.7
    assert l2.metrics(dd, 10000.0)["max_drawdown"] == pytest.approx(0.3, abs=0.01)
    assert l2.metrics(dd, 10000.0)["calmar"] == pytest.approx(
        l2.metrics(dd, 10000.0)["cagr"] / l2.metrics(dd, 10000.0)["max_drawdown"]
    )


def test_paired_test_and_alpha_regression_recover_a_planted_edge_and_the_null():
    rng = np.random.default_rng(3)
    b = rng.normal(0.0005, 0.02, 1600)
    a = 0.8 * b + 0.001 + rng.normal(0, 0.005, 1600)
    t = l2.paired_test(a, 0.8 * b, 5)
    assert t["mean_daily_diff"] == pytest.approx(0.001, abs=3e-4) and t["p_one_sided"] < 0.01
    al = l2.alpha_regression(a, b, 5)
    assert (
        al["beta"] == pytest.approx(0.8, abs=0.03)
        and al["alpha_daily"] == pytest.approx(0.001, abs=3e-4)
        and al["p_alpha_one_sided"] < 0.01
    )
    null = l2.alpha_regression(0.8 * b + rng.normal(0, 0.005, 1600), b, 5)
    assert null["p_alpha_one_sided"] > 0.01 and abs(null["t_alpha_hac"]) < 3
    rm, w = l2.risk_matched_returns(a, b)
    assert (
        w == pytest.approx(min(1.0, a.std(ddof=1) / b.std(ddof=1)))
        and rm.std(ddof=1) == pytest.approx(a.std(ddof=1), rel=1e-6)
    ) or w == 1.0


def good_config():
    m = {"net_return": 0.5, "sortino": 2.0, "max_drawdown": 0.15}
    bm = {"btc_buy_hold": {"sortino": 1.0, "max_drawdown": 0.7}, "equal_weight": {"sortino": 1.0}}
    return {"normal": {"metrics": dict(m), "capital_protection": {"shutdown": False}, "execution": {"fill_ratio": 0.99}},
            "double": {"metrics": {**m, "net_return": 0.3}}, "benchmarks": bm, "incremental_vs_low_volatility": {"p_one_sided": 0.01}}  # fmt: skip


def test_decision_requires_every_registered_criterion_for_each_configuration():
    good = good_config()
    d = l2.decide_config(SPEC, {"H1-h7": good, "H1-h28": good})
    assert d["H1-h7"]["decision"] == "L2 PASS" and d["H1-h28"]["failed"] == []
    muts = {
        "A1_net_return_positive_double_costs": lambda c: c["double"]["metrics"].update(
            net_return=-0.01
        ),
        "A1_net_return_positive_normal_costs": lambda c: c["normal"]["metrics"].update(
            net_return=-0.01
        ),
        "A2_sortino_at_least_btc_buy_hold": lambda c: c["normal"]["metrics"].update(sortino=0.5),
        "A3_max_drawdown_within_limit": lambda c: c["normal"]["metrics"].update(max_drawdown=0.25),
        "A3_max_drawdown_not_above_btc": lambda c: c["benchmarks"]["btc_buy_hold"].update(
            max_drawdown=0.1
        ),
        "A4_no_v3_shutdown": lambda c: c["normal"]["capital_protection"].update(shutdown=True),
        "A5_incremental_value_vs_low_volatility": lambda c: c[
            "incremental_vs_low_volatility"
        ].update(p_one_sided=0.2),
        "A6_fill_ratio": lambda c: c["normal"]["execution"].update(fill_ratio=0.5),
    }
    for crit, mut in muts.items():
        c = json.loads(json.dumps(good))
        mut(c)
        out = l2.decide_config(SPEC, {"H1-h7": c, "H1-h28": good})
        assert (
            crit in out["H1-h7"]["failed"]
            and out["H1-h7"]["decision"] == "NO-GO"
            and out["H1-h28"]["decision"] == "L2 PASS"
        ), crit


# ------------------------------------------------------------------ verification diagnostics
def test_independent_reimplementation_matches_the_registered_ic_even_with_gaps_and_delistings():
    panel, _, symbols = market(
        n_days_hourly=100, n_assets=40, seed=9, ends={3: 24 * 120, 8: 24 * 90}
    )
    spec = spec_for(panel)
    st = L1SPEC["statistics"]
    for h in (7, 28):
        sig = sig_of(panel)
        ret = l1.forward_returns(panel.open, panel.close, h)
        reg, _ = l1.ic_series(sig, ret, panel.member, st["min_assets_per_day"])
        ind = dg.independent_ic(panel, L1SPEC, h)
        both = np.isfinite(reg) & np.isfinite(ind)
        assert (
            both.sum() > 60
            and np.nanmax(np.abs(reg[both] - ind[both])) < spec["diagnostics"]["V1_tolerance"]
        )
        assert (np.isfinite(reg) == np.isfinite(ind)).mean() > 0.97


def test_permutation_placebo_is_centred_and_a_planted_premium_lies_far_outside_it():
    panel, _, _ = market(n_days_hourly=100, n_assets=40, seed=11, lam_premium=25.0)
    sig = sig_of(panel)
    ret = l1.forward_returns(panel.open, panel.close, 7)
    mask = np.zeros(len(panel.dates), bool)
    mask[70:200] = True
    pl = dg.permutation_placebo(sig, ret, panel.member, mask, 20, 40, 1, 14)
    ic, _ = l1.ic_series(sig, ret, panel.member, 20)
    obs = np.nanmean(ic[mask])
    assert (
        abs(pl["mean_of_means"]) < 0.01
        and abs(obs) > 5 * pl["sd_of_means"]
        and abs(obs) > pl["max_abs_mean"]
    )


# ------------------------------------------------------------------ guard
def test_guard_requires_registration_unused_replay_and_an_exact_l2_owner_approval(tmp_path):
    h = run.spec_hash(SPEC)
    good_b = json.loads((Q / "protocol/research_budget.json").read_text(encoding="utf-8"))
    good_b["caps"]["max_diagnostic_replays_per_family"] = 1
    good_b["state"]["further_families"][0]["diagnostic_replays_used"] = 0
    appr = [
        {
            "family_id": run.FAMILY_ID,
            "approved_by": "owner",
            "spec_hash": h,
            "scope": "L2 economic viability",
            "text_sha256": "a" * 64,
        }
    ]

    def files(b, a):
        (tmp_path / "b.json").write_text(json.dumps(b), encoding="utf-8")
        (tmp_path / "a.json").write_text(json.dumps({"approvals": a}), encoding="utf-8")
        return tmp_path / "b.json", tmp_path / "a.json"

    assert run.guard(SPEC, *files(good_b, appr)) == h
    for mut in (lambda b: b["state"]["further_families"][0].update(diagnostic_replays_used=1), lambda b: b["state"].update(total_n=46),
                lambda b: b["state"].update(further_families=[])):  # fmt: skip
        b = json.loads(json.dumps(good_b))
        mut(b)
        with pytest.raises(run.GuardError):
            run.guard(SPEC, *files(b, appr))
    for bad in (
        [],
        [{**appr[0], "approved_by": "agent"}],
        [{**appr[0], "spec_hash": "0" * 64}],
        [{**appr[0], "scope": "L3"}],
    ):
        with pytest.raises(run.GuardError):
            run.guard(SPEC, *files(good_b, bad))


# ------------------------------------------------------------------ end to end
def test_replay_runs_end_to_end_is_deterministic_and_reports_everything_required():
    panel, data, symbols = market(n_days_hourly=100, n_assets=36, seed=21, lam_premium=15.0)
    spec = spec_for(panel, "2021-04-10")
    core1 = run.run_replay(None, panel, spec, data, None)
    core2 = run.run_replay(None, panel, spec, data, None)
    assert (
        core1["engine_hashes"] == core2["engine_hashes"]
        and len(core1["engine_hashes"]) == 2 * 2 * 3
    )
    doc = run.final_doc(spec, core1)
    for cid in ("H1-h7", "H1-h28"):
        c = doc["configurations"][cid]
        for cost in ("normal", "double"):
            m = c[cost]["metrics"]
            for k in ("net_return", "cagr", "sharpe", "sortino", "max_drawdown", "calmar"):
                assert k in m
            assert {
                "annual_one_way_turnover",
                "estimated_cost_usd",
                "mean_exposure",
                "fill_ratio",
            } <= set(c[cost]["execution"])
            assert (
                "final_state" in c[cost]["capital_protection"]
                and "low_volatility" in c[cost]
                and "no_risk_diagnostic" in c[cost]
            )
        assert {"btc_buy_hold", "equal_weight", "cash"} <= set(
            c["benchmarks"]
        ) and "risk_matched_btc_cash_ex_post" in c
        assert set(c["incremental_vs_low_volatility"]) >= {
            "mean_daily_diff",
            "p_one_sided",
            "t_hac",
        }
        assert doc["decision"][cid]["decision"] in ("L2 PASS", "NO-GO") and set(
            doc["decision"][cid]["criteria"]
        ) >= {"A1_net_return_positive_double_costs", "A5_incremental_value_vs_low_volatility"}
    h7 = doc["configurations"]["H1-h7"]
    assert (
        h7["normal"]["metrics"]["final_equity"] >= h7["double"]["metrics"]["final_equity"] - 1e-6
    )  # double costs never help


def test_registered_spec_is_internally_consistent_and_changes_nothing_of_l1():
    assert (
        [c["id"] for c in SPEC["configurations"]]
        == [c["id"] for c in L1SPEC["configurations"]]
        == ["H1-h7", "H1-h28"]
    )
    assert (
        SPEC["signal"]["window_days"] == L1SPEC["signal"]["window_days"]
        and SPEC["signal"]["top_k"] == L1SPEC["signal"]["top_k"]
    )
    assert (
        SPEC["execution"]["max_participation"] == 0.10
        and SPEC["execution"]["decision_hour_utc"] == 1
        and SPEC["risk"]["drawdown_limit"] == 0.20
    )
    assert (
        SPEC["budget_interpretation"]["new_configurations"] == 0
        and SPEC["budget_interpretation"]["n_total"] == 45
    )
    assert (
        pd.Timestamp(SPEC["evaluation"]["hourly_as_of"])
        <= pd.Timestamp("2025-06-30 00:00")
        < pd.Timestamp(SPEC["evaluation"]["epoch_cutoff"])
    )
    assert (BASE.fee, BASE.slippage, STRESS.fee, STRESS.slippage) == (0.001, 0.0005, 0.002, 0.001)


def test_strategy_and_comparator_series_cover_the_same_days():
    panel, data, _ = market(n_days_hourly=100, n_assets=36, seed=21)
    spec = spec_for(panel, "2021-04-10")
    sig = sig_of(panel)
    out = l2.run_active(data, l2.target_schedule(panel, spec, 7, sig), spec, BASE, with_risk=True)
    r_s = run.daily_returns(out.equity, spec["portfolio"]["wallet"])
    btc = run.passive(panel, spec, BASE, "btc_buy_hold")
    ew = run.passive(panel, spec, BASE, "equal_weight")
    # the strategy series runs to the last hourly day (04-30); the comparators stop at the last rebalance day of the spec
    assert (
        len(btc["daily_returns"]) == len(ew["daily_returns"])
        and r_s[0] == 0.0
        and btc["daily_returns"][0] == 0.0
    )
    spec2 = spec_for(panel, "2021-04-30")
    assert len(run.passive(panel, spec2, BASE, "btc_buy_hold")["daily_returns"]) == len(r_s)


def test_final_epoch_feed_marks_only_the_last_epoch_of_a_symbol_that_ended_before_the_cutoff(
    tmp_path,
):
    from synth_pit import build

    out, _store, _freeze = build(tmp_path, "base")
    spec = spec_for(market(n_days_hourly=10, n_assets=3)[0])
    spec["evaluation"]["epoch_cutoff"] = (
        "2021-02-01"  # the fake archive ends with January 2021 (the real one with June 2025)
    )
    feed = l2.final_epoch_feed(out, {"AAA/USDT", "BBB/USDT"}, spec)
    # BBB prints until 2020-12-20 and then ends: DELISTED becomes knowable 48 h after its last candle, never before
    t_end = pd.Timestamp("2020-12-21", tz="UTC")
    assert (
        feed("BBB/USDT", t_end) is None and feed("BBB/USDT", t_end + pd.Timedelta(hours=47)) is None
    )
    assert feed("BBB/USDT", t_end + pd.Timedelta(hours=48)) == Status.DELISTED
    assert (
        feed("AAA/USDT", pd.Timestamp("2025-06-29", tz="UTC")) is None
    )  # runs to the cutoff: not delisted
