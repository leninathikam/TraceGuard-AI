"""Deterministic failure detectors.

Each detector inspects a reconstructed trace and returns structural findings with the
event IDs that support them. Detectors never guess intent; semantic judgements
(e.g. whether a route was wrong when no route table exists) are left to the model.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Callable, Iterable

from .jsonschema_lite import validate
from .schema import FailureCategory as C
from .schema import Finding, Trace, TraceEvent

Detector = Callable[[Trace], Iterable[Finding]]
_DETECTORS: list[Detector] = []


def detector(fn: Detector) -> Detector:
    _DETECTORS.append(fn)
    return fn


def _canonical(args: dict) -> str:
    return json.dumps(args, sort_keys=True, default=str)


def _result_for(trace: Trace, call: TraceEvent) -> TraceEvent | None:
    return next(
        (e for e in trace.events if e.kind == "tool_result" and e.parent_id == call.id), None
    )


def _text_of(event: TraceEvent) -> str:
    return json.dumps(event.output or {}, default=str)


@detector
def hallucinated_tools(trace: Trace) -> Iterable[Finding]:
    tools = trace.tools()
    if not tools:
        return
    for e in trace.events:
        if e.kind == "tool_call" and e.name not in tools:
            yield Finding(
                category=C.hallucinated_tool,
                severity="high",
                event_ids=[e.id],
                title=f"Call to undeclared tool '{e.name}'",
                detail=f"The agent called '{e.name}', which is not among the declared tools: "
                f"{sorted(tools)}.",
                detector="hallucinated_tools",
                evidence={"declared_tools": sorted(tools)},
            )


@detector
def invalid_tool_arguments(trace: Trace) -> Iterable[Finding]:
    tools = trace.tools()
    for e in trace.events:
        if e.kind != "tool_call" or e.name not in tools:
            continue
        errors = validate(e.input, tools[e.name].parameters or {"type": "object"})
        if errors:
            yield Finding(
                category=C.invalid_tool_arguments,
                severity="high",
                event_ids=[e.id],
                title=f"Arguments to '{e.name}' violate its schema",
                detail="; ".join(errors),
                detector="invalid_tool_arguments",
                evidence={"violations": errors, "arguments": e.input},
            )


_DEPENDENCY_ERR = re.compile(
    r"connection (refused|reset)|name or service not known|service unavailable|bad gateway"
    r"|upstream|dns|\b50[0234]\b",
    re.I,
)
_TIMEOUT_ERR = re.compile(r"timed? ?out|deadline exceeded|timeout", re.I)


def _is_dependency_failure(e: TraceEvent) -> bool:
    status = e.attributes.get("http_status")
    return (isinstance(status, int) and status >= 500) or bool(
        e.error and _DEPENDENCY_ERR.search(e.error)
    )


def _is_timeout(e: TraceEvent) -> bool:
    limit = e.attributes.get("timeout_ms")
    return bool(e.error and _TIMEOUT_ERR.search(e.error)) or (
        isinstance(limit, (int, float)) and e.duration_ms > limit
    )


@detector
def dependency_and_timeouts(trace: Trace) -> Iterable[Finding]:
    for e in trace.events:
        if e.status != "error" and not _is_timeout(e):
            continue
        if _is_timeout(e):
            yield Finding(
                category=C.timeout,
                severity="medium",
                event_ids=[e.id],
                title=f"'{e.name}' timed out",
                detail=e.error or f"Took {e.duration_ms:.0f} ms, limit {e.attributes.get('timeout_ms')} ms.",
                detector="dependency_and_timeouts",
            )
        elif _is_dependency_failure(e):
            yield Finding(
                category=C.api_dependency_failure,
                severity="high",
                event_ids=[e.id],
                title=f"External dependency failed during '{e.name}'",
                detail=e.error or f"HTTP {e.attributes.get('http_status')}",
                detector="dependency_and_timeouts",
                evidence={"http_status": e.attributes.get("http_status")},
            )


@detector
def tool_exceptions(trace: Trace) -> Iterable[Finding]:
    for e in trace.events:
        if e.kind == "tool_result" and e.status == "error":
            if _is_timeout(e) or _is_dependency_failure(e):
                continue
            yield Finding(
                category=C.tool_execution_exception,
                severity="high",
                event_ids=[e.id] + ([e.parent_id] if e.parent_id else []),
                title=f"Tool '{e.name}' raised an exception",
                detail=e.error or "Tool returned an error status.",
                detector="tool_exceptions",
            )


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return m.group(1) if m else text


@detector
def malformed_outputs(trace: Trace) -> Iterable[Finding]:
    for e in trace.events:
        schema = e.attributes.get("expected_schema")
        if not schema or not e.output:
            continue
        raw = e.output.get("text")
        if raw is None:
            continue
        try:
            parsed = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            errors = [f"not valid JSON: {exc.msg} at position {exc.pos}"]
        else:
            errors = validate(parsed, schema)
        if errors:
            yield Finding(
                category=C.malformed_output,
                severity="high",
                event_ids=[e.id],
                title=f"Output of '{e.name}' does not match the expected schema",
                detail="; ".join(errors),
                detector="malformed_outputs",
                evidence={"errors": errors, "raw": raw[:500]},
            )


_PLACEHOLDER = re.compile(r"\{\{\s*\w+\s*\}\}|<unknown>|\bUNKNOWN\b|\bTBD\b")


@detector
def missing_context(trace: Trace) -> Iterable[Finding]:
    for e in trace.events:
        required = e.attributes.get("required_context") or []
        ctx = e.input.get("context", {}) if isinstance(e.input.get("context"), dict) else {}
        missing = [k for k in required if ctx.get(k) in (None, "", [], {})]
        unresolved = _PLACEHOLDER.findall(json.dumps(e.input, default=str)) if e.kind in (
            "llm_call",
            "tool_call",
        ) else []
        if missing or unresolved:
            parts = []
            if missing:
                parts.append(f"required context missing: {missing}")
            if unresolved:
                parts.append(f"unresolved placeholders: {sorted(set(unresolved))}")
            yield Finding(
                category=C.missing_context,
                severity="medium",
                event_ids=[e.id],
                title=f"'{e.name}' ran without required context",
                detail="; ".join(parts),
                detector="missing_context",
                evidence={"missing": missing, "unresolved": sorted(set(unresolved))},
            )


@detector
def incorrect_routing(trace: Trace) -> Iterable[Finding]:
    for e in trace.events:
        routes = e.attributes.get("routes")
        intent = e.input.get("intent")
        chosen = (e.output or {}).get("route")
        if e.kind != "route" or not routes or not intent or not chosen:
            continue
        if intent not in routes.get(chosen, []):
            correct = [r for r, intents in routes.items() if intent in intents]
            yield Finding(
                category=C.incorrect_routing,
                severity="medium",
                event_ids=[e.id],
                title=f"Intent '{intent}' routed to '{chosen}'",
                detail=f"Route table maps '{intent}' to {correct or 'no route'}, not '{chosen}'.",
                detector="incorrect_routing",
                evidence={"expected_routes": correct},
            )


@detector
def repeated_and_retry(trace: Trace) -> Iterable[Finding]:
    calls: dict[str, list[TraceEvent]] = defaultdict(list)
    for e in trace.events:
        if e.kind == "tool_call":
            calls[f"{e.name}:{_canonical(e.input)}"].append(e)

    for group in calls.values():
        if len(group) < 2:
            continue
        results = [_result_for(trace, c) for c in group]
        errored = [r for r in results[:-1] if r is not None and r.status == "error"]
        name = group[0].name
        ids = [c.id for c in group]
        if errored:
            non_retryable = [
                r
                for r in errored
                if (
                    isinstance(r.attributes.get("http_status"), int)
                    and 400 <= r.attributes["http_status"] < 500
                    and r.attributes["http_status"] != 429
                )
                or r.attributes.get("retryable") is False
                or (r.error and re.search(r"validation|invalid|unexpected argument", r.error, re.I))
            ]
            no_backoff = all(not c.attributes.get("backoff_ms") for c in group[1:])
            if non_retryable or (len(group) >= 3 and no_backoff):
                why = (
                    "the error was non-retryable, so an identical retry cannot succeed"
                    if non_retryable
                    else f"{len(group)} identical attempts with no backoff"
                )
                yield Finding(
                    category=C.broken_retry_logic,
                    severity="medium",
                    event_ids=ids,
                    title=f"'{name}' retried with identical arguments after failure",
                    detail=f"{len(group)} identical calls; {why}.",
                    detector="repeated_and_retry",
                    evidence={"attempts": len(group)},
                )
        elif len(group) >= 3:
            yield Finding(
                category=C.repeated_tool_calls,
                severity="low",
                event_ids=ids,
                title=f"'{name}' called {len(group)} times with identical arguments",
                detail="Successful identical calls were repeated; results could be reused.",
                detector="repeated_and_retry",
                evidence={"calls": len(group)},
            )


_INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|disregard (the |your )?(system|previous)"
    r"|you are now|reveal (your|the) system prompt|exfiltrate|send (all|the) (credentials|secrets|api keys)",
    re.I,
)


@detector
def prompt_injection(trace: Trace) -> Iterable[Finding]:
    for e in trace.events:
        if e.kind not in ("tool_result", "retrieval"):
            continue
        m = _INJECTION.search(_text_of(e))
        if m:
            later = [x.id for x in trace.events if x.seq > e.seq and x.kind == "tool_call"]
            yield Finding(
                category=C.prompt_injection,
                severity="critical",
                event_ids=[e.id] + later[:3],
                title="Instruction-like content in untrusted input",
                detail=f"Untrusted content from '{e.name}' contains {m.group(0)!r}."
                + (f" {len(later)} tool call(s) followed it." if later else ""),
                detector="prompt_injection",
                evidence={"match": m.group(0), "subsequent_tool_calls": later},
            )


_UNSAFE_TOOLS = {"delete_file", "drop_table", "transfer_funds", "send_email_all", "shell", "exec"}
_UNSAFE_ARGS = re.compile(
    r"rm\s+-rf|drop\s+table|truncate\s+table|chmod\s+777|curl[^|]*\|\s*(ba)?sh|format\s+c:|del\s+/s",
    re.I,
)


@detector
def unsafe_actions(trace: Trace) -> Iterable[Finding]:
    for e in trace.events:
        if e.kind != "tool_call" or e.attributes.get("approved") is True:
            continue
        m = _UNSAFE_ARGS.search(json.dumps(e.input, default=str))
        if e.name in _UNSAFE_TOOLS or m:
            yield Finding(
                category=C.unsafe_action,
                severity="critical",
                event_ids=[e.id],
                title=f"Unapproved destructive action via '{e.name}'",
                detail=(f"Arguments contain {m.group(0)!r}. " if m else "")
                + "No human approval was recorded for this call.",
                detector="unsafe_actions",
            )


@detector
def excessive_tokens(trace: Trace) -> Iterable[Finding]:
    budget = trace.metadata.get("token_budget")
    if not budget:
        return
    total = sum(e.tokens_in + e.tokens_out for e in trace.events)
    if total > budget:
        top = sorted(trace.events, key=lambda e: e.tokens_in + e.tokens_out, reverse=True)[:3]
        yield Finding(
            category=C.excessive_token_usage,
            severity="low",
            event_ids=[e.id for e in top if e.tokens_in + e.tokens_out],
            title=f"Token usage {total:,} exceeds budget {budget:,}",
            detail=f"{total / budget:.1f}x the declared budget.",
            detector="excessive_tokens",
            evidence={"total_tokens": total, "budget": budget},
        )


_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")


@detector
def unsupported_claims(trace: Trace) -> Iterable[Finding]:
    docs: dict[str, str] = {}
    retrieval_ids: list[str] = []
    for e in trace.events:
        if e.kind == "retrieval":
            retrieval_ids.append(e.id)
            for d in (e.output or {}).get("documents", []):
                docs[d["id"]] = d.get("text", "")
    for e in trace.events:
        claims = (e.output or {}).get("claims") if e.kind == "output" else None
        if not claims:
            continue
        for i, claim in enumerate(claims):
            cites = claim.get("citations", [])
            text = claim.get("text", "")
            reason = None
            if not cites:
                reason = "no citation"
            elif any(c not in docs for c in cites):
                reason = f"cites documents that were never retrieved: {[c for c in cites if c not in docs]}"
            else:
                cited = " ".join(docs[c] for c in cites)
                missing = [n for n in _NUMBER.findall(text) if n not in cited]
                if missing:
                    reason = f"figures {missing} do not appear in the cited evidence"
            if reason:
                yield Finding(
                    category=C.unsupported_claim,
                    severity="high",
                    event_ids=[e.id] + retrieval_ids,
                    title=f"Claim {i + 1} is not supported by retrieved evidence",
                    detail=f"{text!r}: {reason}.",
                    detector="unsupported_claims",
                    evidence={"claim_index": i, "claim": text, "reason": reason},
                )


@detector
def failing_tests(trace: Trace) -> Iterable[Finding]:
    for e in trace.events:
        if e.kind == "test_run" and (e.status == "error" or (e.output or {}).get("failed", 0) > 0):
            out = e.output or {}
            yield Finding(
                category=C.failing_test,
                severity="high",
                event_ids=[e.id],
                title=f"{out.get('failed', '?')} of {out.get('total', '?')} tests failed",
                detail="; ".join(f["name"] for f in out.get("failures", [])) or (e.error or ""),
                detector="failing_tests",
                evidence={"failures": out.get("failures", [])},
            )


# Lower rank = more likely to be a root cause when several findings co-occur.
ROOT_CAUSE_RANK = {
    C.unsafe_action: 0,
    C.prompt_injection: 1,
    C.hallucinated_tool: 2,
    C.invalid_tool_arguments: 3,
    C.missing_context: 4,
    C.incorrect_routing: 5,
    C.malformed_output: 6,
    C.unsupported_claim: 7,
    C.failing_test: 8,
    C.api_dependency_failure: 9,
    C.timeout: 10,
    C.tool_execution_exception: 11,
    C.broken_retry_logic: 12,
    C.repeated_tool_calls: 13,
    C.excessive_token_usage: 14,
}

_SYMPTOMS = {
    C.tool_execution_exception: {C.invalid_tool_arguments, C.hallucinated_tool, C.missing_context},
    C.broken_retry_logic: {C.invalid_tool_arguments, C.api_dependency_failure, C.timeout},
}


def _merge_duplicates(findings: list[Finding]) -> list[Finding]:
    merged: dict[tuple[str, str], Finding] = {}
    for f in findings:
        key = (f.category.value, f.detail)
        if key in merged:
            existing = merged[key]
            existing.event_ids += [i for i in f.event_ids if i not in existing.event_ids]
            existing.evidence["occurrences"] = existing.evidence.get("occurrences", 1) + 1
        else:
            merged[key] = f
    for f in merged.values():
        if f.evidence.get("occurrences", 1) > 1:
            f.title += f" (x{f.evidence['occurrences']})"
    return list(merged.values())


def run_detectors(trace: Trace) -> list[Finding]:
    findings = _merge_duplicates([f for d in _DETECTORS for f in d(trace)])
    present = {f.category for f in findings}
    for f in findings:
        causes = _SYMPTOMS.get(f.category, set()) & present
        if causes:
            f.is_symptom_of = min(causes, key=lambda c: ROOT_CAUSE_RANK[c])
    seq = {e.id: e.seq for e in trace.events}
    findings.sort(key=lambda f: (ROOT_CAUSE_RANK[f.category], min((seq.get(i, 0) for i in f.event_ids), default=0)))
    return findings


def primary_finding(findings: list[Finding]) -> Finding | None:
    roots = [f for f in findings if f.is_symptom_of is None]
    return (roots or findings or [None])[0]
