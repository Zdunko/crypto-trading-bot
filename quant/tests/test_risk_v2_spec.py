"""Specification file, code defaults and freeze for the risk layer V2."""

import json
from dataclasses import asdict

from quantlab import protocol as P
from quantlab.risk_v2 import RiskV2Config


SPEC = json.loads((P.QUANT_DIR / "protocol" / "protocol_v6_risk_v2.json").read_text())


def test_code_defaults_equal_the_frozen_specification_and_are_marked_provisional():
    c = asdict(RiskV2Config())
    c["steps"] = list(c["steps"])
    assert SPEC["parameters"] == c and SPEC["provisional"] is True


def test_specification_states_the_non_guarantee_and_the_hwm_rule():
    d = SPEC["definitions"]
    assert "never reset" in d["H"] and "NOT guaranteed maximum losses" in d["note"]
    assert (
        "never cleared" in SPEC["safety_disqualified"]
        and "independent of T4" in SPEC["safety_disqualified"]
    )
    assert SPEC["one_transition_per_candle"] is True and len(SPEC["states"]) == 5


def test_v6_freeze_and_the_whole_amendment_chain_verify():
    assert P.verify_manifest_v6() == [] and P.verify_all() == []
    a4 = json.loads(
        (P.QUANT_DIR / "protocol" / "amendments" / "A4_causality_empty_trades.json").read_text()
    )
    assert a4["id"] == "A4" and a4["changes"][0]["file"] == "quantlab/causality.py"
