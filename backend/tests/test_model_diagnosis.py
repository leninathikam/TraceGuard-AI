import json

import pytest

from conftest import completion, fake_client
from traceguard.diagnosis import ModelDiagnosisInvalid, diagnose, diagnose_with_model
from traceguard.nebius import PRICING, NebiusClient, NebiusError, extract_json
from traceguard.sandbox import run_scenario
from traceguard.scenarios import SCENARIOS


@pytest.fixture(scope="module")
def tool_trace():
    trace = run_scenario(SCENARIOS["tool_agent"]).trace
    trace.id = "tr_test"
    return trace


def _good(edits=None):
    return json.dumps({
        "category": "invalid_tool_arguments",
        "supporting_event_ids": ["e003", "e004"],
        "root_cause_hypothesis": "argument_template maps US date, 12h time and a 'duration' string.",
        "confidence": "high", "confidence_rationale": "schema violations are explicit",
        "limitations": "cannot see the tool implementation",
        "repair": {"summary": "use ISO slots", "edits": edits if edits is not None else [
            {"path": "tool_policy.json", "find": '"{date_us}"', "replace": '"{date_iso}"'}]},
        "verification_procedure": ["replay"],
    })


def test_extract_json_handles_think_and_fences():
    assert extract_json('<think>{"no": 1}</think>Here:\n```json\n{"a": {"b": "}"}}\n```') == {"a": {"b": "}"}}
    assert extract_json('prefix {"a": 1} suffix') == {"a": 1}


