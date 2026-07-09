"""Tests for ClaudeCLIClient — the subscription-Claude (`claude -p`) backend.

No real CLI calls here: `subprocess.run` is mocked in every test. The
opt-in real smoke test lives in tests/smoke/test_llm_claude_cli_smoke.py,
env-gated exactly like the Ollama one, so CI never shells out to `claude`.

The load-bearing behaviours these tests pin:

- backend selection wiring (`FOEDUS_LLM_BACKEND=claude-cli`),
- argv shape: headless print, plain text, model pinned, system prompt
  honored, NO tool use, customizations off (so the seat answers from the
  prompt alone), user prompt via stdin, neutral cwd (never the repo),
- SUBSCRIPTION auth: ANTHROPIC_API_KEY is stripped from the subprocess env
  so a credit-less API key never shadows the claude.ai OAuth login,
- failure paths: timeout and non-zero exit both raise (the LLMDiplomat's
  `_complete` catches these and degrades to a safe Hold fallback),
- the invocation shape is logged once, not once per call.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import uuid

import pytest

from foedus.agents.llm import client as client_module
from foedus.agents.llm.client import (
    ClaudeCLIClient,
    LLMClient,
    make_client_from_env,
)


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _patch_run(monkeypatch, captured: dict, result=None, side_effect=None):
    """Patch the module's subprocess.run, recording argv + kwargs."""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        if side_effect is not None:
            raise side_effect
        return result if result is not None else _completed(stdout="ok")

    monkeypatch.setattr(client_module.subprocess, "run", fake_run)


# --- selection / construction ---------------------------------------------


def test_make_client_from_env_selects_claude_cli(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_BACKEND", "claude-cli")
    assert isinstance(make_client_from_env(), ClaudeCLIClient)


def test_claude_cli_is_a_valid_llm_client() -> None:
    assert isinstance(ClaudeCLIClient(), LLMClient)


def test_default_model_is_sonnet(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_MODEL", raising=False)
    assert ClaudeCLIClient().model == "sonnet"


def test_reads_model_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_MODEL", "opus")
    assert ClaudeCLIClient().model == "opus"


def test_explicit_model_arg_beats_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_MODEL", "opus")
    assert ClaudeCLIClient(model="haiku").model == "haiku"


# --- argv shape -----------------------------------------------------------


def test_argv_is_headless_text_pinned_and_toolless(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_MODEL", raising=False)
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))

    client = ClaudeCLIClient()  # default neutral base; argv is cwd-independent
    out = client.complete("SYSTEM_TEXT", "USER_TEXT")

    argv = captured["argv"]
    assert argv[0] == "claude"
    assert "-p" in argv  # headless print mode

    i = argv.index("--output-format")
    assert argv[i + 1] == "text"  # plain text, no JSON envelope / decoration

    i = argv.index("--model")
    assert argv[i + 1] == "sonnet"  # model pinned

    i = argv.index("--system-prompt")
    assert argv[i + 1] == "SYSTEM_TEXT"  # system prompt honored

    # No tool use: `--tools ""` disables every built-in tool.
    i = argv.index("--tools")
    assert argv[i + 1] == ""

    # Customizations off so the seat answers from the prompt alone (no
    # CLAUDE.md / hooks / MCP servers / skills). This is also what keeps
    # .nexus-mcp.json out of scope entirely.
    assert "--safe-mode" in argv

    # No on-disk session transcript per call: a many-call harness run would
    # otherwise accumulate unbounded ~/.claude/projects/*.jsonl files.
    # (--no-session-persistence only works together with -p, which we use.)
    assert "--no-session-persistence" in argv

    assert out == "ok"


def test_user_prompt_goes_via_stdin_not_argv(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))

    ClaudeCLIClient().complete("SYS", "the long user prompt")

    assert captured["kwargs"]["input"] == "the long user prompt"
    # The user text must not be smuggled in as an argv token.
    assert "the long user prompt" not in captured["argv"]


