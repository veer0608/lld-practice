"""A thin client for the one model call this platform makes.

Kept behind a `LLMClient` protocol with exactly one method, so the evaluator
above it is testable without a network and swapping provider is a new class.

Two hard-won rules are baked in, both about free-tier quota:

* never pin a `-latest` alias. An alias repoints to whatever is newest and the
  newest model carries the smallest allowance, so the same code can lose most
  of its daily budget overnight with no change on our side.
* a 429 covers two unrelated things. A per-minute burst clears in seconds; a
  per-day ceiling does not clear until tomorrow. So the branch reads the body,
  never the status code alone. It is deliberately asymmetric: only a body that
  names a per-day quota is treated as a wall and moves to the next model.
  Anything else, including a 429 that names no quota at all, is retried, because
  waiting a few seconds to find out is cheaper than abandoning a run over a blip.
"""

from __future__ import annotations

import os
import random
import re
import time
from pathlib import Path
from typing import Protocol

import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Pinned ids, in the order they are tried. Free-tier quota is per model, so a
# 429 on one says nothing about the next.
MODELS: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it",
    "gemini-3-flash-preview",
)

RETRY_STATUSES = {500, 502, 503, 504}


class LLMUnavailable(RuntimeError):
    """Every model in the ladder refused. The caller should degrade, not crash."""


class LLMClient(Protocol):
    """One method, so a fake is three lines."""

    def complete(self, prompt: str) -> str:  # pragma: no cover - protocol
        ...


def load_api_key() -> str | None:
    """Read GEMINI_API_KEY from the environment, then from a local .env.

    Env wins, so a deployment never depends on a file being present.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


class GeminiClient:
    """Walks the pinned ladder, retries what is worth retrying, gives up loudly."""

    def __init__(
        self,
        api_key: str | None = None,
        models: tuple[str, ...] = MODELS,
        timeout: float = 45.0,
        max_retries: int = 4,
    ) -> None:
        self.api_key = api_key or load_api_key()
        self.models = models
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMUnavailable("No GEMINI_API_KEY configured.")

        failures: list[str] = []
        for model in self.models:
            try:
                return self._call_model(model, prompt)
            except LLMUnavailable as exc:
                failures.append(str(exc))
        raise LLMUnavailable(" | ".join(failures))

    def _call_model(self, model: str, prompt: str) -> str:
        url = GEMINI_URL.format(model=model)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
        }
        last = ""
        for attempt in range(self.max_retries):
            try:
                response = httpx.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                last = "{}: transport error {}".format(model, exc)
                self._sleep(attempt)
                continue

            if response.status_code < 400:
                return self._text_from(response.json())

            body = response.text
            detail = body.strip().replace("\n", " ")[:200]

            if response.status_code == 429:
                if self._is_daily_wall(body):
                    raise LLMUnavailable(
                        "{}: daily quota exhausted, {}".format(model, detail)
                    )
                # Per-minute or unnamed. Both are worth waiting on: waiting a few
                # seconds to find out is cheap, guessing wrong loses the call.
                last = "{}: rate limited, {}".format(model, detail)
                self._sleep(attempt)
                continue

            if response.status_code in RETRY_STATUSES:
                last = "{}: {} {}".format(model, response.status_code, detail)
                self._sleep(attempt)
                continue

            # 400/401/403/404 and friends. Waiting changes nothing.
            raise LLMUnavailable("{}: {} {}".format(model, response.status_code, detail))

        raise LLMUnavailable(last or "{}: retries exhausted".format(model))

    @staticmethod
    def _is_daily_wall(body: str) -> bool:
        per_day = re.search(r"PerDay|per day|requests per day|RPD", body, re.IGNORECASE)
        return bool(per_day)

    def _sleep(self, attempt: int) -> None:
        time.sleep(min(8.0, 1.5 * (2**attempt)) * (0.7 + random.random() * 0.6))

    @staticmethod
    def _text_from(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMUnavailable("Model returned no candidates: " + str(data)[:200])
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not text.strip():
            raise LLMUnavailable("Model returned an empty response.")
        return text
