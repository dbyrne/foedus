"""Pluggable LLM backends for LLM-driven agents.

`FOEDUS_LLM_BACKEND` selects the backend for `make_client_from_env()`:
"ollama" (default, free, local), "claude" (anthropic SDK / API key --
opt-in "ceiling" backend, costs tokens), or "claude-cli" (the Claude Code
CLI in headless print mode, using the machine's claude.ai SUBSCRIPTION
auth -- zero API dollars). `FOEDUS_LLM_MODEL` overrides the model id for
any of them. `OLLAMA_HOST` / `ANTHROPIC_API_KEY` are the usual
per-backend env vars; the claude-cli backend needs neither, and takes an
optional `FOEDUS_CLAUDE_CLI_BIN` override for the `claude` executable path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Protocol, runtime_checkable


_DEFAULT_CLI_TIMEOUT = 300.0


def _resolve_cli_timeout(explicit: float | None) -> float:
    """Resolve the per-call `claude -p` timeout: an explicit constructor arg
    wins, else `FOEDUS_LLM_CLI_TIMEOUT` (seconds), else the default 300s.

    A missing / empty / non-numeric / non-positive env value falls back to the
    default rather than raising -- a bad timeout must never silently make every
    call fail instantly. (PR #37's 180s handicap is now opt-in via the env var,
    which the paired cross-game experiment sets to stay comparable.)
    """
    if explicit is not None:
        return explicit
    raw = os.environ.get("FOEDUS_LLM_CLI_TIMEOUT")
    if raw is None or not raw.strip():
        return _DEFAULT_CLI_TIMEOUT
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_CLI_TIMEOUT
    return val if val > 0 else _DEFAULT_CLI_TIMEOUT


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

    Concurrency isolation (parallel_seats): several seats' `claude -p`
    subprocesses can run at the SAME time. Each `complete()` call therefore
    runs in its OWN freshly-created temp dir (a unique subdir of the neutral
    base, removed after the call) and carries its OWN unique ``--session-id``.
    Two concurrent calls sharing a cwd would collide on the CLI's cwd-keyed
    project state (``~/.claude/projects/<slug>/``); a shared session id would
    collide on session identity. Per-call isolation removes both races. The
    ``ANTHROPIC_API_KEY`` / provider-routing strip in ``_subprocess_env`` is
    likewise recomputed per call, so subscription auth holds on every
    concurrent path (nothing here is memoized on the shared instance).

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
        timeout: float | None = None,
    ) -> None:
        self.model = model or os.environ.get("FOEDUS_LLM_MODEL") or "sonnet"
        self.binary = (
            binary or os.environ.get("FOEDUS_CLAUDE_CLI_BIN") or "claude"
        )
        # None -> resolved to a neutral system temp dir at call time (kept
        # lazy so construction has no filesystem side effects, which keeps
        # tests hermetic).
        self._cwd = cwd
        # An explicit `timeout=` wins; else FOEDUS_LLM_CLI_TIMEOUT; else 300s.
        self.timeout = _resolve_cli_timeout(timeout)
        self._argv_logged = False

    @property
    def cwd(self) -> str:
        """The neutral BASE dir. Each `complete()` call runs in a fresh unique
        subdir of this (created + removed per call) so concurrent calls never
        share a working directory."""
        return self._cwd or tempfile.gettempdir()

    def _build_argv(self, system: str, session_id: str) -> list[str]:
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
            # Don't persist a session transcript per call: with -p this seat
            # is stateless, and a many-call harness run would otherwise
            # accumulate unbounded ~/.claude/projects/*.jsonl files.
            "--no-session-persistence",
            # A unique session id per call (the "client id"): even under
            # concurrency no two invocations share a session identity.
            "--session-id",
            session_id,
            "--system-prompt",
            system,
        ]

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        # Force the first-party subscription (claude.ai OAuth) path: never
        # let a (credit-less) API key / bearer token shadow it, nor a
        # provider-routing override send the seat to Bedrock/Vertex.
        for var in (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
        ):
            env.pop(var, None)
        return env

    def _log_invocation_once(self, cwd_base: str) -> None:
        if self._argv_logged:
            return
        self._argv_logged = True
        # Log the invocation *shape* once per client (not per call) for
        # reproducibility; the long, per-call system/user text is redacted, and
        # the per-call cwd subdir + session id are shown as placeholders (they
        # vary per call, so the logged line stays call-invariant).
        # A multi-seat run has one client per seat, so it emits one line per
        # seat -- still "not per call", and it labels each seat's invocation.
        template = self._build_argv("<SYSTEM_PROMPT>", "<SESSION_ID>")
        print(
            f"[ClaudeCLIClient] argv={template!r} cwd_base={cwd_base!r} "
            f"timeout={self.timeout}s (per call: unique cwd subdir + session id; "
            f"user prompt via stdin; API-key/provider-routing env stripped "
            f"-> subscription auth)",
            file=sys.stderr,
            flush=True,
        )

    def complete(self, system: str, user: str) -> str:
        # A unique session id ("client id") and a fresh isolated working dir per
        # call, so concurrent `claude -p` invocations never share session
        # identity or cwd-keyed CLI state (see the class docstring).
        session_id = str(uuid.uuid4())
        argv = self._build_argv(system, session_id)
        base = self.cwd
        self._log_invocation_once(base)
        # The base must exist for per-call mkdtemp. The default base (system
        # tempdir) always does; create an explicitly-configured base if missing
        # so a misconfigured cwd fails loud here rather than silently degrading
        # every call to a swallowed FileNotFoundError -> an all-Hold seat.
        os.makedirs(base, exist_ok=True)
        call_cwd = tempfile.mkdtemp(prefix="foedus-seat-", dir=base)
        try:
            result = subprocess.run(
                argv,
                input=user,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                cwd=call_cwd,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"claude -p timed out after {self.timeout}s"
            ) from e
        finally:
            # Never leak a temp dir per call, even on timeout / error.
            shutil.rmtree(call_cwd, ignore_errors=True)
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
