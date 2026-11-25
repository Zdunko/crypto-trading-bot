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
    assert conf["total_distinct"] == conf["phase3"]["subtotal"] + conf["phase4"]["subtotal"] == 40
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
