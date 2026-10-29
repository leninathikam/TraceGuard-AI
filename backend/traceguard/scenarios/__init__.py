from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).parent


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    summary: str
    editable_files: tuple[str, ...]
    # Files the diagnosis model may read. Held-out tests are deliberately excluded.
    context_files: tuple[str, ...]
    code_files: tuple[str, ...] = ()
    captured_files: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return ROOT / self.id

    def read(self, name: str) -> str:
        if name in self.captured_files:
            return self.captured_files[name]
        return (self.path / name).read_text(encoding="utf-8")


def for_trace(trace) -> Scenario | None:
    """Resolve a captured artifact, never a client-supplied filesystem path."""
    scenario = SCENARIOS.get(trace.scenario or "")
    captured = trace.metadata.get("captured_files", {})
    if not scenario or not captured:
        return scenario
    from ..sandbox import apply_edits
    from ..schema import FileEdit
    edits = [FileEdit(path=p, find="", replace=s) for p, s in captured.items()]
    apply_edits(scenario, edits)
    return replace(scenario, captured_files=dict(captured))


SCENARIOS: dict[str, Scenario] = {
    s.id: s
    for s in [
        Scenario(
            id="tool_agent",
            title="A. Tool-calling agent",
            summary="A scheduling agent calls book_room with argument names and formats that "
            "violate the tool schema, then blindly retries.",
            editable_files=("tool_policy.json",),
            context_files=("tool_policy.json",),
        ),
        Scenario(
            id="research_agent",
            title="B. Research agent",
            summary="A RAG agent answers from retrieved documents but appends a remembered "
            "claim that no retrieved evidence supports. The agent reports success.",
            editable_files=("answer_policy.json",),
            context_files=("answer_policy.json", "corpus.json"),
        ),
        Scenario(
            id="coding_agent",
            title="C. Coding agent",
            summary="A coding agent writes parse_duration() with a unit bug and no input "
            "validation; visible tests fail. Held-out tests guard against overfitting.",
            editable_files=("solution.py",),
            context_files=("solution.py", "test_visible.py"),
            code_files=("solution.py",),
        ),
        Scenario(
            id="payment_gateway",
            title="D. Enterprise Codebase (Payment Gateway)",
            summary="A multi-module financial services repository (gateway, models, services, ledger, test suites). The agent omitted idempotency key propagation in order checkout.",
            editable_files=("services/order_service.py",),
            context_files=(
                "services/order_service.py",
                "gateway/models.py",
                "gateway/client.py",
                "services/ledger.py",
                "tests/test_compliance.py",
            ),
            code_files=("services/order_service.py",),
        ),
    ]
}
