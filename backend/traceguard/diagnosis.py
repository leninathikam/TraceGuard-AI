"""Diagnosis service: rules-only, Nemotron-only, or hybrid (rules evidence + Nemotron reasoning)."""

from __future__ import annotations

import json
from typing import Any, Literal

from .detectors import primary_finding, run_detectors
from .nebius import Completion, NebiusClient, NebiusError, extract_json
from .sandbox import RepairRejected, apply_edits
from .scenarios import SCENARIOS
from .schema import (
    Diagnosis,
    FailureCategory,
    FileEdit,
    Finding,
    ModelCallInfo,
    RepairProposal,
    Trace,
)

Mode = Literal["rules", "model", "hybrid"]

_RULE_REPAIRS = {
    FailureCategory.invalid_tool_arguments: "Make the agent emit arguments that match the tool schema "
    "(names, types and formats); validate arguments against the schema before calling.",
    FailureCategory.hallucinated_tool: "Restrict tool selection to the declared tool list and reject "
    "unknown tool names before execution.",
    FailureCategory.tool_execution_exception: "Inspect the tool error and fix the input or the tool.",
    FailureCategory.api_dependency_failure: "Add retry with exponential backoff and a circuit breaker "
    "for the failing dependency; surface a degraded response.",
    FailureCategory.timeout: "Raise the timeout or reduce the work per call; add cancellation and retry.",
    FailureCategory.malformed_output: "Constrain output with a JSON schema / structured output mode and "
    "validate before downstream use.",
    FailureCategory.missing_context: "Resolve required context before the step runs, or ask the user.",
    FailureCategory.incorrect_routing: "Fix the routing rule for this intent.",
    FailureCategory.repeated_tool_calls: "Cache tool results within a run.",
    FailureCategory.broken_retry_logic: "Only retry retryable errors (429/5xx/timeouts) with backoff.",
    FailureCategory.prompt_injection: "Treat retrieved/tool content as data, not instructions; require "
    "approval for actions triggered after untrusted input.",
    FailureCategory.unsafe_action: "Require human approval for destructive tools.",
    FailureCategory.excessive_token_usage: "Trim context and cap per-step token budgets.",
    FailureCategory.unsupported_claim: "Only emit claims grounded in retrieved evidence; drop or cite "
    "unsupported claims.",
    FailureCategory.failing_test: "Fix the code under test so the failing assertions pass.",
}


def _verification_steps(category: FailureCategory) -> list[str]:
    steps = ["Apply the repair to an isolated copy of the agent workspace.",
             "Replay the original task in the sandbox and capture a new trace."]
    if category == FailureCategory.failing_test:
        steps.append("Run the visible and held-out test suites; all tests must pass.")
    else:
        steps.append("Run the scenario acceptance checks; every check must pass.")
    steps.append("Re-run the deterministic detectors on the new trace and confirm the original "
                 "finding is gone with no new findings (no regressions).")
    return steps


def diagnose_rules(trace: Trace, findings: list[Finding] | None = None) -> Diagnosis:
    findings = run_detectors(trace) if findings is None else findings
    primary = primary_finding(findings)
    if primary is None:
        return Diagnosis(
            trace_id=trace.id, mode="rules", category=FailureCategory.none, supporting_event_ids=[],
            root_cause_hypothesis="No deterministic detector fired on this trace.",
            confidence="low",
            confidence_rationale="Absence of rule hits does not prove the run was correct.",
            limitations="Rules only detect structural failures; semantic errors need model review.",
            repair=RepairProposal(summary="No repair proposed."),
            verification_procedure=[], findings_used=[],
        )
    symptoms = [f for f in findings if f.is_symptom_of == primary.category]
    hypothesis = f"{primary.title}. {primary.detail}"
    if symptoms:
        hypothesis += " Downstream symptoms: " + "; ".join(s.title for s in symptoms) + "."
    return Diagnosis(
        trace_id=trace.id, mode="rules", category=primary.category,
        supporting_event_ids=list(dict.fromkeys(i for f in [primary, *symptoms] for i in f.event_ids)),
        root_cause_hypothesis=hypothesis,
        confidence="medium",
        confidence_rationale=f"Detector '{primary.detector}' matched a structural pattern in the trace; "
        "the causal link to the failure is inferred from a fixed priority order.",
        limitations="Rules confirm the symptom exists but cannot explain why the agent produced it, "
        "and cannot author a concrete patch, so this repair cannot be replay-verified.",
        repair=RepairProposal(summary=_RULE_REPAIRS.get(primary.category, "Investigate manually.")),
        verification_procedure=_verification_steps(primary.category),
        findings_used=findings,
    )


