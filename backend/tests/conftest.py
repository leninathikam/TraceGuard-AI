import json
import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TRACEGUARD_DB", ":memory:")

from traceguard.nebius import NebiusClient  # noqa: E402
from traceguard.schema import FileEdit  # noqa: E402

REFERENCE_REPAIRS = {
    "tool_agent": [FileEdit(
        path="tool_policy.json",
        find='''    "date": "{date_us}",
    "start_time": "{time_12h}",
    "duration": "{duration_text}",''',
        replace='''    "date": "{date_iso}",
    "start_time": "{time_24h}",
    "duration_minutes": "{duration_minutes}",''',
    )],
    "research_agent": [FileEdit(
        path="answer_policy.json",
        find='"include_background_knowledge": true',
        replace='"include_background_knowledge": false',
    )],
    "coding_agent": [FileEdit(path="solution.py", find="", replace='''import re

_PATTERN = re.compile(r"(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?")


def parse_duration(text: str) -> int:
    """Return the total number of seconds in a duration like '1h30m' or '45s'."""
    match = _PATTERN.fullmatch(text)
    if not text or match is None:
        raise ValueError(f"invalid duration: {text!r}")
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds
''')],
    "payment_gateway": [FileEdit(
        path="services/order_service.py",
        find="""        # BUG: Fails to pass the idempotency_key to the ledger service (passes empty string)
        self.ledger.record_transaction(
            order_id=order_id,
            idempotency_key="",
            gross_amount=amount,
            fee_amount=fee,
            status=PaymentStatus.CAPTURED,
        )""",
        replace="""        self.ledger.record_transaction(
            order_id=order_id,
            idempotency_key=idempotency_key,
            gross_amount=amount,
            fee_amount=fee,
            status=PaymentStatus.CAPTURED,
        )""",
    )],
}


def fake_client(responses: list[dict], calls: list | None = None) -> NebiusClient:
    """A NebiusClient whose HTTP layer returns canned chat-completion bodies (tests only)."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(json.loads(request.content or b"{}"))
        item = queue.pop(0)
        return httpx.Response(item.get("status", 200), json=item.get("json", {}))

    return NebiusClient(api_key="test-key", transport=httpx.MockTransport(handler), max_retries=2)


def completion(content: str, prompt_tokens: int = 1000, completion_tokens: int = 200) -> dict:
    return {"json": {"model": "nvidia/nemotron-3-super-120b-a12b",
                     "choices": [{"message": {"role": "assistant", "content": content}}],
                     "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}}}


@pytest.fixture
def reference_repairs():
    return REFERENCE_REPAIRS
