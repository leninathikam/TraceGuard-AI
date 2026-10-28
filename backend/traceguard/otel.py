"""Convert OTLP/JSON spans that follow the OpenTelemetry GenAI semantic conventions into a Trace."""

from __future__ import annotations

import json
from typing import Any

from .schema import Trace, TraceEvent


def _attr_value(v: dict[str, Any]) -> Any:
    for key in ("stringValue", "boolValue", "doubleValue"):
        if key in v:
            return v[key]
    if "intValue" in v:
        return int(v["intValue"])
    if "arrayValue" in v:
        return [_attr_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def _attrs(span: dict[str, Any]) -> dict[str, Any]:
    return {a["key"]: _attr_value(a.get("value", {})) for a in span.get("attributes", [])}


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def from_otlp(payload: dict[str, Any], workflow: str = "otel-import") -> Trace:
    spans = [
        s
        for rs in payload.get("resourceSpans", [])
        for ss in rs.get("scopeSpans", [])
        for s in ss.get("spans", [])
    ]
    spans.sort(key=lambda s: int(s.get("startTimeUnixNano", 0)))
    events: list[TraceEvent] = []
    span_to_event: dict[str, str] = {}
    task = ""

    def add(**kw: Any) -> str:
        eid = f"e{len(events) + 1:03d}"
        events.append(TraceEvent(id=eid, seq=len(events) + 1, **kw))
        return eid

    for span in spans:
        a = _attrs(span)
        op = a.get("gen_ai.operation.name", "")
        failed = span.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")
        error = span.get("status", {}).get("message") if failed else None
        duration = (int(span.get("endTimeUnixNano", 0)) - int(span.get("startTimeUnixNano", 0))) / 1e6
        parent = span_to_event.get(span.get("parentSpanId", ""))
        common = dict(duration_ms=max(duration, 0.0), attributes={k: v for k, v in a.items()
                                                                  if not k.startswith("gen_ai.tool.call")})
        if op == "execute_tool":
            name = a.get("gen_ai.tool.name", span.get("name", "tool"))
            call = add(kind="tool_call", name=name, parent_id=parent,
                       input=_maybe_json(a.get("gen_ai.tool.call.arguments")) or {}, **common)
            result = _maybe_json(a.get("gen_ai.tool.call.result"))
            add(kind="tool_result", name=name, parent_id=call,
                output=result if isinstance(result, dict) else {"result": result},
                status="error" if failed else "ok", error=error)
            span_to_event[span.get("spanId", "")] = call
        else:
            kind = "llm_call" if op in ("chat", "text_completion", "generate_content") else "agent_step"
            if op == "invoke_agent":
                kind = "agent_start"
                task = task or str(a.get("gen_ai.agent.description", span.get("name", "")))
            prompt = a.get("gen_ai.input.messages") or a.get("gen_ai.prompt")
            completion = a.get("gen_ai.output.messages") or a.get("gen_ai.completion")
            eid = add(kind=kind, name=span.get("name", op or "span"), parent_id=parent,
                      input={"messages": _maybe_json(prompt)} if prompt else {},
                      output={"text": completion if isinstance(completion, str) else json.dumps(completion)}
                      if completion else None,
                      status="error" if failed else "ok", error=error,
                      tokens_in=int(a.get("gen_ai.usage.input_tokens", 0) or 0),
                      tokens_out=int(a.get("gen_ai.usage.output_tokens", 0) or 0), **common)
            span_to_event[span.get("spanId", "")] = eid

    failed_any = any(e.status == "error" for e in events)
    return Trace(workflow=workflow, task=task, events=events,
                 final_status="failure" if failed_any else "unknown",
                 metadata={"source": "otlp"})