def _truncate(value: Any, limit: int = 700) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"...[+{len(value) - limit} chars]"
    if isinstance(value, dict):
        return {k: _truncate(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v, limit) for v in value[:20]]
    return value


def _compact_events(trace: Trace) -> list[dict[str, Any]]:
    out = []
    for e in trace.events:
        item: dict[str, Any] = {"id": e.id, "kind": e.kind, "name": e.name, "status": e.status}
        for key in ("parent_id", "error"):
            if getattr(e, key):
                item[key] = getattr(e, key)
        if e.input:
            item["input"] = _truncate(e.input)
        if e.output:
            item["output"] = _truncate(e.output)
        attrs = {k: v for k, v in e.attributes.items() if k != "expected_schema"}
        if attrs:
            item["attributes"] = _truncate(attrs)
        out.append(item)
    return out


SYSTEM_PROMPT = """You are TraceGuard, a reliability engineer that debugs other AI agents.
You receive an execution trace of an agent run. Identify the single most likely ROOT CAUSE of the
failure (not a downstream symptom), cite the trace event IDs that support it, and propose the
smallest repair to the editable files that would make the task succeed without breaking anything else.

Rules:
- Only cite event IDs that exist in the trace.
- Your root cause is a hypothesis; it will be tested by replaying the agent with your repair.
- Edits use exact search/replace: "find" must be copied verbatim from the current file content and
  must occur exactly once. Use "find": "" only to replace a whole file.
- Only edit files listed under editable_files. Keep edits minimal. Do not special-case test inputs.
- Code repairs may not import os, sys, subprocess, socket, pathlib or call eval/exec/open.
- confidence is a coarse self-assessment (low/medium/high), not a probability.

Respond with ONE JSON object and nothing else, matching:
{
  "category": one of %CATEGORIES%,
  "supporting_event_ids": ["e001", ...],
  "root_cause_hypothesis": "what went wrong and why, 1-3 sentences",
  "confidence": "low" | "medium" | "high",
  "confidence_rationale": "why",
  "limitations": "what you could not determine from the trace",
  "repair": {"summary": "...", "edits": [{"path": "...", "find": "...", "replace": "..."}]},
  "verification_procedure": ["step", ...]
}"""


def build_messages(trace: Trace, findings: list[Finding] | None, files: dict[str, str]) -> list[dict[str, str]]:
    categories = json.dumps([c.value for c in FailureCategory])
    payload: dict[str, Any] = {
        "task": trace.task,
        "workflow": trace.workflow,
        "agent_description": trace.metadata.get("agent_description", ""),
        "final_status_reported_by_agent": trace.final_status,
        "tools": trace.metadata.get("tools", []),
        "events": _compact_events(trace),
        "editable_files": {p: c for p, c in files.items() if p in trace.metadata.get("editable_files", [])},
        "read_only_files": {p: c for p, c in files.items() if p not in trace.metadata.get("editable_files", [])},
    }
    if findings is not None:
        payload["deterministic_findings"] = [
            {"category": f.category.value, "event_ids": f.event_ids, "title": f.title,
             "detail": f.detail, "is_symptom_of": f.is_symptom_of.value if f.is_symptom_of else None}
            for f in findings
        ]
        payload["note"] = ("deterministic_findings come from rule-based detectors and are reliable "
                           "evidence of symptoms; decide which one is the root cause, and look for "
                           "semantic problems the rules cannot see.")
    return [
        {"role": "system", "content": SYSTEM_PROMPT.replace("%CATEGORIES%", categories)},
        {"role": "user", "content": json.dumps(payload, indent=1, default=str)},
    ]


