"""Pluggable LLM backends for LLM-driven agents.

`FOEDUS_LLM_BACKEND` selects the backend for `make_client_from_env()`:
"ollama" (default, free, local) or "claude" (opt-in "ceiling" backend,
costs tokens). `FOEDUS_LLM_MODEL` overrides the model id for either.
`OLLAMA_HOST` / `ANTHROPIC_API_KEY` are the usual per-backend env vars.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's raw text completion for one turn's prompt."""
        ...


class StubLLMClient:
    """Deterministic scripted client for tests — no network, no model.

    `responses` is consumed in order, one string per `complete()` call.
    Running out of scripted responses raises rather than silently
    reusing a stale one, so a test's call count is part of its contract.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self._responses:
            raise RuntimeError(
                "StubLLMClient: no scripted response left for call "
                f"#{len(self.calls)}"
            )
        return self._responses.pop(0)


class OllamaClient:
    """HTTP client for a local Ollama server (`/api/chat`). Default
    backend — free, no API key, unlimited local play."""

    def __init__(self, model: str | None = None, host: str | None = None,
                 timeout: float = 120.0) -> None:
        self.model = model or os.environ.get("FOEDUS_LLM_MODEL", "llama3.1")
        self.host = (
            host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        ).rstrip("/")
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        import httpx

        r = httpx.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]


class ClaudeClient:
    """anthropic SDK client — opt-in "ceiling" backend. Costs tokens.

    The `anthropic` import is lazy (only on `complete()`, not
    construction) so local-only Ollama runs need neither the package
    nor an API key installed/set.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 max_tokens: int = 2048) -> None:
        self.model = model or os.environ.get(
            "FOEDUS_LLM_MODEL", "claude-haiku-4-5-20251001"
        )
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "ClaudeClient requires the `anthropic` package: "
                "pip install anthropic"
            ) from e
        client = anthropic.Anthropic(api_key=self._api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in resp.content if block.type == "text"
        )


_BACKENDS = {"ollama": OllamaClient, "claude": ClaudeClient}


def make_client_from_env() -> LLMClient:
    backend = os.environ.get("FOEDUS_LLM_BACKEND", "ollama").strip().lower()
    cls = _BACKENDS.get(backend)
    if cls is None:
        raise ValueError(
            f"unknown FOEDUS_LLM_BACKEND={backend!r}; "
            f"expected one of {sorted(_BACKENDS)}"
        )
    return cls()
