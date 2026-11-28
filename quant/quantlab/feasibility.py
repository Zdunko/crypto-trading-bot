"""S6 feasibility gate: machine-readable pre-registration, deterministic and fail-closed.

A pre-registration is a JSON document (``protocol/preregistration_template.json``). :func:`gate` checks
it against the thresholds frozen in ``docs/phase4c/s6_criteria.json`` (never against thresholds taken from
the document) and returns GATE_PASS / GATE_FAIL with one entry per check. **A pass never authorises a
market evaluation**: ``authorizes_market_evaluation`` is always False; :func:`may_start_market_run` needs
the research budget and a separate owner approval record. Any malformed input or internal error is a
FAIL. Pure functions, no network, no market data.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from quantlab import budget as budget_mod
from quantlab.stats import min_detectable_sharpe


QUANT = Path(__file__).resolve().parents[1]
CRITERIA = QUANT / "docs/phase4c/s6_criteria.json"
REGISTRY = QUANT / "protocol/spec_registry.json"
APPROVALS = QUANT / "protocol/run_approvals.json"
TEMPLATE = QUANT / "protocol/preregistration_template.json"
SCHEMA = "prereg-v1"
HOLDOUT_ACK = (
    "S1_listing_keys_and_last_month",
    "S3_survivorship_reporting",
    "S4_post_cutoff_symbol_names",
    "S4_request_log_gap",
)
RANGE_KEYS = (
    "assets",
    "entries_per_asset_year",
    "active_day_share",
    "cluster_size",
    "rho",
    "serial_rho",
)
SECTIONS = {
    "schema": str,
    "family": dict,
    "economic": dict,
    "strategy": dict,
    "data": dict,
    "execution": dict,
    "risk": dict,
    "expected": dict,
    "hypotheses": list,
    "benchmarks": list,
    "budget": dict,
    "declarations": dict,
}
ALLOWED = {
    "family": {"id", "family_key", "title", "version"},
    "economic": {
        "hypothesis",
        "rationale",
        "counterparty",
        "expected_failure_modes",
        "falsifiable_prediction",
    },
    "strategy": {"configurations", "indicators", "decision_time", "signal_inputs"},
    "data": {"dataset_hash", "interval", "universe", "warmup_days", "evaluation"},
    "execution": {"engine", "fill", "costs", "max_participation", "min_notional"},
    "risk": {
        "layer",
        "config_sha256",
        "universe_guard",
        "spot_only",
        "leverage",
        "shorting",
        "averaging",
        "position_adjustment",
    },
    "expected": set(RANGE_KEYS),
    "budget": {"new_configurations"},
    "declarations": {
        "results_seen",
        "prior_looks",
        "holdout_access",
        "holdout_metadata_acknowledged",
        "gate_thresholds",
    },
}


def thresholds() -> dict:
    return json.loads(CRITERIA.read_text(encoding="utf-8"))["gate_thresholds"]


def canonical(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def spec_hash(doc: dict) -> str:
    """Hash of everything except the declarations (which describe the process, not the specification)."""
    return sha(canonical({k: v for k, v in doc.items() if k != "declarations"}))


def config_hash(family_key: str, cfg: dict) -> str:
    params = sorted((p["name"], p["value"]) for p in cfg["parameters"])
    return sha(canonical({"family_key": family_key, "parameters": params}))


class Fail(Exception):
    """A check failure with a human-readable reason."""


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _rng(d: dict, key: str) -> tuple[float, float]:
    r = d.get(key)
    if (
        not isinstance(r, dict)
        or set(r) != {"lo", "hi"}
        or not (_num(r["lo"]) and _num(r["hi"]))
        or r["lo"] > r["hi"]
    ):
        raise Fail(f"expected.{key} must be {{lo, hi}} with finite numbers and lo <= hi")
    return float(r["lo"]), float(r["hi"])


# ---------------------------------------------------------------------------- checks
def check_schema(doc: dict) -> None:
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise Fail(f"schema must be {SCHEMA}")
    extra = set(doc) - set(SECTIONS)
    if extra:
        raise Fail(f"unknown sections: {sorted(extra)}")
    for k, t in SECTIONS.items():
        if k not in doc or not isinstance(doc[k], t):
            raise Fail(f"missing or mistyped section: {k}")
    for k, allowed in ALLOWED.items():
        unknown = set(doc[k]) - allowed
        if unknown:
            raise Fail(f"unknown fields in {k}: {sorted(unknown)}")
        missing = allowed - set(doc[k]) - ({"gate_thresholds"} if k == "declarations" else set())
        if missing:
            raise Fail(f"missing fields in {k}: {sorted(missing)}")
    canonical(doc)  # NaN/inf or non-JSON values raise ValueError -> FAIL


def check_rationale(doc: dict) -> None:
    e = doc["economic"]
    for k in ("hypothesis", "rationale", "counterparty", "falsifiable_prediction"):
        v = e[k]
        if not isinstance(v, str) or len(v.strip()) < 40 or v.strip().upper().startswith("TODO"):
            raise Fail(
                f"economic.{k} must be a substantive statement (>= 40 characters, not a placeholder)"
            )
    fm = e["expected_failure_modes"]
    if (
        not isinstance(fm, list)
        or len([x for x in fm if isinstance(x, str) and len(x.strip()) >= 20]) < 2
    ):
        raise Fail("at least two expected failure modes (>= 20 characters each) are required")
    for k in ("id", "family_key", "title"):
        if not isinstance(doc["family"][k], str) or not doc["family"][k].strip():
            raise Fail(f"family.{k} is required")


def check_causality(doc: dict, th: dict) -> None:
    d, s = doc["data"], doc["strategy"]
    if d["dataset_hash"] != th["dataset_hash"]:
        raise Fail("dataset_hash differs from the frozen S4 dataset hash")
    if d["interval"] not in ("1d", "1h"):
        raise Fail("data.interval must be 1d or 1h")
    u = d["universe"]
    if not isinstance(u, dict) or set(u) != {"threshold", "max_stale_days"}:
        raise Fail("data.universe must have threshold and max_stale_days")
    if u["threshold"] not in th["universe"]["thresholds"] or not (
        isinstance(u["max_stale_days"], int)
        and 0 <= u["max_stale_days"] <= th["universe"]["max_stale_days"]
    ):
        raise Fail("universe threshold/staleness outside the frozen settings")
    inds = s["indicators"]
    if (
        not isinstance(inds, list)
        or not isinstance(s["signal_inputs"], list)
        or not s["signal_inputs"]
    ):
        raise Fail("indicators and signal_inputs must be declared")
    if s["decision_time"] not in ("daily_close_completed", "hourly_close_completed"):
        raise Fail("decision_time must use completed candles only")
    wmax: float = 0
    for i in inds:
        if not isinstance(i, dict) or set(i) != {"name", "window", "input", "interval"}:
            raise Fail("each indicator needs name, window, input, interval")
        if i["input"] != "completed_candles" or not (
            isinstance(i["window"], int) and i["window"] >= 1
        ):
            raise Fail(
                f"indicator {i.get('name')}: input must be completed_candles with an integer window"
            )
        wmax = max(wmax, i["window"] * (1 if i["interval"] == "1d" else 1 / 24))
    if not (isinstance(d["warmup_days"], int) and d["warmup_days"] >= wmax + 1):
        raise Fail(f"warmup_days must be >= largest window + 1 ({wmax + 1:g})")
    ev = d["evaluation"]
    lo, hi = date.fromisoformat(ev["start"]), date.fromisoformat(ev["end_exclusive"])
    b0, b1 = (date.fromisoformat(x) for x in th["evaluation_window_bounds"])
    if lo < b0 or hi > b1 or hi <= lo:
        raise Fail("evaluation window must lie inside the research bounds (never the holdout)")
    if (hi - lo).days / 365.25 < th["min_evaluation_years"]:
        raise Fail(f"evaluation window shorter than {th['min_evaluation_years']} years")


def check_execution(doc: dict, th: dict) -> None:
    x = doc["execution"]
    if x["engine"] != "quantlab.execution" or x["fill"] != "next_candle_open":
        raise Fail("engine must be quantlab.execution with fills at the next candle open")
    c = x["costs"]
    if (
        not isinstance(c, dict)
        or set(c) != {"fee", "slippage", "stress_multiple"}
        or not all(_num(v) for v in c.values())
    ):
        raise Fail("costs need fee, slippage, stress_multiple")
    m = th["min_costs"]
    if (
        c["fee"] < m["fee"]
        or c["slippage"] < m["slippage"]
        or c["stress_multiple"] < m["stress_multiple"]
    ):
        raise Fail("costs below the BASE scenario or no stress scenario")
    if not (_num(x["max_participation"]) and 0 < x["max_participation"] <= th["max_participation"]):
        raise Fail("max_participation must be in (0, 0.10]")
    if not (_num(x["min_notional"]) and x["min_notional"] >= th["min_notional"]):
        raise Fail("min_notional below the protocol minimum")


def check_risk(doc: dict, th: dict) -> None:
    r = doc["risk"]
    if r["layer"] != "risk_v2" or r["config_sha256"] != th["risk_config_sha256"]:
        raise Fail("risk layer must be the frozen S2 risk_v2 configuration (hash mismatch)")
    if r["universe_guard"] is not True or r["spot_only"] is not True:
        raise Fail("universe guard on and spot only are mandatory")
    if any(r[k] is not False for k in ("leverage", "shorting", "averaging", "position_adjustment")):
        raise Fail("no leverage, shorting, averaging or position adjustment")


def check_complexity(doc: dict, th: dict) -> None:
    cfgs = doc["strategy"]["configurations"]
    if not isinstance(cfgs, list) or not (1 <= len(cfgs) <= th["max_configurations"]):
        raise Fail(f"1..{th['max_configurations']} configurations required")
    if doc["budget"]["new_configurations"] != len(cfgs):
        raise Fail("budget.new_configurations must equal the number of configurations")
    ids = [c.get("id") for c in cfgs]
    if len(set(ids)) != len(ids) or sum(1 for c in cfgs if c.get("role") == "primary") != 1:
        raise Fail("unique configuration ids and exactly one primary configuration")
    for c in cfgs:
        if set(c) != {"id", "role", "description", "parameters"} or c["role"] not in (
            "primary",
            "descriptive",
        ):
            raise Fail(f"configuration {c.get('id')}: bad fields")
        free = 0
        for p in c["parameters"]:
            if set(p) != {"name", "value", "kind", "source"}:
                raise Fail(f"configuration {c['id']}: parameter needs name, value, kind, source")
            v = p["value"]
            if isinstance(v, (list, dict)) or not (isinstance(v, (str, bool)) or _num(v)):
                raise Fail(
                    f"parameter {p['name']}: a single fixed scalar is required (no ranges or search spaces)"
                )
            if p["kind"] not in ("free", "convention"):
                raise Fail(f"parameter {p['name']}: kind must be free or convention")
            if p["kind"] == "convention" and not (
                isinstance(p["source"], str) and len(p["source"].strip()) >= 10
            ):
                raise Fail(f"parameter {p['name']}: a convention needs a stated source")
            free += p["kind"] == "free"
        if free > th["max_free_parameters_per_configuration"]:
            raise Fail(f"configuration {c['id']}: {free} free parameters exceed the cap")


def power(doc: dict, th: dict) -> dict:
    """Seeded Monte Carlo over the declared ranges -> lower/upper quantiles (arithmetic, no market data)."""
    ex = doc["expected"]
    mc = th["monte_carlo"]
    rng = np.random.default_rng(mc["seed"])
    n = mc["draws"]
    ev = doc["data"]["evaluation"]
    years = (
        date.fromisoformat(ev["end_exclusive"]) - date.fromisoformat(ev["start"])
    ).days / 365.25

    def draw(k: str) -> np.ndarray:
        lo, hi = _rng(ex, k)
        return rng.uniform(lo, hi, n)

    assets, rate, share, cluster, rho, serial = (draw(k) for k in RANGE_KEYS)
    if (
        np.any(share <= 0)
        or np.any(share > 1)
        or np.any(serial < 0)
        or np.any(serial >= 1)
        or np.any(rho < 0)
        or np.any(rho > 1)
    ):
        raise Fail("share must be in (0,1], rho in [0,1], serial_rho in [0,1)")
    if np.any(cluster < 1) or np.any(assets < 1) or np.any(rate < 0):
        raise Fail("cluster_size >= 1, assets >= 1, entries_per_asset_year >= 0")
    raw = assets * rate * years
    eff = raw / (1 + (cluster - 1) * rho)  # Kish design effect for simultaneous, correlated entries
    n_active = years * 365 * share * (1 - serial) / (1 + serial)
    mde = np.array([min_detectable_sharpe(max(int(x), 2), 365) for x in n_active])
    lq, uq = mc["lower_quantile"], mc["upper_quantile"]
    return {
        "years": years,
        "raw_episodes_p05": float(np.quantile(raw, lq)),
        "effective_episodes_p05": float(np.quantile(eff, lq)),
        "mde_sharpe_p95": float(np.quantile(mde, uq)),
        "raw_episodes_median": float(np.median(raw)),
    }


def check_power(doc: dict, th: dict) -> dict:
    p = power(doc, th)
    if p["raw_episodes_p05"] < th["min_raw_episodes_p05"]:
        raise Fail(
            f"T1 not reachable: 5th percentile of raw episodes {p['raw_episodes_p05']:.1f} < {th['min_raw_episodes_p05']}"
        )
    if p["effective_episodes_p05"] < th["min_effective_episodes_p05"]:
        raise Fail(
            f"effective episodes (5th pct) {p['effective_episodes_p05']:.1f} < {th['min_effective_episodes_p05']}"
        )
    if p["mde_sharpe_p95"] > th["max_mde_annualised_sharpe_p95"]:
        raise Fail(
            f"minimum detectable Sharpe (95th pct) {p['mde_sharpe_p95']:.2f} > {th['max_mde_annualised_sharpe_p95']}"
        )
    return p


def check_budget(doc: dict, th: dict, budget: dict) -> None:
    v = budget_mod.violations(budget)
    if v:
        raise Fail("research budget already violated: " + "; ".join(v))
    caps, st = budget["caps"], budget["state"]
    k = doc["budget"]["new_configurations"]
    if len(st["further_families"]) + 1 > caps["max_further_families"]:
        raise Fail("further-family cap exhausted")
    if k > caps["max_configurations_per_family"] or st["total_n"] + k > caps["max_total_n"]:
        raise Fail("configuration or N cap would be exceeded")
    hy = doc["hypotheses"]
    if (
        not hy
        or len(hy) > k + 1
        or any(not (isinstance(h, dict) and set(h) == {"id", "statement"}) for h in hy)
    ):
        raise Fail("hypotheses: 1..(configurations+1) entries with id and statement")


def check_duplicates(doc: dict, th: dict, registry: dict) -> None:
    fam = doc["family"]
    if fam["family_key"] in set(th["rejected_family_keys_never_retested"]) | set(
        registry["rejected_family_keys"]
    ):
        raise Fail("this family key was rejected earlier and is never re-tested")
    seen_ids = {r["family_id"] for r in registry["registered"]}
    seen_titles = {r["title"].lower() for r in registry["registered"]}
    if fam["id"] in seen_ids or fam["title"].lower() in seen_titles:
        raise Fail("family id or title already registered")
    hashes = {h for r in registry["registered"] for h in r["config_hashes"]} | {
        h for r in registry["historical"] for h in r["config_hashes"]
    }
    sh = {r["spec_hash"] for r in registry["registered"]}
    for c in doc["strategy"]["configurations"]:
        if config_hash(fam["family_key"], c) in hashes:
            raise Fail(f"configuration {c['id']} duplicates an earlier experiment")
    if spec_hash(doc) in sh:
        raise Fail("identical specification already registered")


def check_retrospective(doc: dict, th: dict, frozen: dict | None) -> None:
    d = doc["declarations"]
    if d["results_seen"] is not False or d["prior_looks"] != 0:
        raise Fail(
            "a pre-registration must be written before any result is seen (results_seen false, prior_looks 0)"
        )
    gt = d.get("gate_thresholds")
    if gt is not None and gt != th:
        raise Fail(
            "gate thresholds in the document differ from the frozen thresholds (retrospective change)"
        )
    if frozen is not None:
        if frozen["spec_hash"] != spec_hash(doc):
            raise Fail("specification changed after it was frozen (spec hash mismatch)")
        if frozen["thresholds_sha256"] != sha(canonical(th)):
            raise Fail("frozen thresholds differ from the current thresholds")


def check_holdout(doc: dict) -> None:
    d = doc["declarations"]
    if d["holdout_access"] is not False:
        raise Fail("holdout_access must be false")
    ack = d["holdout_metadata_acknowledged"]
    if not isinstance(ack, list) or set(HOLDOUT_ACK) - set(ack):
        raise Fail(
            "known holdout metadata exposures must be acknowledged: " + ", ".join(HOLDOUT_ACK)
        )


def check_benchmarks(doc: dict, th: dict) -> None:
    b = doc["benchmarks"]
    missing = set(th["required_benchmarks"]) - set(b)
    if missing or len(set(b)) != len(b):
        raise Fail(f"benchmarks missing or duplicated: {sorted(missing)}")


# ---------------------------------------------------------------------------- gate
def _both(dup, bench, doc: dict, th: dict, registry: dict) -> None:
    dup(doc, th, registry)
    bench(doc, th)


def gate(
    doc: Any,
    budget: dict | None = None,
    registry: dict | None = None,
    frozen: dict | None = None,
) -> dict:
    """Deterministic, fail-closed evaluation. Never raises; never authorises a market run."""
    checks: dict[str, dict] = {}
    th: dict = {}
    try:
        th = thresholds()
        budget = (
            budget
            if budget is not None
            else json.loads(budget_mod.BUDGET.read_text(encoding="utf-8"))
        )
        registry = (
            registry if registry is not None else json.loads(REGISTRY.read_text(encoding="utf-8"))
        )
    except Exception as e:
        return _result(
            {"A1": {"pass": False, "reason": f"gate inputs unreadable: {e}"}}, None, None, {}
        )
    bud: dict = budget
    reg: dict = registry
    steps = [
        ("A1", lambda: check_schema(doc)),
        ("A2", lambda: check_rationale(doc)),
        ("A3", lambda: check_causality(doc, th)),
        ("A4", lambda: check_execution(doc, th)),
        ("A5", lambda: check_risk(doc, th)),
        ("A6", lambda: check_complexity(doc, th)),
        ("A7", lambda: check_power(doc, th)),
        ("A8", lambda: check_budget(doc, th, bud)),
        ("A9", lambda: _both(check_duplicates, check_benchmarks, doc, th, reg)),
        ("A10", lambda: check_retrospective(doc, th, frozen)),
        ("A11", lambda: check_holdout(doc)),
    ]
    schema_ok = True
    p: dict = {}
    for cid, fn in steps:
        if not schema_ok and cid != "A1":
            checks[cid] = {
                "pass": False,
                "reason": "skipped: the document does not satisfy the schema",
            }
            continue
        try:
            out = fn()
            checks[cid] = {"pass": True, "reason": "ok"}
            if cid == "A7" and isinstance(out, dict):
                p = out
        except Fail as e:
            checks[cid] = {"pass": False, "reason": str(e)}
        except Exception as e:
            checks[cid] = {"pass": False, "reason": f"{type(e).__name__}: {e}"}
        if cid == "A1" and not checks[cid]["pass"]:
            schema_ok = False
    sh = None
    try:
        sh = spec_hash(doc) if schema_ok else None
    except Exception:
        sh = None
    return _result(checks, sh, th, p)


def _result(checks: dict, sh: str | None, th: dict | None, p: dict) -> dict:
    ok = all(c["pass"] for c in checks.values()) and len(checks) == 11
    res = {
        "verdict": "GATE_PASS" if ok else "GATE_FAIL",
        "authorizes_market_evaluation": False,  # by construction, whatever the verdict
        "note": "a gate pass only makes the specification eligible to be PROPOSED for approval",
        "checks": checks,
        "failed": sorted(k for k, v in checks.items() if not v["pass"]),
        "spec_hash": sh,
        "thresholds_sha256": sha(canonical(th)) if th else None,
        "power": p,
    }
    res["result_hash"] = sha(canonical({k: v for k, v in res.items() if k != "result_hash"}))
    return res


def freeze_preregistration(doc: dict, result: dict) -> dict:
    """The record that makes later edits detectable (spec hash + thresholds hash)."""
    if result["verdict"] != "GATE_PASS":
        raise Fail("only a specification that passed the gate can be frozen")
    return {
        "family_id": doc["family"]["id"],
        "spec_hash": result["spec_hash"],
        "thresholds_sha256": result["thresholds_sha256"],
        "gate_result_hash": result["result_hash"],
        "authorizes_market_evaluation": False,
    }


def may_start_market_run(
    family_id: str, budget: dict, approvals: dict, frozen: dict | None
) -> tuple[bool, str]:
    """True only with: budget room, a registered preregistered family, a frozen passing spec AND an explicit
    owner approval for that exact spec hash."""
    ok, why = budget_mod.can_start_run(budget, family_id)
    if not ok:
        return False, why
    if frozen is None or frozen.get("family_id") != family_id:
        return False, "no frozen gate-passing pre-registration for this family"
    for a in approvals.get("approvals", []):
        if (
            a.get("family_id") == family_id
            and a.get("approved_by") == "owner"
            and a.get("spec_hash") == frozen["spec_hash"]
            and isinstance(a.get("text_sha256"), str)
            and len(a["text_sha256"]) == 64
        ):
            return True, "ok"
    return False, "no explicit owner approval for this exact specification"


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "check":
        try:
            doc = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"GATE_FAIL: unreadable input: {e}", file=sys.stderr)
            return 1
        r = gate(doc)
        print(json.dumps(r, indent=1, sort_keys=True))
        return 0 if r["verdict"] == "GATE_PASS" else 1
    print("usage: python -m quantlab.feasibility check PREREGISTRATION.json", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
