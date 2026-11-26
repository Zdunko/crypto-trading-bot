"""Experiment ledger arithmetic and the v4 freeze."""

import json

from quantlab import protocol as P


def test_ledger_totals_are_internally_consistent_and_tied_to_the_protocol():
    led = json.loads((P.QUANT_DIR / "protocol" / "experiment_ledger.json").read_text())
    proto = P.load_protocol()
    variants = sum(2 * len(v) for k, v in proto["robustness"].items() if k != "method")
    conf = led["configurations_evaluated_on_research_data"]
    assert conf["phase3"]["one_at_a_time_variants"] == variants == 22
    assert conf["phase3"]["subtotal"] == len(proto["strategies"]) + variants
    assert conf["phase4"]["subtotal"] == 2 + 12
    assert (
        conf["total_distinct"]
        == conf["phase3"]["subtotal"] + conf["phase4"]["subtotal"] + conf["family_a"]["subtotal"]
        == 43
    )
    runs = led["runs"]
    assert (
        sum(r["freqtrade_backtests"] for r in runs)
        == led["execution_totals"]["freqtrade_backtests_in_successful_runs"]
        == 136
    )
    assert sum(r["new_configurations"] for r in runs) == conf["total_distinct"]
    assert led["execution_totals"]["holdout_evaluations"] == 0
    assert (
        led["execution_totals"]["first_evaluations"]
        + led["execution_totals"]["repeats_of_identical_configurations"]
        == 136
    )


def test_v4_manifest_verifies_and_detects_changes(tmp_path):
    import shutil

    assert P.verify_manifest_v4() == []
    q = tmp_path / "quant"
    shutil.copytree(P.QUANT_DIR, q, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    p = q / "quantlab" / "execution.py"
    p.write_text(p.read_text() + "\n# tamper\n")
    assert any("execution.py" in e for e in P.verify_manifest_v4(q))


def test_v5_manifest_verifies_and_detects_a_changed_specification(tmp_path):
    import shutil

    assert P.verify_manifest_v5() == []
    q = tmp_path / "quant"
    shutil.copytree(P.QUANT_DIR, q, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    spec = q / "protocol" / "protocol_v5_family_a.json"
    spec.write_text(spec.read_text().replace('"sigma_target": 0.4', '"sigma_target": 0.5'))
    assert any("protocol_v5_family_a.json" in e for e in P.verify_manifest_v5(q))


def _copy(tmp_path):
    import shutil

    q = tmp_path / "quant"
    shutil.copytree(P.QUANT_DIR, q, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return q


def test_amendment_a1_is_a_complete_auditable_chain_and_originals_are_preserved():
    a = json.loads(
        (P.QUANT_DIR / "protocol" / "amendments" / "A1_liquidity_volume.json").read_text()
    )
    assert a["id"] == "A1" and a["owner_approval"] and a["reason"] and a["tests_added"]
    for name, h in a["preserves"].items():  # the original manifests are untouched byte for byte
        assert P._norm_hash(P.QUANT_DIR / "protocol" / name) == h
    originals = {**json.loads((P.QUANT_DIR / "protocol/frozen_manifest_v4.json").read_text())["files"],
                 **json.loads((P.QUANT_DIR / "protocol/frozen_manifest_v5.json").read_text())["files"]}  # fmt: skip
    final = {}
    for am in P.load_amendments():  # the last amendment of a file defines its current hash
        for ch in am["changes"]:
            final[ch["file"]] = ch["to"]
    for ch in a["changes"]:
        assert ch["from"] == originals[ch["file"]]
        assert final[ch["file"]] == P._norm_hash(P.QUANT_DIR / ch["file"])
    changed = {f for f, h in originals.items() if P._norm_hash(P.QUANT_DIR / f) != h}
    listed = {c["file"] for am in P.load_amendments() for c in am["changes"]}
    assert changed == listed  # no file changed without being listed in an amendment
    assert P.verify_all() == []


def test_changing_an_amended_file_again_or_editing_an_original_manifest_is_detected(tmp_path):
    q = _copy(tmp_path)
    ex = q / "quantlab" / "execution.py"
    ex.write_text(ex.read_text() + "\n# later edit\n")
    assert any("execution.py" in e for e in P.verify_manifest_v5(q))
    q2 = _copy(tmp_path / "second")
    m = q2 / "protocol" / "frozen_manifest_v5.json"
    m.write_text(m.read_text().replace("\n", "\n "))
    assert any(
        "original frozen_manifest_v5.json was modified" in e for e in P.verify_manifest_v5(q2)
    )


def test_amendment_chain_break_is_reported(tmp_path):
    q = _copy(tmp_path)
    f = q / "protocol" / "amendments" / "A1_liquidity_volume.json"
    a = json.loads(f.read_text())
    a["changes"][0]["from"] = "0" * 64
    f.write_text(json.dumps(a))
    assert any("chain broken" in e for e in P.verify_manifest_v4(q))
