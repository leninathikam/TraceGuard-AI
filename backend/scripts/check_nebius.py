"""Live smoke test of the Token Factory connection. Never prints the API key."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from traceguard.env import load_dotenv  # noqa: E402

load_dotenv()

from traceguard.nebius import DEPRECATED_MODELS, NebiusClient  # noqa: E402

client = NebiusClient()
print(f"key set: {client.configured}  primary model: {client.model}  base_url: {client.base_url}")
print(f"configured fallback model: {client.fallback_model}")

models = client.list_models()
print(f"models visible to this key: {len(models)}")
nvidia_models = sorted(m for m in models if m.lower().startswith("nvidia/"))
print("NVIDIA models:", nvidia_models)

if client.model in DEPRECATED_MODELS:
    print(f"WARNING: Primary model '{client.model}' deprecates on November 9, 2026.")
print(f"primary model served: {client.model in models}")
print(f"fallback model served: {client.fallback_model in models if client.fallback_model else False}")

# Smoke test primary model
print("\n--- Smoke test primary model ---")
reply = client.chat(
    [{"role": "user", "content": 'Return the JSON object {"ok": true, "status": "primary"} and nothing else.'}],
    max_tokens=300,
)
print("reply:", reply.content[:300].replace("\n", " "))
print(
    f"served model: {reply.raw_model_field}  tokens in/out: {reply.prompt_tokens}/{reply.completion_tokens}  "
    f"cost: ${reply.cost_usd:.6f}  latency: {reply.latency_ms:.0f} ms  attempts: {reply.attempts}"
)

# Smoke test fallback model
if client.fallback_model:
    print(f"\n--- Smoke test fallback model ({client.fallback_model}) ---")
    fb_reply = client.chat(
        [{"role": "user", "content": 'Return the JSON object {"ok": true, "status": "fallback"} and nothing else.'}],
        max_tokens=300,
        model=client.fallback_model,
        allow_fallback=False,
    )
    print("fallback reply:", fb_reply.content[:300].replace("\n", " "))
    print(
        f"served model: {fb_reply.raw_model_field}  tokens in/out: {fb_reply.prompt_tokens}/{fb_reply.completion_tokens}  "
        f"cost: ${fb_reply.cost_usd:.6f}  latency: {fb_reply.latency_ms:.0f} ms  attempts: {fb_reply.attempts}"
    )
