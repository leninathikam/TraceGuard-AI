from __future__ import annotations

from dataclasses import dataclass
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

    @property
    def path(self) -> Path:
        return ROOT / self.id

    def read(self, name: str) -> str:
        return (self.path / name).read_text(encoding="utf-8")


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
    ]
}
