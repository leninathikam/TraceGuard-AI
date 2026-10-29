import json

from fastapi.testclient import TestClient

from conftest import REFERENCE_REPAIRS, completion, fake_client
from traceguard import api
from traceguard.benchmark.cases import CASES


def test_end_to_end_scenario_flow(monkeypatch):
    http = TestClient(api.app)
    run = http.post("/api/scenarios/tool_agent/run").json()
    tid = run["trace_id"]
    assert "invalid_tool_arguments" in run["categories"]

    edits = [e.model_dump() for e in REFERENCE_REPAIRS["tool_agent"]]
    body = json.dumps({
        "category": "invalid_tool_arguments", "supporting_event_ids": ["e003", "e004"],
        "root_cause_hypothesis": "bad template", "confidence": "high", "confidence_rationale": "x",
        "limitations": "y", "repair": {"summary": "fix template", "edits": edits},
        "verification_procedure": ["replay"]})
    monkeypatch.setattr(api, "client", lambda: fake_client([completion(body)]))

    d = http.post(f"/api/traces/{tid}/diagnose", json={"mode": "hybrid"}).json()
    assert d["model_call"]["model"].startswith("nvidia/")
    v = http.post(f"/api/diagnoses/{d['id']}/verify").json()
    assert v["status"] == "validated" and v["repaired_trace_id"]

    detail = http.get(f"/api/traces/{tid}").json()
    assert detail["diagnoses"][0]["hypothesis_status"] == "supported_by_replay"
    replay = http.get(f"/api/traces/{v['repaired_trace_id']}").json()
    assert replay["trace"]["final_status"] == "success" and replay["findings"] == []
    assert http.get("/api/usage").json()["by_model"][0]["n"] >= 1


def test_model_mode_without_key_is_explicit(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    http = TestClient(api.app)
    tid = http.post("/api/traces", json=CASES[0].trace.model_dump()).json()["trace_id"]
    r = http.post(f"/api/traces/{tid}/diagnose", json={"mode": "model"})
    assert r.status_code == 400 and "NEBIUS_API_KEY" in r.json()["detail"]
    rules = http.post(f"/api/traces/{tid}/diagnose", json={"mode": "rules"}).json()
    assert rules["category"] == "invalid_tool_arguments"


def test_rules_evaluation_runs_and_skips_model_modes(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    http = TestClient(api.app)
    r = http.post("/api/evaluations", json={"modes": ["rules", "hybrid"], "include_repairs": False}).json()
    assert "rules" in r["diagnosis"] and "hybrid" in r["skipped"]
    assert http.get("/api/evaluations/latest").json()["id"] == r["id"]


def test_sandbox_status_and_mode_endpoints():
    http = TestClient(api.app)
    status = http.get("/api/sandbox/status").json()
    assert "current_mode" in status and "docker_available" in status
    r = http.post("/api/sandbox/mode", json={"mode": "docker"}).json()
    assert r["current_mode"] == "docker"
    r = http.post("/api/sandbox/mode", json={"mode": "subprocess"}).json()
    assert r["current_mode"] == "subprocess"
