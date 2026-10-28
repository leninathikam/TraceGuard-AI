"""Verified Repair Loop: apply a proposed repair in isolation, replay, and compare."""

from __future__ import annotations

import difflib

from .detectors import run_detectors
from .sandbox import RepairRejected, apply_edits, run_scenario
from .scenarios import SCENARIOS
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
    scenario = SCENARIOS.get(trace.scenario or "")
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
    still_failing = [n for n, ok in after.items() if not ok and n not in regressions]
    remaining = run_detectors(repaired.trace) if repaired.trace else []

    if repaired.error:
        status, reason = "failed", f"Replay error: {repaired.error}"
    elif regressions:
        status, reason = "failed", f"Repair introduced {len(regressions)} regression(s)."
    elif not repaired.acceptance_passed:
        status, reason = "failed", f"{len(still_failing)} acceptance check(s) still failing after repair."
    elif remaining:
        status, reason = "failed", (f"Acceptance passed but {len(remaining)} detector finding(s) remain: "
                                    + "; ".join(f.title for f in remaining))
    else:
        status, reason = "validated", (f"All {len(after)} acceptance checks pass after replay "
                                       f"({len(fixed)} fixed, 0 regressions) and no detector findings remain.")
    return Verification(
        **base, status=status, reason=reason, diff=diff, baseline=baseline, repaired=repaired,
        fixed_checks=fixed, regressions=regressions, still_failing=still_failing,
        remaining_findings=remaining,
    )
