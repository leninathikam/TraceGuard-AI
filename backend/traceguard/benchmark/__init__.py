"""Evaluation runner comparing rules-only, Nemotron-only and hybrid diagnosis.

Run from backend/:  python -m traceguard.benchmark --modes rules,model,hybrid
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..detectors import primary_finding, run_detectors
from ..diagnosis import ModelDiagnosisInvalid, diagnose_rules, diagnose_with_model
from ..nebius import NebiusClient, NebiusError
from ..sandbox import run_scenario
from ..scenarios import SCENARIOS
from ..schema import Diagnosis, utcnow
from ..verify import verify_repair
from .cases import CASES, Case


def _prf(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": p, "recall": r, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def _diagnose_case(case: Case, mode: str, client: NebiusClient) -> dict[str, Any]:
    trace = case.trace.model_copy(deep=True)
    trace.id = f"bench_{case.id}"
    start = time.perf_counter()
    if mode == "rules":
        findings = run_detectors(trace)
        primary = primary_finding(findings)
        return {"case": case.id, "predicted": primary.category.value if primary else "none",
                "predicted_set": sorted({f.category.value for f in findings}),
                "latency_ms": (time.perf_counter() - start) * 1000, "ok": True}
    try:
        d, _ = diagnose_with_model(trace, mode, client)
        info = d.model_call
        return {"case": case.id, "predicted": d.category.value, "ok": True,
                "latency_ms": info.latency_ms, "tokens": info.prompt_tokens + info.completion_tokens,
                "cost_usd": info.cost_usd, "attempts": info.attempts, "info": info,
                "hypothesis": d.root_cause_hypothesis}
    except ModelDiagnosisInvalid as exc:
        return {"case": case.id, "predicted": "invalid_output", "ok": False, "error": str(exc),
                "info": exc.info, "latency_ms": exc.info.latency_ms,
                "tokens": exc.info.prompt_tokens + exc.info.completion_tokens, "cost_usd": exc.info.cost_usd}
    except NebiusError as exc:
        return {"case": case.id, "predicted": "error", "ok": False, "error": str(exc), "latency_ms": None}


def _score(cases: list[Case], results: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    by_id = {r["case"]: r for r in results}
    tp = fp = fn = tn = 0
    correct = 0
    per_kind: dict[str, list[int]] = {}
    rows = []
    for case in cases:
        r = by_id[case.id]
        pred = r["predicted"]
        truth_fail = bool(case.expected)
        pred_fail = pred not in ("none",)
        if r["ok"]:
            tp += truth_fail and pred_fail
            fp += (not truth_fail) and pred_fail
            fn += truth_fail and not pred_fail
            tn += (not truth_fail) and not pred_fail
        else:
            fn += truth_fail
        hit = pred == case.primary
        correct += hit
        per_kind.setdefault(case.kind, []).append(int(hit))
        rows.append({"case": case.id, "kind": case.kind, "expected": case.primary, "predicted": pred,
                     "correct": hit, "ok": r["ok"], "error": r.get("error"),
                     "latency_ms": r.get("latency_ms"), "tokens": r.get("tokens"),
                     "hypothesis": r.get("hypothesis")})

    out: dict[str, Any] = {
        "mode": mode,
        "cases": len(cases),
        "failure_detection": _prf(tp, fp, fn) | {"tn": tn},
        "root_cause_accuracy": correct / len(cases),
        "accuracy_by_kind": {k: sum(v) / len(v) for k, v in per_kind.items()},
        "invalid_or_failed_outputs": sum(not r["ok"] for r in results),
        "rows": rows,
    }
    lat = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    out["latency_ms_median"] = statistics.median(lat) if lat else None
    if mode != "rules":
        toks = [r["tokens"] for r in results if r.get("tokens")]
        costs = [r["cost_usd"] for r in results if r.get("cost_usd") is not None]
        out["tokens_per_diagnosis_mean"] = statistics.mean(toks) if toks else None
        out["cost_usd_per_diagnosis_mean"] = statistics.mean(costs) if costs else None
        out["cost_usd_total"] = sum(costs)
    else:
        tp_c = fp_c = fn_c = 0
        for case in cases:
            pred_set = set(by_id[case.id]["predicted_set"])
            tp_c += len(pred_set & case.expected)
            fp_c += len(pred_set - case.expected)
            fn_c += len(case.expected - pred_set)
        out["category_detection_multilabel"] = _prf(tp_c, fp_c, fn_c)
    return out


def _repair_eval(mode: str, client: NebiusClient) -> dict[str, Any]:
    rows = []
    for sid, scenario in SCENARIOS.items():
        baseline = run_scenario(scenario)
        trace = baseline.trace
        trace.id = f"bench_{sid}"
        row: dict[str, Any] = {"scenario": sid}
        try:
            if mode == "rules":
                d: Diagnosis = diagnose_rules(trace)
            else:
                d, _ = diagnose_with_model(trace, mode, client)
                row["cost_usd"] = d.model_call.cost_usd
                row["latency_ms"] = d.model_call.latency_ms
        except NebiusError as exc:
            rows.append(row | {"proposal_valid": False, "status": "model_error", "error": str(exc)})
            continue
        d.id = f"bench_dx_{sid}"
        v = verify_repair(d, trace, baseline=baseline)
        rows.append(row | {
            "category": d.category.value,
            "proposal_valid": v.status in ("validated", "failed"),
            "status": v.status,
            "reason": v.reason,
            "fixed": len(v.fixed_checks),
            "regressions": len(v.regressions),
            "diff": v.diff,
        })
    n = len(rows)
    return {
        "mode": mode,
        "scenarios": n,
        "proposal_validity_rate": sum(r["proposal_valid"] for r in rows) / n,
        "verified_repair_rate": sum(r["status"] == "validated" for r in rows) / n,
        "regression_rate": sum(1 for r in rows if r.get("regressions")) / n,
        "rows": rows,
    }


def run_evaluation(modes: list[str], client: NebiusClient | None = None, include_repairs: bool = True,
                   workers: int = 4) -> dict[str, Any]:
    client = client or NebiusClient()
    result: dict[str, Any] = {"created_at": utcnow(), "model": client.model, "diagnosis": {},
                              "repairs": {}, "skipped": {}, "_llm_calls": []}
    for mode in modes:
        if mode != "rules" and not client.configured:
            result["skipped"][mode] = "NEBIUS_API_KEY not set; model modes were not run."
            continue
        with ThreadPoolExecutor(max_workers=1 if mode == "rules" else workers) as pool:
            results = list(pool.map(lambda c: _diagnose_case(c, mode, client), CASES))
        for r in results:
            if "info" in r:
                result["_llm_calls"].append({"info": r.pop("info"), "model": client.model, "ok": r["ok"],
                                             "error": r.get("error")})
        result["diagnosis"][mode] = _score(CASES, results, mode)
        if include_repairs:
            result["repairs"][mode] = _repair_eval(mode, client)
    return result


def main() -> None:
    from ..env import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", default="rules,model,hybrid")
    parser.add_argument("--no-repairs", action="store_true")
    parser.add_argument("--out", default="../results/evaluation.json")
    args = parser.parse_args()
    result = run_evaluation(args.modes.split(","), include_repairs=not args.no_repairs)
    result.pop("_llm_calls")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    for mode, s in result["diagnosis"].items():
        det = s["failure_detection"]
        print(f"[{mode}] root-cause acc={s['root_cause_accuracy']:.2f} "
              f"detect P={det['precision']} R={det['recall']} by_kind={s['accuracy_by_kind']}")
    for mode, s in result["repairs"].items():
        print(f"[{mode}] repairs valid={s['proposal_validity_rate']:.2f} "
              f"verified={s['verified_repair_rate']:.2f} regressions={s['regression_rate']:.2f}")
    for mode, why in result["skipped"].items():
        print(f"[{mode}] SKIPPED: {why}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