def test_model_diagnosis_validated_and_costed(tool_trace):
    calls = []
    client = fake_client([completion(_good())], calls)
    d, comps = diagnose_with_model(tool_trace, "hybrid", client)
    assert d.category.value == "invalid_tool_arguments" and d.mode == "hybrid"
    assert d.model_call.model == "nvidia/nemotron-3-super-120b-a12b"
    assert d.model_call.cost_usd == pytest.approx((1000 * 0.30 + 200 * 0.90) / 1e6)
    body = calls[0]
    assert body["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert body["response_format"] == {"type": "json_object"}
    payload = json.loads(body["messages"][1]["content"])
    assert "deterministic_findings" in payload and "tool_policy.json" in payload["editable_files"]


def test_model_mode_does_not_see_rule_findings(tool_trace):
    calls = []
    diagnose_with_model(tool_trace, "model", fake_client([completion(_good())], calls))
    assert "deterministic_findings" not in json.loads(calls[0]["messages"][1]["content"])


def test_hidden_tests_never_sent_to_model():
    trace = run_scenario(SCENARIOS["coding_agent"]).trace
    trace.id = "tr_code"
    calls = []
    bad = json.dumps({"category": "nope"})
    with pytest.raises(ModelDiagnosisInvalid):
        diagnose_with_model(trace, "hybrid", fake_client([completion(bad), completion(bad)], calls))
    sent = json.dumps(calls)
    assert "test_visible.py" in sent and "test_hidden" not in sent


def test_invalid_output_gets_one_corrective_retry(tool_trace):
    bad = _good().replace('"e003", "e004"', '"e999"')
    calls = []
    d, comps = diagnose_with_model(tool_trace, "model", fake_client([completion(bad), completion(_good())], calls))
    assert len(comps) == 2 and d.model_call.attempts == 2
    assert any("e999" in e for e in d.model_call.validation_errors)
    assert "failed validation" in calls[1]["messages"][-1]["content"]


def test_inapplicable_edit_is_a_validation_error(tool_trace):
    bad = _good([{"path": "tool_policy.json", "find": "not in file", "replace": "x"}])
    with pytest.raises(ModelDiagnosisInvalid, match="matched 0 times"):
        diagnose_with_model(tool_trace, "model", fake_client([completion(bad), completion(bad)]))


def test_transient_errors_retry_then_succeed(tool_trace, monkeypatch):
    monkeypatch.setattr("traceguard.nebius.time.sleep", lambda s: None)
    client = fake_client([{"status": 503}, {"status": 429}, completion(_good())])
    d, comps = diagnose_with_model(tool_trace, "model", client)
    assert comps[0].attempts == 3


def test_response_format_rejection_falls_back(tool_trace):
    calls = []
    client = fake_client([{"status": 400, "json": {"error": "response_format unsupported"}},
                          completion(_good())], calls)
    diagnose_with_model(tool_trace, "model", client)
    assert "response_format" in calls[0] and "response_format" not in calls[1]


def test_hybrid_falls_back_to_rules_and_says_so(tool_trace, monkeypatch):
    monkeypatch.setattr("traceguard.nebius.time.sleep", lambda s: None)
    client = fake_client([{"status": 500}] * 3)
    d = diagnose(tool_trace, "hybrid", client)
    assert d.fallback_reason and "fell back to rules" in d.fallback_reason
    assert d.category.value == "invalid_tool_arguments"
    with pytest.raises(NebiusError):
        diagnose(tool_trace, "model", fake_client([{"status": 500}] * 3))


def test_client_default_fallback_model_is_nemotron_ultra(monkeypatch):
    monkeypatch.delenv("TRACEGUARD_FALLBACK_MODEL", raising=False)
    client = NebiusClient(api_key="k")
    assert client.fallback_model == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert client.fallback_model in PRICING
    monkeypatch.setenv("TRACEGUARD_FALLBACK_MODEL", "custom-fallback")
    assert NebiusClient(api_key="k").fallback_model == "custom-fallback"


def test_chat_falls_back_to_strong_model_on_api_error(monkeypatch):
    monkeypatch.setattr("traceguard.nebius.time.sleep", lambda s: None)
    calls = []
    # Primary model returns 404 (e.g. deprecated endpoint), fallback model succeeds
    client = fake_client(
        [
            {"status": 404, "json": {"error": "model deprecated"}},
            completion('{"ok": true}', model="nvidia/Nemotron-3-Ultra-550b-a55b"),
        ],
        calls=calls,
        fallback_model="nvidia/Nemotron-3-Ultra-550b-a55b",
    )
    reply = client.chat([{"role": "user", "content": "hello"}])
    assert reply.model == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert len(calls) == 2
    assert calls[0]["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert calls[1]["model"] == "nvidia/Nemotron-3-Ultra-550b-a55b"


def test_diagnose_falls_back_to_strong_model_on_primary_api_deprecation(tool_trace, monkeypatch):
    monkeypatch.setattr("traceguard.nebius.time.sleep", lambda s: None)
    calls = []
    client = fake_client(
        [
            {"status": 404, "json": {"error": "model deprecated"}},
            completion(_good(), model="nvidia/Nemotron-3-Ultra-550b-a55b"),
        ],
        calls=calls,
        fallback_model="nvidia/Nemotron-3-Ultra-550b-a55b",
    )
    d = diagnose(tool_trace, "hybrid", client)
    assert d.category.value == "invalid_tool_arguments"
    assert d.model_call.model == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert d.fallback_reason is not None
    assert "nvidia/Nemotron-3-Ultra-550b-a55b" in d.fallback_reason


def test_diagnose_falls_back_to_strong_model_on_validation_failure(tool_trace, monkeypatch):
    bad = json.dumps({"category": "invalid_category_not_real"})
    calls = []
    # Primary model returns invalid output twice; fallback client is invoked and succeeds
    client = fake_client(
        [
            completion(bad),
            completion(bad),
            completion(_good(), model="nvidia/Nemotron-3-Ultra-550b-a55b"),
        ],
        calls=calls,
        fallback_model="nvidia/Nemotron-3-Ultra-550b-a55b",
    )
    d = diagnose(tool_trace, "hybrid", client)
    assert d.category.value == "invalid_tool_arguments"
    assert d.model_call.model == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert d.fallback_reason is not None
    assert "recovered using NVIDIA fallback model" in d.fallback_reason


def test_diagnose_hybrid_falls_back_to_rules_when_both_primary_and_fallback_fail(tool_trace, monkeypatch):
    monkeypatch.setattr("traceguard.nebius.time.sleep", lambda s: None)
    client = fake_client(
        [
            {"status": 500},
            {"status": 500},
            {"status": 500},
            {"status": 500},
            {"status": 500},
            {"status": 500},
        ],
        fallback_model="nvidia/Nemotron-3-Ultra-550b-a55b",
    )
    d = diagnose(tool_trace, "hybrid", client)
    assert d.mode == "hybrid"
    assert d.category.value == "invalid_tool_arguments"
    assert d.fallback_reason is not None
    assert "fell back to rules" in d.fallback_reason
