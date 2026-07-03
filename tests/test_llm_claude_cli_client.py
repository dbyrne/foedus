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

import subprocess
import tempfile

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

    client = ClaudeCLIClient(cwd="/tmp/neutral-dir")
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


def test_explicit_cwd_is_passed_to_subprocess(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))
    ClaudeCLIClient(cwd="/tmp/neutral-dir").complete("s", "u")
    assert captured["kwargs"]["cwd"] == "/tmp/neutral-dir"


def test_default_cwd_is_a_neutral_tempdir_never_the_repo(monkeypatch) -> None:
    captured: dict = {}
    _patch_run(monkeypatch, captured, _completed(stdout="ok"))
    ClaudeCLIClient().complete("s", "u")  # cwd defaulted
    cwd = captured["kwargs"]["cwd"]
    assert cwd  # set, never None
    # A neutral system temp dir — not the foedus repo, so no repo CLAUDE.md
    # and no engine source is reachable from the seat.
    assert cwd == tempfile.gettempdir()


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