def validate_model_output(trace: Trace, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    valid_ids = {e.id for e in trace.events}
    try:
        data["category"] = FailureCategory(data.get("category")).value
    except ValueError:
        errors.append(f"category {data.get('category')!r} is not one of the allowed values")
    ids = data.get("supporting_event_ids") or []
    unknown = [i for i in ids if i not in valid_ids]
    if unknown:
        errors.append(f"supporting_event_ids {unknown} do not exist in the trace")
    if not ids and data.get("category") != "none":
        errors.append("supporting_event_ids must not be empty")
    if data.get("confidence") not in ("low", "medium", "high"):
        errors.append("confidence must be low, medium or high")
    for key in ("root_cause_hypothesis", "confidence_rationale", "limitations"):
        if not isinstance(data.get(key), str) or not data.get(key):
            errors.append(f"{key} must be a non-empty string")
    repair = data.get("repair") or {}
    try:
        proposal = RepairProposal(**repair)
    except Exception as exc:
        errors.append(f"repair is malformed: {exc}")
        proposal = None
    if proposal and proposal.edits and trace.scenario in SCENARIOS:
        try:
            apply_edits(SCENARIOS[trace.scenario], proposal.edits)
        except RepairRejected as exc:
            errors.append(f"repair edit rejected: {exc}")
    if not isinstance(data.get("verification_procedure"), list):
        data["verification_procedure"] = []
    return data, errors


def scenario_files(trace: Trace) -> dict[str, str]:
    scenario = SCENARIOS.get(trace.scenario or "")
    return {p: scenario.read(p) for p in scenario.context_files} if scenario else {}


def diagnose_with_model(
    trace: Trace, mode: Mode, client: NebiusClient, findings: list[Finding] | None = None
) -> tuple[Diagnosis, list[Completion]]:
    if mode == "hybrid" and findings is None:
        findings = run_detectors(trace)
    messages = build_messages(trace, findings if mode == "hybrid" else None, scenario_files(trace))
    completions: list[Completion] = []
    all_errors: list[str] = []
    data: dict[str, Any] | None = None
    for _ in range(2):
        completion = client.chat(messages)
        completions.append(completion)
        try:
            parsed = extract_json(completion.content)
        except (ValueError, json.JSONDecodeError) as exc:
            errors = [f"response was not a JSON object: {exc}"]
        else:
            parsed, errors = validate_model_output(trace, parsed)
        if not errors:
            data = parsed
            break
        all_errors += errors
        messages = messages + [
            {"role": "assistant", "content": completion.content[:6000]},
            {"role": "user", "content": "Your response failed validation:\n- " + "\n- ".join(errors)
             + "\nReturn a corrected JSON object only."},
        ]

    info = ModelCallInfo(
        model=client.model,
        attempts=len(completions),
        prompt_tokens=sum(c.prompt_tokens for c in completions),
        completion_tokens=sum(c.completion_tokens for c in completions),
        cost_usd=round(sum(c.cost_usd for c in completions), 6),
        latency_ms=round(sum(c.latency_ms for c in completions), 1),
        validation_errors=all_errors,
    )
    if data is None:
        raise ModelDiagnosisInvalid(info, all_errors)
    return (
        Diagnosis(
            trace_id=trace.id, mode=mode, category=FailureCategory(data["category"]),
            supporting_event_ids=data["supporting_event_ids"],
            root_cause_hypothesis=data["root_cause_hypothesis"],
            confidence=data["confidence"],
            confidence_rationale=data["confidence_rationale"],
            limitations=data["limitations"],
            repair=RepairProposal(**data["repair"]),
            verification_procedure=data["verification_procedure"] or _verification_steps(
                FailureCategory(data["category"])),
            findings_used=findings or [],
            model_call=info,
        ),
        completions,
    )


class ModelDiagnosisInvalid(NebiusError):
    def __init__(self, info: ModelCallInfo, errors: list[str]):
        super().__init__("model output failed validation twice: " + "; ".join(errors))
        self.info = info


def diagnose(trace: Trace, mode: Mode, client: NebiusClient | None = None) -> Diagnosis:
    findings = run_detectors(trace)
    if mode == "rules":
        return diagnose_rules(trace, findings)
    client = client or NebiusClient()
    try:
        diagnosis, _ = diagnose_with_model(trace, mode, client, findings if mode == "hybrid" else None)
        return diagnosis
    except NebiusError as exc:
        if mode == "model":
            raise
        fallback = diagnose_rules(trace, findings)
        fallback.mode = "hybrid"
        fallback.fallback_reason = f"Nemotron diagnosis unavailable, fell back to rules: {exc}"
        if isinstance(exc, ModelDiagnosisInvalid):
            fallback.model_call = exc.info
        return fallback
