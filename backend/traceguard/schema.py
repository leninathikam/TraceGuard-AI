from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


EventKind = Literal[
    "agent_start",
    "agent_step",
    "llm_call",
    "tool_call",
    "tool_result",
    "retrieval",
    "route",
    "output",
    "test_run",
    "error",
    "agent_end",
]


class FailureCategory(str, Enum):
    invalid_tool_arguments = "invalid_tool_arguments"
    tool_execution_exception = "tool_execution_exception"
    malformed_output = "malformed_output"
    missing_context = "missing_context"
    hallucinated_tool = "hallucinated_tool"
    incorrect_routing = "incorrect_routing"
    repeated_tool_calls = "repeated_tool_calls"
    api_dependency_failure = "api_dependency_failure"
    timeout = "timeout"
    prompt_injection = "prompt_injection"
    unsafe_action = "unsafe_action"
    excessive_token_usage = "excessive_token_usage"
    broken_retry_logic = "broken_retry_logic"
    unsupported_claim = "unsupported_claim"
    failing_test = "failing_test"
    none = "none"


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class TraceEvent(BaseModel):
    id: str
    seq: int
    kind: EventKind
    name: str
    parent_id: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    status: Literal["ok", "error"] = "ok"
    error: str | None = None
    duration_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    attributes: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    id: str = ""
    workflow: str
    scenario: str | None = None
    task: str = ""
    final_status: Literal["success", "failure", "unknown"] = "unknown"
    created_at: str = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    events: list[TraceEvent]

    def tools(self) -> dict[str, ToolSpec]:
        return {t["name"]: ToolSpec(**t) for t in self.metadata.get("tools", [])}

    def event(self, event_id: str) -> TraceEvent | None:
        return next((e for e in self.events if e.id == event_id), None)


Severity = Literal["critical", "high", "medium", "low"]


class Finding(BaseModel):
    category: FailureCategory
    severity: Severity
    event_ids: list[str]
    title: str
    detail: str
    detector: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    is_symptom_of: FailureCategory | None = None


class FileEdit(BaseModel):
    path: str
    find: str
    replace: str


class RepairProposal(BaseModel):
    summary: str
    edits: list[FileEdit] = Field(default_factory=list)

    @property
    def verifiable(self) -> bool:
        return bool(self.edits)


Confidence = Literal["low", "medium", "high"]
HypothesisStatus = Literal["hypothesis", "supported_by_replay", "not_supported_by_replay"]


class ModelCallInfo(BaseModel):
    model: str
    attempts: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    validation_errors: list[str] = Field(default_factory=list)


class Diagnosis(BaseModel):
    id: str = ""
    trace_id: str
    mode: Literal["rules", "model", "hybrid"]
    created_at: str = Field(default_factory=utcnow)
    category: FailureCategory
    supporting_event_ids: list[str]
    root_cause_hypothesis: str
    hypothesis_status: HypothesisStatus = "hypothesis"
    confidence: Confidence
    confidence_rationale: str
    limitations: str
    repair: RepairProposal
    verification_procedure: list[str]
    findings_used: list[Finding] = Field(default_factory=list)
    model_call: ModelCallInfo | None = None
    fallback_reason: str | None = None


class AcceptanceCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class SandboxRun(BaseModel):
    ok: bool
    agent_exit_code: int | None
    acceptance_passed: bool
    checks: list[AcceptanceCheck]
    trace: Trace | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    sandbox: str = "subprocess"
    error: str | None = None


class Verification(BaseModel):
    id: str = ""
    diagnosis_id: str
    trace_id: str
    created_at: str = Field(default_factory=utcnow)
    status: Literal["validated", "failed", "rejected", "not_applicable"]
    reason: str
    diff: str = ""
    baseline: SandboxRun | None = None
    repaired: SandboxRun | None = None
    fixed_checks: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    still_failing: list[str] = Field(default_factory=list)
    remaining_findings: list[Finding] = Field(default_factory=list)
    repaired_trace_id: str | None = None
    intervention_tests: list[dict[str, Any]] = Field(default_factory=list)
    evidence_hashes: dict[str, str] = Field(default_factory=dict)
    causal_scope: str = "Not tested."
