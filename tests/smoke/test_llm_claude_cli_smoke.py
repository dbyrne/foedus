"""Opt-in real-`claude -p` smoke test for ClaudeCLIClient.

NOT part of the default CI signal: requires FOEDUS_LLM_SMOKE=1 AND a
working `claude` CLI logged into a claude.ai subscription (this makes ONE
real subprocess call and spends subscription capacity, zero API dollars).

Run manually:
    FOEDUS_LLM_SMOKE=1 pytest tests/smoke/test_llm_claude_cli_smoke.py -s

It verifies the subscription-auth path end to end: a real completion comes
back non-empty via the CLI, without an ANTHROPIC_API_KEY in scope.
"""

from __future__ import annotations

import os
import shutil
import time

import pytest

from foedus.agents.llm.client import ClaudeCLIClient

pytestmark = pytest.mark.skipif(
    os.environ.get("FOEDUS_LLM_SMOKE") != "1",
    reason="opt-in only: set FOEDUS_LLM_SMOKE=1 (and a logged-in `claude` CLI) to run",
)


def test_one_real_claude_cli_call_returns_nonempty() -> None:
    if shutil.which("claude") is None:
        pytest.skip("no `claude` CLI on PATH")

    client = ClaudeCLIClient(model=os.environ.get("FOEDUS_LLM_MODEL", "sonnet"))
    t0 = time.monotonic()
    out = client.complete(
        system="You are a terse test harness. Follow the user instruction literally.",
        user="Reply with exactly the single word: PONG",
    )
    dt = time.monotonic() - t0

    print(
        f"\n[claude-cli smoke] model={client.model} latency={dt:.1f}s "
        f"reply={out.strip()[:60]!r}"
    )
    assert out.strip(), "expected a non-empty completion from claude -p"
