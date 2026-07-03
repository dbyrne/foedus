"""Opt-in real-Ollama smoke test for LLMDiplomat (First Light §7/§8).

NOT part of the default CI signal: requires FOEDUS_LLM_SMOKE=1 AND a
reachable local Ollama server (OLLAMA_HOST, default localhost:11434).
Runs ONE real game end-to-end and reports the parse-fail rate -- the
design brief requires that rate be measured and reported, never
silently ignored, even when it's high on a small local model.

Run manually:
    OLLAMA_HOST=http://localhost:11434 FOEDUS_LLM_SMOKE=1 \
        pytest tests/smoke/test_llm_diplomat_ollama_smoke.py -s
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("FOEDUS_LLM_SMOKE") != "1",
    reason="opt-in only: set FOEDUS_LLM_SMOKE=1 (and a reachable Ollama) to run",
)


def _ollama_reachable(host: str) -> bool:
    try:
        import httpx
        r = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def test_one_real_ollama_game_reports_parse_fail_rate() -> None:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not _ollama_reachable(host):
        pytest.skip(f"no Ollama server reachable at {host}")

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import foedus_llm_diplomat_run as harness

    sweep, telemetry, final_state, agent = harness.run_one_llm_game(
        game_id=0, seed=1, llm_seat=0,
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=8,
    )

    n = telemetry["n_decisions"]
    fails = telemetry["parse_fail_count"]
    rate = fails / n if n else 1.0
    print(
        f"\n[llm-diplomat smoke] model={os.environ.get('FOEDUS_LLM_MODEL', '(default)')} "
        f"n_decisions={n} parse_fail_count={fails} parse_fail_rate={rate:.1%}"
    )

    assert final_state.is_terminal()
    assert n > 0
    if rate > 0.15:
        print(
            f"[llm-diplomat smoke] WARNING: parse-fail rate {rate:.1%} exceeds "
            f"the 15% design threshold -- consider few-shot prompting, JSON "
            f"mode, or a larger local model."
        )
