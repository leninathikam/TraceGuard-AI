"""Client for Nebius Token Factory's OpenAI-compatible chat completions API."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
# NVIDIA's flagship strong model serving as production fallback
DEFAULT_FALLBACK_MODEL = "nvidia/Nemotron-3-Ultra-550b-a55b"

# Models deprecating on Token Factory Serverless endpoints by November 9, 2026:
DEPRECATED_MODELS = {
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "zai-org/GLM-5.1",
    "deepseek-ai/DeepSeek-V4-Pro",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "deepseek-ai/DeepSeek-V4.1-Flash",
    "Qwen/Qwen3.5-397B-A17B",
    "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "moonshotai/Kimi-K2.6",
    "moonshotai/Kimi-K2.7-Code",
    "openbmb/MiniCPM-V-4_5",
}

# USD per million tokens (input, output), from the public Token Factory model catalog
# (https://tokenfactory.nebius.com/model-catalog.md, retrieved 2026-10-25).
PRICING = {
    "nvidia/nemotron-3-super-120b-a12b": (0.30, 0.90),
    "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
    "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
    "nvidia/Nemotron-3.5-Super-VL": (0.30, 0.90),
}


class NebiusError(RuntimeError):
    pass


class NebiusNotConfigured(NebiusError):
    pass


@dataclass
class Completion:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    attempts: int
    raw_model_field: str = ""
    reasoning: str = ""

    @property
    def cost_usd(self) -> float:
        price_in, price_out = PRICING.get(self.model, (0.0, 0.0))
        return (self.prompt_tokens * price_in + self.completion_tokens * price_out) / 1_000_000


@dataclass
class NebiusClient:
    api_key: str | None = field(default_factory=lambda: os.environ.get("NEBIUS_API_KEY"))
    base_url: str = field(
        default_factory=lambda: os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE_URL)
    )
    model: str = field(default_factory=lambda: os.environ.get("TRACEGUARD_MODEL", DEFAULT_MODEL))
    fallback_model: str | None = field(
        default_factory=lambda: os.environ.get("TRACEGUARD_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)
    )
    timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("TRACEGUARD_TIMEOUT_S", "120"))
    )
    max_retries: int = 2
    transport: httpx.BaseTransport | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client(self) -> httpx.Client:
        if not self.api_key:
            raise NebiusNotConfigured("NEBIUS_API_KEY is not set")
        return httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(self.timeout_s, connect=15.0),
            transport=self.transport,
        )

    def list_models(self) -> list[str]:
        with self._client() as client:
            resp = client.get("models")
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        json_mode: bool = True,
        model: str | None = None,
        allow_fallback: bool = True,
    ) -> Completion:
        target_model = model or self.model
        body: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        last_error = ""
        start = time.perf_counter()
        with self._client() as client:
            for attempt in range(1, self.max_retries + 2):
                try:
                    resp = client.post("chat/completions", json=body)
                except httpx.TimeoutException:
                    last_error = f"timeout after {self.timeout_s}s"
                except httpx.TransportError as exc:
                    last_error = f"transport error: {exc}"
                else:
                    if resp.status_code == 400 and "response_format" in body:
                        # Some deployments reject response_format; retry once without it.
                        body.pop("response_format")
                        last_error = f"400 with response_format: {resp.text[:200]}"
                        continue
                    if resp.status_code in (429, 500, 502, 503, 504):
                        last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    elif resp.status_code >= 400:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                        # Fatal client error (e.g. 404/410/400 model deprecated or invalid), do not retry same model
                        break
                    else:
                        return self._parse(resp.json(), start, attempt, model_name=target_model)
                if attempt <= self.max_retries:
                    time.sleep(min(2**attempt, 8))

        if allow_fallback and self.fallback_model and self.fallback_model != target_model:
            try:
                return self.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    model=self.fallback_model,
                    allow_fallback=False,
                )
            except NebiusError as fb_exc:
                raise NebiusError(
                    f"Token Factory request failed for primary '{target_model}' ({last_error}) "
                    f"and fallback '{self.fallback_model}' ({fb_exc})"
                ) from fb_exc

        raise NebiusError(f"Token Factory request failed after retries: {last_error}")

    def _parse(
        self, data: dict[str, Any], start: float, attempts: int, model_name: str | None = None
    ) -> Completion:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise NebiusError(f"Unexpected response shape: {json.dumps(data)[:300]}") from exc
        usage = data.get("usage") or {}
        return Completion(
            content=message.get("content") or "",
            reasoning=message.get("reasoning_content") or "",
            model=model_name or self.model,
            raw_model_field=data.get("model", ""),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=(time.perf_counter() - start) * 1000,
            attempts=attempts,
        )


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first top-level JSON object out of a model response."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        return json.loads(fenced.group(1))
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in response")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unterminated JSON object in response")
