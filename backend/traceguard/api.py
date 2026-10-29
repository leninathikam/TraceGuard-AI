from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .env import load_dotenv

load_dotenv()

from .benchmark import run_evaluation  # noqa: E402
from .detectors import run_detectors
from .diagnosis import diagnose
from .nebius import NebiusClient, NebiusError, NebiusNotConfigured
from .otel import from_otlp
from .sandbox import run_scenario
from .scenarios import SCENARIOS
from .schema import Trace
from .store import Store
from .verify import verify_repair
from .live_agent import run_live_agent
from .evidence import regression_test

app = FastAPI(title="TraceGuard AI", version=__version__)
store = Store()


def client() -> NebiusClient:
    return NebiusClient()


def ingest(trace: Trace, source: str) -> dict[str, Any]:
    trace.id = ""
    store.add_trace(trace, source=source)
    findings = run_detectors(trace)
    store.set_findings(trace.id, findings)
    return {"trace_id": trace.id, "finding_count": len(findings),
            "categories": sorted({f.category.value for f in findings})}


class SandboxModeRequest(BaseModel):
    mode: Literal["subprocess", "docker"]


@app.get("/api/sandbox/status")
def sandbox_status() -> dict[str, Any]:
    from .sandbox import is_docker_available, _sandbox_mode
    avail, detail = is_docker_available()
    return {
        "current_mode": _sandbox_mode(),
        "docker_available": avail,
        "docker_detail": detail,
        "image": os.environ.get("TRACEGUARD_SANDBOX_IMAGE", "python:3.12-slim"),
    }


@app.post("/api/sandbox/mode")
def set_sandbox_mode(req: SandboxModeRequest) -> dict[str, Any]:
    os.environ["TRACEGUARD_SANDBOX"] = req.mode
    return sandbox_status()


@app.get("/api/health")
def health() -> dict[str, Any]:
    c = client()
    return {"status": "ok", "version": __version__, "nebius_configured": c.configured,
            "model": c.model, "base_url": c.base_url,
            "sandbox": os.environ.get("TRACEGUARD_SANDBOX", "subprocess")}


@app.get("/api/nebius/check")
def nebius_check() -> dict[str, Any]:
    """Live check: list Token Factory models and confirm the configured NVIDIA model is served."""
    c = client()
    try:
        models = c.list_models()
    except NebiusNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Token Factory unreachable: {exc}")
    nvidia = sorted(m for m in models if m.lower().startswith("nvidia/"))
    return {"model": c.model, "model_available": c.model in models, "nvidia_models": nvidia}


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    return [{"id": s.id, "title": s.title, "summary": s.summary,
             "editable_files": list(s.editable_files)} for s in SCENARIOS.values()]


@app.post("/api/scenarios/{scenario_id}/run")
def run(scenario_id: str) -> dict[str, Any]:
    scenario = SCENARIOS.get(scenario_id)
    if not scenario:
        raise HTTPException(404, "unknown scenario")
    result = run_scenario(scenario)
    if result.trace is None:
        raise HTTPException(500, f"scenario produced no trace: {result.error or result.stderr[-300:]}")
    return {**ingest(result.trace, "scenario"),
            "acceptance": [c.model_dump() for c in result.checks]}


@app.post('/api/agents/coding/run')
def run_coding_agent() -> dict[str, Any]:
    c = client()
    try:
        result, info = run_live_agent(c)
    except NebiusError as exc:
        store.log_llm_call('agent_generation', None, getattr(exc, 'info', None), c.model, False, str(exc))
        raise HTTPException(400 if isinstance(exc, NebiusNotConfigured) else 502, str(exc))
    store.log_llm_call('agent_generation', None, info, c.model, result.ok, result.error)
    if result.trace is None:
        raise HTTPException(502, result.error or 'Generated agent produced no trace')
    return {**ingest(result.trace, 'live_agent'), 'acceptance_passed': result.acceptance_passed,
            'acceptance': [check.model_dump() for check in result.checks]}


@app.post("/api/traces")
def ingest_trace(trace: Trace) -> dict[str, Any]:
    return ingest(trace, "api")


@app.post("/api/traces/otlp")
def ingest_otlp(payload: dict[str, Any], workflow: str = "otel-import") -> dict[str, Any]:
    try:
        trace = from_otlp(payload, workflow)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, f"could not parse OTLP payload: {exc}")
    if not trace.events:
        raise HTTPException(422, "no spans found in payload")
    return ingest(trace, "otlp")


@app.get("/api/traces")
def traces() -> list[dict[str, Any]]:
    return store.list_traces()


