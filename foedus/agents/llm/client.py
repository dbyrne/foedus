"""Pluggable LLM backends for LLM-driven agents.

`FOEDUS_LLM_BACKEND` selects the backend for `make_client_from_env()`:
"ollama" (default, free, local), "claude" (anthropic SDK / API key --
opt-in "ceiling" backend, costs tokens), or "claude-cli" (the Claude Code
CLI in headless print mode, using the machine's claude.ai SUBSCRIPTION
auth -- zero API dollars). `FOEDUS_LLM_MODEL` overrides the model id for
any of them. `OLLAMA_HOST` / `ANTHROPIC_API_KEY` are the usual
per-backend env vars; the claude-cli backend needs neither.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
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


class ClaudeCLIClient:
    """Subscription-Claude backend: shells out to the Claude Code CLI in
    headless print mode (`claude -p`), one subprocess per `complete()`.

    Uses the machine's claude.ai SUBSCRIPTION auth (OAuth, read by the CLI
    from ~/.claude/.credentials.json), NOT the anthropic API key. To make
    that happen, ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN are stripped from
    the subprocess environment -- otherwise a credit-less API key set in
    the parent env shadows the subscription and every call fails with
    "Credit balance is too low". Zero API dollars either way.

    The seat is a Diplomacy player, not a coding session, so each call
    answers from the prompt alone:

    - `--safe-mode` disables every customization (CLAUDE.md auto-discovery,
      hooks, MCP servers, skills, plugins, custom agents) while keeping
      auth + model selection working. This is also what keeps the repo's
      CLAUDE.md and `.nexus-mcp.json` entirely out of scope -- we never
      read those files; safe-mode just never loads them.
    - `--tools ""` disables all built-in tools (no Bash/Read/etc.), so the
      seat cannot reach the engine source and calls stay fast.
    - `--system-prompt` fully replaces the default coding system prompt
      with the diplomat's, mapping cleanly onto the `system` argument
      (the equivalent of the SDK's `system=`), and drops the per-machine
      dynamic sections (cwd/env/git status) too.
    - cwd is a neutral temp dir, never the foedus repo, so even a
      misconfiguration can't surface repo context.

    Backend/transport failures raise (timeout, non-zero exit, `claude`
    not on PATH). The LLMDiplomat's `_complete` catches those and degrades
    to a safe Hold fallback, so a flaky CLI never crashes a game.
    """

    def __init__(
        self,
        model: str | None = None,
        *,
        binary: str | None = None,
        cwd: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        self.model = model or os.environ.get("FOEDUS_LLM_MODEL") or "sonnet"
        self.binary = (
            binary or os.environ.get("FOEDUS_CLAUDE_CLI_BIN") or "claude"
        )
        # None -> resolved to a neutral system temp dir at call time (kept
        # lazy so construction has no filesystem side effects, which keeps
        # tests hermetic).
        self._cwd = cwd
        self.timeout = timeout
        self._argv_logged = False

    @property
    def cwd(self) -> str:
        return self._cwd or tempfile.gettempdir()

    def _build_argv(self, system: str) -> list[str]:
        return [
            self.binary,
            "-p",
            "--output-format",
            "text",
            "--model",
            self.model,
            "--safe-mode",
            "--tools",
            "",
            "--system-prompt",
            system,
        ]

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        # Force the subscription (claude.ai OAuth) path: never let a
        # (credit-less) API key or bearer token shadow it.
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        return env

    def _log_invocation_once(self, cwd: str) -> None:
        if self._argv_logged:
            return
        self._argv_logged = True
        # Log the invocation *shape* once (not per call) for reproducibility;
        # the long, per-call system/user text is redacted.
        template = self._build_argv("<SYSTEM_PROMPT>")
        print(
            f"[ClaudeCLIClient] argv={template!r} cwd={cwd!r} timeout={self.timeout}s "
            f"(user prompt via stdin; ANTHROPIC_API_KEY stripped -> subscription auth)",
            file=sys.stderr,
            flush=True,
        )

    def complete(self, system: str, user: str) -> str:
        argv = self._build_argv(system)
        cwd = self.cwd
        self._log_invocation_once(cwd)
        try:
            result = subprocess.run(
                argv,
                input=user,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                cwd=cwd,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"claude -p timed out after {self.timeout}s"
            ) from e
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(
                f"claude -p exited {result.returncode}: {stderr[:500]}"
            )
        return result.stdout


_BACKENDS = {
    "ollama": OllamaClient,
    "claude": ClaudeClient,
    "claude-cli": ClaudeCLIClient,
}


def make_client_from_env() -> LLMClient:
    backend = os.environ.get("FOEDUS_LLM_BACKEND", "ollama").strip().lower()
    cls = _BACKENDS.get(backend)
    if cls is None:
        raise ValueError(
            f"unknown FOEDUS_LLM_BACKEND={backend!r}; "
            f"expected one of {sorted(_BACKENDS)}"
        )
    return cls()
