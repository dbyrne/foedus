"""Tests for scripts/foedus_llm_diplomat_run.py — the LLM-diplomat run
harness (sweep JSONL + telemetry sidecar + transcript), driven end-to-end
with StubLLMClient (deterministic, no real model, CI-able).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat

import foedus_llm_diplomat_run as harness


def _stub_factory(n_turns: int):
    def factory():
        responses = [
            json.dumps({"press": {"stance": {}, "intents": []},
                        "pacts": {"propose": [], "accept": []}}),
            json.dumps({"orders": {}}),
        ] * n_turns
        return LLMDiplomat(client=StubLLMClient(responses))
    return factory


def test_run_one_llm_game_returns_sweep_and_telemetry_records() -> None:
    sweep, telemetry, final_state, agent = harness.run_one_llm_game(
        game_id=0, seed=1, llm_seat=0,
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=2,
        llm_agent_factory=_stub_factory(2),
    )
    assert sweep["agents"][0] == "LLMDiplomat"
    assert len(sweep["agents"]) == 4
    assert len(sweep["final_scores"]) == 4
    assert "eliminated" in sweep
    assert "detente_reached" in sweep
    assert "winners" in sweep
    assert "total_turns" in sweep

    assert telemetry["game_id"] == 0
    assert telemetry["llm_seat"] == 0
    assert "betrayals" in telemetry
    assert "pact_breaches" in telemetry
    assert "reputation" in telemetry
    assert "parse_fail_count" in telemetry
    assert telemetry["n_decisions"] == len(agent.decision_log)
    assert telemetry["parse_fail_count"] == 0

    assert final_state.is_terminal()


def test_run_one_llm_game_counts_parse_failures() -> None:
    def failing_factory():
        return LLMDiplomat(client=StubLLMClient(["garbage"] * 8))
    _sweep, telemetry, _state, agent = harness.run_one_llm_game(
        game_id=1, seed=2, llm_seat=0,
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=2,
        llm_agent_factory=failing_factory,
    )
    assert telemetry["parse_fail_count"] > 0
    assert telemetry["parse_fail_count"] == sum(
        1 for r in agent.decision_log if r["fell_back"]
    )


def test_render_transcript_includes_expected_sections() -> None:
    _sweep, _telemetry, final_state, _agent = harness.run_one_llm_game(
        game_id=0, seed=1, llm_seat=0,
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=2,
        llm_agent_factory=_stub_factory(2),
    )
    text = harness.render_transcript(final_state, llm_seat=0)
    assert "Final scores" in text
    assert "Betrayals observed" in text
    assert "Pact breaches observed" in text


def test_main_writes_sweep_telemetry_and_transcript(tmp_path) -> None:
    out_dir = tmp_path / "out"
    rc = harness.main([
        "--num-games", "2", "--max-turns", "2", "--seed-offset", "5",
        "--heuristics", "GreedyHold,GreedyHold,GreedyHold",
        "--out-dir", str(out_dir),
    ], llm_agent_factory=_stub_factory(2))
    assert rc == 0

    sweep_lines = (out_dir / "sweep.jsonl").read_text().strip().splitlines()
    telemetry_lines = (out_dir / "telemetry.jsonl").read_text().strip().splitlines()
    assert len(sweep_lines) == 2
    assert len(telemetry_lines) == 2
    for line in sweep_lines:
        json.loads(line)
    for line in telemetry_lines:
        json.loads(line)

    transcripts = sorted(out_dir.glob("transcript_game*.md"))
    assert len(transcripts) >= 1
    assert transcripts[0].read_text().strip()