@app.get("/api/traces/{trace_id}")
def trace_detail(trace_id: str) -> dict[str, Any]:
    trace = store.get_trace(trace_id)
    if not trace:
        raise HTTPException(404, "trace not found")
    return {
        "trace": trace.model_dump(mode="json"),
        "findings": [f.model_dump(mode="json") for f in store.get_findings(trace_id)],
        "diagnoses": [d.model_dump(mode="json") for d in store.diagnoses_for(trace_id)],
        "verifications": [v.model_dump(mode="json") for v in store.verifications_for(trace_id)],
        "scenario": trace.scenario if trace.scenario in SCENARIOS else None,
    }


class DiagnoseRequest(BaseModel):
    mode: Literal["rules", "model", "hybrid"] = "hybrid"


@app.post("/api/traces/{trace_id}/diagnose")
def diagnose_trace(trace_id: str, req: DiagnoseRequest) -> dict[str, Any]:
    trace = store.get_trace(trace_id)
    if not trace:
        raise HTTPException(404, "trace not found")
    c = client()
    try:
        d = diagnose(trace, req.mode, c)
    except NebiusNotConfigured as exc:
        raise HTTPException(400, f"{exc}. Set NEBIUS_API_KEY to use Nemotron diagnosis.")
    except NebiusError as exc:
        store.log_llm_call("diagnosis", trace_id, getattr(exc, "info", None), c.model, False, str(exc))
        raise HTTPException(502, str(exc))
    if d.model_call or req.mode != "rules":
        store.log_llm_call("diagnosis", trace_id, d.model_call, c.model,
                           d.fallback_reason is None, d.fallback_reason)
    store.add_diagnosis(d)
    return d.model_dump(mode="json")


@app.post("/api/diagnoses/{diagnosis_id}/verify")
def verify(diagnosis_id: str) -> dict[str, Any]:
    d = store.get_diagnosis(diagnosis_id)
    if not d:
        raise HTTPException(404, "diagnosis not found")
    trace = store.get_trace(d.trace_id)
    v = verify_repair(d, trace)
    if v.repaired and v.repaired.trace:
        replay = v.repaired.trace.model_copy(deep=True)
        replay.workflow = f"{replay.workflow} (replay of {trace.id})"
        v.repaired_trace_id = ingest(replay, "replay")["trace_id"]
    if v.status == "validated":
        d.hypothesis_status = "supported_by_replay"
    elif v.status == "failed":
        d.hypothesis_status = "not_supported_by_replay"
    store.add_diagnosis(d)
    store.add_verification(v)
    return v.model_dump(mode="json")


@app.get('/api/traces/{trace_id}/evidence')
def export_evidence(trace_id: str) -> Response:
    import json
    detail = trace_detail(trace_id)
    return Response(json.dumps(detail, indent=2), media_type='application/json',
                    headers={'Content-Disposition': 'attachment; filename="traceguard-evidence.json"'})


@app.get('/api/diagnoses/{diagnosis_id}/regression-test')
def export_regression(diagnosis_id: str) -> Response:
    d = store.get_diagnosis(diagnosis_id)
    if not d:
        raise HTTPException(404, 'diagnosis not found')
    versions = [v for v in store.verifications_for(d.trace_id) if v.diagnosis_id == d.id]
    if not versions:
        raise HTTPException(409, 'Verify the repair before exporting a regression test')
    try:
        source = regression_test(store.get_trace(d.trace_id), d, versions[0])
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return Response(source, media_type='text/x-python',
                    headers={'Content-Disposition': 'attachment; filename="test_traceguard_regression.py"'})


class EvalRequest(BaseModel):
    modes: list[Literal["rules", "model", "hybrid"]] = ["rules", "model", "hybrid"]
    include_repairs: bool = True


@app.post("/api/evaluations")
def evaluate(req: EvalRequest) -> dict[str, Any]:
    result = run_evaluation(req.modes, client(), include_repairs=req.include_repairs)
    for call in result.pop("_llm_calls", []):
        store.log_llm_call("evaluation", None, call["info"], call["model"], call["ok"], call.get("error"))
    eid = store.add_evaluation(result)
    return {"id": eid, **result}


@app.get("/api/evaluations/latest")
def latest_evaluation() -> dict[str, Any] | None:
    return store.latest_evaluation()


@app.get("/api/usage")
def usage() -> dict[str, Any]:
    return store.usage()


_static = Path(os.environ.get("TRACEGUARD_STATIC", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if _static.is_dir():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        return FileResponse(_static / "index.html")
