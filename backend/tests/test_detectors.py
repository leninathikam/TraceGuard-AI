from traceguard.benchmark.cases import CASES
from traceguard.detectors import primary_finding, run_detectors
from traceguard.jsonschema_lite import validate
from traceguard.otel import from_otlp


def test_schema_validator_reports_each_violation():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}, "d": {"type": "string", "pattern": r"^\d{4}$"}},
              "required": ["n"], "additionalProperties": False}
    errors = validate({"d": "12", "x": 1}, schema)
    assert any("missing required property 'n'" in e for e in errors)
    assert any("unexpected property 'x'" in e for e in errors)
    assert any("does not match pattern" in e for e in errors)
    assert validate({"n": 3}, schema) == []
    assert validate({"n": True}, schema)  # bools are not integers


def test_structural_cases_hit_expected_primary():
    for case in CASES:
        if case.kind != "structural":
            continue
        findings = run_detectors(case.trace)
        primary = primary_finding(findings)
        assert primary is not None, case.id
        assert primary.category.value == case.primary, (case.id, [f.category.value for f in findings])


def test_healthy_cases_are_clean():
    for case in CASES:
        if case.kind == "healthy":
            assert run_detectors(case.trace) == [], case.id


def test_symptoms_point_at_root_cause():
    case = next(c for c in CASES if c.id == "invalid_args_missing")
    findings = {f.category.value: f for f in run_detectors(case.trace)}
    assert findings["tool_execution_exception"].is_symptom_of.value == "invalid_tool_arguments"
    assert findings["invalid_tool_arguments"].is_symptom_of is None


def test_otlp_genai_spans_become_tool_events():
    def attr(k, v):
        return {"key": k, "value": {"stringValue": v}}

    payload = {"resourceSpans": [{"scopeSpans": [{"spans": [
        {"spanId": "a", "name": "invoke_agent weather", "startTimeUnixNano": "1", "endTimeUnixNano": "5",
         "attributes": [attr("gen_ai.operation.name", "invoke_agent")]},
        {"spanId": "b", "parentSpanId": "a", "name": "execute_tool get_weather", "startTimeUnixNano": "2",
         "endTimeUnixNano": "3", "status": {"code": 2, "message": "missing argument 'city'"},
         "attributes": [attr("gen_ai.operation.name", "execute_tool"), attr("gen_ai.tool.name", "get_weather"),
                        attr("gen_ai.tool.call.arguments", '{"location": "Lisbon"}')]},
    ]}]}]}
    trace = from_otlp(payload)
    kinds = [(e.kind, e.name) for e in trace.events]
    assert ("tool_call", "get_weather") in kinds and ("tool_result", "get_weather") in kinds
    call = next(e for e in trace.events if e.kind == "tool_call")
    assert call.input == {"location": "Lisbon"} and call.parent_id == "e001"
    assert any(f.category.value == "tool_execution_exception" for f in run_detectors(trace))