def test_argv_uses_configured_binary(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))
    ClaudeCLIClient(binary="/opt/claude").complete("s", "u")
    assert captured["argv"][0] == "/opt/claude"


def test_binary_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_CLAUDE_CLI_BIN", "/usr/local/bin/claude")
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))
    ClaudeCLIClient().complete("s", "u")
    assert captured["argv"][0] == "/usr/local/bin/claude"


# --- neutral cwd (no repo-context / engine-source leak) -------------------


def test_explicit_cwd_is_used_as_the_base_for_a_per_call_subdir(
    monkeypatch, tmp_path
) -> None:
    # An explicit cwd is now the BASE under which each call gets its OWN fresh
    # subdir (concurrency isolation), rather than the shared cwd itself.
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))
    base = str(tmp_path)
    ClaudeCLIClient(cwd=base).complete("s", "u")
    cwd = captured["kwargs"]["cwd"]
    assert cwd.startswith(base)  # under the configured base
    assert cwd != base           # ...but its own isolated subdir, not the base


def test_default_cwd_is_a_neutral_tempdir_never_the_repo(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))
    ClaudeCLIClient().complete("s", "u")  # cwd defaulted
    cwd = captured["kwargs"]["cwd"]
    assert cwd  # set, never None
    # A fresh per-call subdir of the system temp dir — never the foedus repo, so
    # no repo CLAUDE.md / engine source is reachable, and (see the isolation
    # tests below) two concurrent calls never share a cwd.
    assert cwd.startswith(tempfile.gettempdir())
    assert cwd != tempfile.gettempdir()


# --- per-call isolation so concurrent `claude -p` calls never collide -------
#
# Under parallel_seats several seats' `claude -p` subprocesses run at the SAME
# time. Two concurrent invocations that shared a cwd would collide on the CLI's
# cwd-keyed project state (~/.claude/projects/<slug>/), and a shared session id
# would collide on session identity. So every `complete()` call must run in its
# OWN fresh temp dir and carry its OWN unique --session-id (the "client id").


def _patch_run_record_all(monkeypatch, records, *, barrier=None, result=None):
    """Patch subprocess.run to append one record per call: argv, kwargs, the
    cwd, and whether that cwd existed as a real dir AT call time. An optional
    Barrier releases only when every concurrent caller is inside its call —
    proving real overlap rather than accidental serialization."""
    lock = threading.Lock()

    def fake_run(argv, **kwargs):
        cwd = kwargs.get("cwd")
        cwd_existed = bool(cwd) and os.path.isdir(cwd)
        if barrier is not None:
            barrier.wait()
        with lock:
            records.append(
                {"argv": argv, "kwargs": kwargs, "cwd": cwd,
                 "cwd_existed": cwd_existed}
            )
        return result if result is not None else _completed(stdout="ok")

    monkeypatch.setattr(client_module.subprocess, "run", fake_run)


def _session_id(argv) -> str:
    return argv[argv.index("--session-id") + 1]


def test_each_call_carries_a_unique_valid_session_id(monkeypatch) -> None:
    records: list = []
    _patch_run_record_all(monkeypatch, records)
    c = ClaudeCLIClient()
    c.complete("s", "u1")
    c.complete("s", "u2")
    ids = [_session_id(r["argv"]) for r in records]
    assert ids[0] != ids[1]         # a distinct client id per call
    for sid in ids:
        uuid.UUID(sid)              # a real UUID (raises ValueError otherwise)


def test_each_call_runs_in_its_own_isolated_cwd(monkeypatch) -> None:
    records: list = []
    _patch_run_record_all(monkeypatch, records)
    c = ClaudeCLIClient()
    c.complete("s", "u1")
    c.complete("s", "u2")
    cwds = [r["cwd"] for r in records]
    assert cwds[0] != cwds[1]                       # a fresh dir per call
    assert all(r["cwd_existed"] for r in records)   # it really existed at call time
    for cwd in cwds:
        assert cwd.startswith(tempfile.gettempdir())  # neutral, never the repo


