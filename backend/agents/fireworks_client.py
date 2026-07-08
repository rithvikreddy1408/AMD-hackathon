"""Fireworks API client with a deterministic mock mode for offline testing.

Real mode: POSTs to Fireworks chat completions, expects the model to return
a single JSON object per the caller's schema (enforced via prompt, parsed
with a best-effort JSON extraction + one retry on parse failure).

Mock mode: no network call. Runs a small deterministic heuristic over the
structured `context` passed alongside the prompt, so the full debate/judge
pipeline is testable end-to-end without an API key. Same call signature as
real mode, so swapping in a key later requires no caller changes.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()

FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/chat/completions"


class FireworksClient:
    def __init__(self, model: str, mock: bool = False, api_key: str | None = None, timeout: int = 60):
        self.model = model
        self.mock = mock or not (api_key or os.getenv("FIREWORKS_API_KEY"))
        self.api_key = api_key or os.getenv("FIREWORKS_API_KEY")
        self.timeout = timeout
        self.call_count = 0
        self.total_seconds = 0.0

    def chat_json(self, system: str, user: str, mock_fn=None, mock_context=None, max_tokens: int = 400) -> dict:
        start = time.perf_counter()
        if self.mock:
            if mock_fn is None:
                raise RuntimeError("mock mode active but no mock_fn provided")
            result = mock_fn(mock_context)
        else:
            result = self._call_real(system, user, max_tokens)
        elapsed = time.perf_counter() - start
        self.call_count += 1
        self.total_seconds += elapsed
        return result

    def _call_real(self, system: str, user: str, max_tokens: int) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        last_error = None
        for attempt in range(2):
            try:
                response = requests.post(
                    FIREWORKS_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"]
                return self._extract_json(text)
            except (requests.exceptions.RequestException, ValueError) as exc:
                last_error = exc
        raise last_error

    @staticmethod
    def _extract_json(text: str) -> dict:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"no JSON object found in model output: {text[:200]}")
        return json.loads(match.group(0))

    def stats(self) -> dict:
        avg_ms = (self.total_seconds / self.call_count * 1000) if self.call_count else 0.0
        return {"model": self.model, "mock": self.mock, "calls": self.call_count, "avg_ms_per_call": round(avg_ms, 3)}
