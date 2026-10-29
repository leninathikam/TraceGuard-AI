"""Verified Repair Loop: apply a proposed repair in isolation, replay, and compare."""

from __future__ import annotations

import difflib
import hashlib

from .detectors import run_detectors
from .sandbox import RepairRejected, apply_edits, run_scenario
from .scenarios import for_trace
from .schema import Diagnosis, SandboxRun, Trace, Verification


def unified_diff(changed: dict[str, tuple[str, str]]) -> str:
    chunks = []
    for path, (before, after) in changed.items():
        chunks.extend(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}",
        ))
    return "".join(chunks)


def verify_repair(diagnosis: Diagnosis, trace: Trace, baseline: SandboxRun | None = None) -> Verification:
    base = dict(diagnosis_id=diagnosis.id, trace_id=trace.id)
    scenario = for_trace(trace)
    if scenario is None:
        return Verification(**base, status="not_applicable",
                            reason="Imported trace has no replayable workspace; repair can only be reviewed.")
    if not diagnosis.repair.edits:
        return Verification(**base, status="not_applicable",
                            reason="Diagnosis proposes no concrete file edits, so there is nothing to replay.")
    try:
        changed = apply_edits(scenario, diagnosis.repair.edits)
    except RepairRejected as exc:
        return Verification(**base, status="rejected", reason=f"Repair failed safety/applicability checks: {exc}")

    diff = unified_diff(changed)
    baseline = baseline or run_scenario(scenario)
    repaired = run_scenario(scenario, diagnosis.repair.edits)

    before = {c.name: c.passed for c in baseline.checks}
    after = {c.name: c.passed for c in repaired.checks}
    fixed = [n for n, ok in after.items() if ok and before.get(n) is False]
    regressions = [n for n, ok in before.items() if ok and not after.get(n, False)]
    missing = sorted(set(before) - set(after))
    still_failing = [n for n, ok in after.items() if not ok and n not in regressions] + missing
    remaining = run_detectors(repaired.trace) if repaired.trace else []

    if not baseline.ok or baseline.error or not baseline.trace or not baseline.checks:
        status, reason = "failed", "Baseline could not be reproduced; repair evidence is inconclusive."
    elif len(before) != len(baseline.checks) or len(after) != len(repaired.checks):
        status, reason = "failed", "Duplicate acceptance check names make comparison ambiguous."
    elif baseline.acceptance_passed:
        status, reason = "not_applicable", "Baseline already passes acceptance; no failing check was repaired."
    elif not repaired.ok or repaired.error or not repaired.trace:
        status, reason = "failed", f"Replay error: {repaired.error}"
    elif missing:
        status, reason = "failed", f"Replay omitted acceptance checks: {', '.join(missing)}"
    elif regressions:
        status, reason = "failed", f"Repair introduced {len(regressions)} regression(s)."
    elif not repaired.acceptance_passed or not after or not all(after.values()):
        status, reason = "failed", f"{len(still_failing)} acceptance check(s) still failing after repair."
    elif remaining:
        status, reason = "failed", (f"Acceptance passed but {len(remaining)} detector finding(s) remain: "
                                    + "; ".join(f.title for f in remaining))
    elif not fixed:
        status, reason = "failed", "No baseline failure was fixed."
    else:
        status, reason = "validated", (f"All {len(after)} acceptance checks pass after replay "
                                       f"({len(fixed)} fixed, 0 regressions) and no detector findings remain.")
    interventions = []
    # Leave one edit out. Invalid dependent patches are inconclusive, never causal evidence.
    if status == "validated":
        for index in range(min(len(diagnosis.repair.edits), 8)):
            edits = diagnosis.repair.edits[:index] + diagnosis.repair.edits[index + 1:]
            try:
                ablated = run_scenario(scenario, edits)
                checks = {c.name: c.passed for c in ablated.checks}
                restored = [n for n in fixed if checks.get(n) is False]
                inconclusive = not ablated.ok or set(checks) != set(before)
                interventions.append({"omitted_edit": index, "path": diagnosis.repair.edits[index].path,
                                      "outcome": "inconclusive" if inconclusive else
                                      "failure_restored" if restored else "not_necessary_for_fixed_checks",
                                      "restored_failures": restored, "error": ablated.error})
            except RepairRejected as exc:
                interventions.append({"omitted_edit": index, "outcome": "inconclusive", "error": str(exc)})
    hashes = workspace_hashes(scenario)
    for p, (_, source) in changed.items():
        hashes[f"repaired:{p}"] = hashlib.sha256(source.encode()).hexdigest()
    return Verification(
        **base, status=status, reason=reason, diff=diff, baseline=baseline, repaired=repaired,
        fixed_checks=fixed, regressions=regressions, still_failing=still_failing,
        remaining_findings=remaining,
        intervention_tests=interventions, evidence_hashes=hashes,
        causal_scope="Controlled artifact replay and leave-one-edit-out tests (at most 8). "
        "Evidence concerns these checks and this captured artifact; it does not prove the model's "
        "explanation or generalize to new LLM samples.",
    )


def workspace_hashes(scenario) -> dict[str, str]:
    paths = sorted(p for p in scenario.path.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    result = {}
    for path in paths:
        name = path.relative_to(scenario.path).as_posix()
        content = scenario.read(name).encode() if name in scenario.captured_files else path.read_bytes()
        result[f"baseline:{name}"] = hashlib.sha256(content).hexdigest()
    from .scenarios import ROOT
    result["harness:_tracer.py"] = hashlib.sha256((ROOT / '_tracer.py').read_bytes()).hexdigest()
    return result