def test_per_call_cwd_is_removed_after_the_call(monkeypatch) -> None:
    """A many-call harness run must not leak one temp dir per call."""
    records: list = []
    _patch_run_record_all(monkeypatch, records)
    ClaudeCLIClient().complete("s", "u")
    assert not os.path.isdir(records[0]["cwd"])  # cleaned up


def test_per_call_cwd_is_removed_even_on_failure(monkeypatch) -> None:
    """The per-call temp dir is cleaned up even when the call raises."""
    records: list = []
    _patch_run_record_all(monkeypatch, records,
                          result=_completed(returncode=2, stderr="boom"))
    with pytest.raises(RuntimeError):
        ClaudeCLIClient().complete("s", "u")
    assert not os.path.isdir(records[0]["cwd"])


def test_per_call_cwd_is_removed_on_timeout(monkeypatch) -> None:
    """...and on the timeout path specifically (the `finally` runs before the
    RuntimeError re-raise) — 'removed on every path incl. timeout'."""
    captured: dict = {}
    _patch_run(monkeypatch, captured,
               side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=1))
    with pytest.raises(RuntimeError):
        ClaudeCLIClient(timeout=1).complete("s", "u")
    assert not os.path.isdir(captured["kwargs"]["cwd"])  # cleaned up on timeout


def test_missing_explicit_cwd_base_is_created_not_silently_degraded(
    monkeypatch, tmp_path
) -> None:
    """A configured-but-not-yet-existing cwd base is created, so a misconfig
    can't degrade every call to a swallowed FileNotFoundError -> all-Hold seat."""
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))
    base = tmp_path / "does" / "not" / "exist" / "yet"
    assert not base.exists()
    ClaudeCLIClient(cwd=str(base)).complete("s", "u")
    assert base.is_dir()  # created rather than raising FileNotFoundError
    assert captured["kwargs"]["cwd"].startswith(str(base))  # per-call subdir


