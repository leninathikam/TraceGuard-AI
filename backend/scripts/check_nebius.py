"""Live smoke test of the Token Factory connection. Never prints the API key."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from traceguard.env import load_dotenv  # noqa: E402

load_dotenv()

from traceguard.nebius import NebiusClient  # noqa: E402

client = NebiusClient()
print(f"key set: {client.configured}  model: {client.model}  base_url: {client.base_url}")
models = client.list_models()
print(f"models visible to this key: {len(models)}")
print("NVIDIA models:", sorted(m for m in models if m.lower().startswith("nvidia/")))
print("configured model served:", client.model in models)
reply = client.chat([{"role": "user", "content": 'Return the JSON object {"ok": true} and nothing else.'}],
                    max_tokens=300)
print("reply:", reply.content[:300].replace("\n", " "))
print(f"served model: {reply.raw_model_field}  tokens in/out: {reply.prompt_tokens}/{reply.completion_tokens}  "
      f"cost: ${reply.cost_usd:.6f}  latency: {reply.latency_ms:.0f} ms  attempts: {reply.attempts}")
