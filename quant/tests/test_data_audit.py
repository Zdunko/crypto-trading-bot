"""Synthetic tests of the S3 audit primitives: every defect class, look-ahead, holdout guard, gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantlab import data_audit as da


DAY = 86_400_000
HOUR = 3_600_000
LO, HI = da.month_bounds_ms("2022-03")


def rows_1d(n=31, mult=1, start=LO, price=100.0, vol=10.0):
    out = []
    for i in range(n):
        t = (start + i * DAY) * mult
        out.append(
            [
                str(t),
                str(price),
                str(price * 1.1),
                str(price * 0.9),
                str(price),
                str(vol),
                str(t + 1),
                str(vol * price),
                "5",
                "0",
                "0",
                "0",
            ]
        )
    return out


def kinds(rep):
    return set(rep.findings)


def test_clean_file():
    r = da.check_candles(rows_1d(), "1d", "2022-03")
    assert (
        r.findings == {} and not r.quarantined and r.missing_candles == 0 and r.expected_rows == 31
    )


def test_microsecond_timestamps_normalised_and_accepted():
    r = da.check_candles(rows_1d(mult=1000), "1d", "2022-03")
    assert not r.quarantined and r.ts_digits == 16
    assert da.to_ms(1_646_092_800_000_000) == 1_646_092_800_000
    with pytest.raises(ValueError):
        da.to_ms(12345)


def test_gap_is_warning_not_fatal():
    rs = rows_1d()
    del rs[5:8]
    r = da.check_candles(rs, "1d", "2022-03")
    assert r.missing_candles == 3 and "gap" in kinds(r) and not r.quarantined


def test_duplicate_out_of_order_misaligned_outside():
    rs = rows_1d()
    assert "duplicate_timestamp" in kinds(da.check_candles(rs + [rs[3]], "1d", "2022-03"))
    sw = rows_1d()
    sw[4], sw[5] = sw[5], sw[4]
    assert "out_of_order" in kinds(da.check_candles(sw, "1d", "2022-03"))
    shifted = rows_1d()
    shifted[2][0] = str(int(shifted[2][0]) + 1)
    assert "misaligned_timestamp" in kinds(da.check_candles(shifted, "1d", "2022-03"))
    out = rows_1d(start=LO + 10 * DAY)
    assert "outside_month" in kinds(da.check_candles(out, "1d", "2022-03"))


def test_repeated_block_named_distinctly():
    rs = rows_1d()
    r = da.check_candles(rs * 4, "1d", "2022-03")
    assert "repeated_block" in kinds(r) and r.quarantined


def test_malformed_and_invalid_values():
    for mutate, kind in [
        (lambda r: r.__setitem__(1, "abc"), "malformed_row"),
        (lambda r: r.__setitem__(1, "nan"), "malformed_row"),
        (lambda r: r.__setitem__(1, "-1"), "nonpositive_price"),
        (lambda r: r.__setitem__(5, "-3"), "negative_volume"),
        (lambda r: r.__setitem__(2, "50"), "ohlc_inconsistent"),  # high below open/close
    ]:
        rs = rows_1d()
        mutate(rs[7])
        assert kind in kinds(da.check_candles(rs, "1d", "2022-03")), kind
    short = rows_1d()
    short[3] = short[3][:4]
    assert "malformed_row" in kinds(da.check_candles(short, "1d", "2022-03"))
    assert "empty" in kinds(da.check_candles([], "1d", "2022-03"))


def test_zero_volume_warning_only():
    rs = rows_1d()
    rs[2][5] = "0"
    r = da.check_candles(rs, "1d", "2022-03")
    assert "zero_volume" in kinds(r) and not r.quarantined


def test_hourly_expected_rows():
    r = da.check_candles([], "1h", "2022-03")
    assert r.expected_rows == 744
    r2 = da.check_candles(
        [[str(LO + i * HOUR), "1", "1", "1", "1", "1", "0", "1"] for i in range(744)],
        "1h",
        "2022-03",
    )
    assert not r2.quarantined and r2.missing_candles == 0


def test_pit_eligibility_has_no_lookahead():
    base = {LO + i * DAY: (100.0, 2e6) for i in range(-120, 0)}
    t = LO
    assert da.pit_eligible(base, t, 1e6)
    # mutating anything at or after t, or making future volume enormous/zero, changes nothing
    fut = dict(base)
    for i in range(60):
        fut[t + i * DAY] = (1.0, 0.0)
    assert da.pit_eligible(fut, t, 1e6) == da.pit_eligible(base, t, 1e6)
    # the day exactly at t is excluded (strict <)
    only_at_t = {t: (1.0, 1e12)}
    assert not da.pit_eligible(only_at_t, t, 1e6)
    # too little history, or median below threshold
    assert not da.pit_eligible({LO + i * DAY: (1.0, 5e6) for i in range(-30, 0)}, t, 1e6)
    assert not da.pit_eligible(base, t, 3e6)


def test_identity_flags():
    assert da.coverage_breaks(["2021-01", "2021-02", "2021-03"]) == []
    assert da.coverage_breaks(["2021-01", "2021-02", "2021-06"]) == [("2021-02", "2021-06")]
    assert da.coverage_breaks(["2021-01", "2021-03"]) == []  # one missing month is below the rule
    d = {LO + i * DAY: (100.0, 1.0) for i in range(5)}
    d[LO + 5 * DAY] = (0.5, 1.0)  # 200x down: redenomination/migration signature
    assert da.price_jumps(d)[0][1] == pytest.approx(0.005)
    assert da.identity_flags(["2021-01"], d)["flagged"]
    assert not da.identity_flags(["2021-01"], {LO: (1.0, 1.0), LO + DAY: (1.2, 1.0)})["flagged"]


def test_regime_label_and_wilson():
    assert da.regime_label([100, 140]) == "bull"
    assert da.regime_label([100, 75]) == "bear"
    assert da.regime_label([100, 110]) == "sideways"
    assert da.regime_label([100]) == "unknown"
    assert da.wilson_upper(0, 0) == 1.0
    assert da.wilson_upper(0, 400) < 0.01
    assert da.wilson_upper(40, 400) > 0.1


def test_holdout_guard():
    da.assert_dev_month("2025-06")
    for ym in ("2025-07", "2026-01"):
        with pytest.raises(ValueError):
            da.assert_dev_month(ym)


def test_fetch_guard_refuses_holdout():
    import importlib.util

    p = Path(__file__).resolve().parents[1] / "docs/phase4c/s3_scripts/fetch.py"
    spec = importlib.util.spec_from_file_location("s3_fetch", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.guard("2025-06")
    with pytest.raises(SystemExit):
        mod.guard("2025-07")
    assert all(m < "2025-07" for ms in mod.universe().values() for m in ms)


CRIT = json.loads(
    (Path(__file__).resolve().parents[1] / "docs/phase4c/s3_criteria.json").read_text(
        encoding="utf-8"
    )
)
GOOD = dict(
    L1_permitted=True,
    L2_note="n/a",
    checksum_share=1.0,
    daily_quarantine_share=0.0,
    hourly_wilson_upper=0.01,
    u1_min_eligible_1M=40,
    u2_share_ge30_5M=0.9,
    u3_min_eligible_1M_after_exclusions=35,
    s1_dead_retained_share=1.0,
    s2_dead_share_by_cohort={},
    r1_months_by_regime={"bull": 8, "bear": 8, "sideways": 8},
    p1_identical=True,
    c1_storage_gb=0.5,
    c1_download_hours=1.0,
    t1={},
    exclusions_required=False,
)


def test_gates_verdicts_and_each_gate_can_fail():
    assert da.evaluate_gates(CRIT, GOOD)["verdict"] == "GO"
    assert (
        da.evaluate_gates(CRIT, {**GOOD, "exclusions_required": True})["verdict"]
        == "CONDITIONAL_GO"
    )
    breaks = {
        "L1": ("L1_permitted", False),
        "I1": ("checksum_share", 0.99),
        "Q1": ("daily_quarantine_share", 0.05),
        "Q2": ("hourly_wilson_upper", 0.2),
        "U1": ("u1_min_eligible_1M", 29),
        "U2": ("u2_share_ge30_5M", 0.5),
        "U3": ("u3_min_eligible_1M_after_exclusions", 10),
        "S1": ("s1_dead_retained_share", 0.9),
        "R1": ("r1_months_by_regime", {"bull": 8, "bear": 2, "sideways": 8}),
        "P1": ("p1_identical", False),
        "C1": ("c1_storage_gb", 5.0),
    }
    for gate, (k, v) in breaks.items():
        r = da.evaluate_gates(CRIT, {**GOOD, k: v})
        assert r["verdict"] == "NO_GO" and gate in r["failed"], gate


def test_partial_month_is_not_a_gap():
    rs = rows_1d()[10:25]  # listed on day 11, delisted after day 25
    r = da.check_candles(rs, "1d", "2022-03")
    assert r.leading_missing == 10 and r.trailing_missing == 6
    assert r.missing_candles == 0 and "gap" not in kinds(r) and not r.quarantined