def test_concurrent_calls_are_fully_isolated(monkeypatch) -> None:
    """THE shared-state isolation proof: N seats' calls run genuinely at once
    (a Barrier forces true overlap), and each gets a DISTINCT cwd + session id,
    a per-call env with the credit-less API key stripped, and its temp dir
    really coexisting during the overlap — no cross-call clobbering."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-credit-less")
    n = 4
    records: list = []
    barrier = threading.Barrier(n, timeout=10)
    _patch_run_record_all(monkeypatch, records, barrier=barrier)
    clients = [ClaudeCLIClient() for _ in range(n)]  # one client per seat

    errors: list = []

    def call(c, i):
        try:
            c.complete("sys", f"user-{i}")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=call, args=(c, i))
               for i, c in enumerate(clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors                                    # all released -> real overlap
    assert len(records) == n
    assert len({r["cwd"] for r in records}) == n         # each call its OWN cwd
    assert len({_session_id(r["argv"]) for r in records}) == n  # ...and session id
    assert all(r["cwd_existed"] for r in records)        # dirs coexisted concurrently
    for r in records:
        assert "ANTHROPIC_API_KEY" not in r["kwargs"]["env"]  # stripped per call


# --- subscription auth (strip the credit-less API key) --------------------


def test_strips_anthropic_api_key_so_subscription_auth_is_used(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-credit-less-dummy")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "bearer-dummy")
    # Provider-routing overrides would send the seat off the first-party
    # subscription entirely; they must not survive into the subprocess.
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))

    ClaudeCLIClient().complete("s", "u")

    env = captured["kwargs"]["env"]
    # The API-key / provider-routing overrides are removed → the CLI falls
    # back to the machine's claude.ai subscription OAuth
    # (~/.claude/.credentials.json).
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "CLAUDE_CODE_USE_BEDROCK" not in env
    assert "CLAUDE_CODE_USE_VERTEX" not in env
    # ...but the rest of the environment is preserved (PATH, HOME, etc.).
    assert "PATH" in env


# --- output passthrough ---------------------------------------------------


def test_text_passthrough(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="the model's raw text\n"))
    assert ClaudeCLIClient().complete("s", "u") == "the model's raw text\n"


# --- failure paths (diplomat degrades these to a safe Hold) ---------------


def test_timeout_raises(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(
        monkeypatch,
        captured,
        side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=180),
    )
    with pytest.raises(RuntimeError):
        ClaudeCLIClient(timeout=180).complete("s", "u")


def test_nonzero_exit_raises_with_stderr(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(
        monkeypatch,
        captured,
        _completed(returncode=2, stderr="kaboom from claude", stdout=""),
    )
    with pytest.raises(RuntimeError) as excinfo:
        ClaudeCLIClient().complete("s", "u")
    msg = str(excinfo.value)
    assert "kaboom from claude" in msg or "2" in msg


def test_timeout_value_is_passed_to_subprocess(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))
    ClaudeCLIClient(timeout=42.0).complete("s", "u")
    assert captured["kwargs"]["timeout"] == 42.0


# --- configurable timeout (FOEDUS_LLM_CLI_TIMEOUT, default 300) ------------
#
# PR #37 found 18% of decisions were forced Holds from `claude -p` hitting the
# old 180s client timeout. The new default is 300s to kill that handicap going
# forward; the paired cross-game experiment re-pins it to 180 via the env var.


def test_default_timeout_is_300_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_CLI_TIMEOUT", raising=False)
    assert ClaudeCLIClient().timeout == 300.0


def test_timeout_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_CLI_TIMEOUT", "180")
    assert ClaudeCLIClient().timeout == 180.0


def test_timeout_env_accepts_float(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_CLI_TIMEOUT", "90.5")
    assert ClaudeCLIClient().timeout == 90.5


def test_explicit_timeout_arg_beats_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_CLI_TIMEOUT", "180")
    assert ClaudeCLIClient(timeout=42.0).timeout == 42.0


def test_bad_timeout_env_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_CLI_TIMEOUT", "not-a-number")
    assert ClaudeCLIClient().timeout == 300.0


def test_empty_timeout_env_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_CLI_TIMEOUT", "   ")
    assert ClaudeCLIClient().timeout == 300.0


def test_nonpositive_timeout_env_falls_back_to_default(monkeypatch) -> None:
    # A zero or negative timeout would make every call fail instantly; reject it.
    for bad in ("0", "-5", "-1.5"):
        monkeypatch.setenv("FOEDUS_LLM_CLI_TIMEOUT", bad)
        assert ClaudeCLIClient().timeout == 300.0, bad


# --- argv logged once, not per call ---------------------------------------


def test_invocation_shape_logged_once_not_per_call(monkeypatch, capsys) -> None:
    _patch_run(monkeypatch, {}, _completed(stdout="ok"))
    client = ClaudeCLIClient()
    client.complete("s1", "u1")
    client.complete("s2", "u2")
    err = capsys.readouterr().err
    # Exactly one invocation-shape line for the whole client lifetime.
    assert err.count("ClaudeCLIClient") == 1
    # The redacted template records the flags without dumping the prompt.
    assert "--safe-mode" in err
    assert "u1" not in err and "u2" not in err  # no prompt text leaked


def test_logged_template_redacts_the_system_prompt(monkeypatch, capsys) -> None:
    _patch_run(monkeypatch, {}, _completed(stdout="ok"))
    ClaudeCLIClient().complete("SECRET_SYSTEM_PROMPT", "SECRET_USER_PROMPT")
    err = capsys.readouterr().err
    assert "SECRET_SYSTEM_PROMPT" not in err
    assert "SECRET_USER_PROMPT" not in err
