"""Tests for the opt-in per-turn spectate JSONL emitter (foedus/spectate/emit.py).

Default OFF (no callback wired) must leave harness output byte-identical;
when wired via FOEDUS_SPECTATE_DIR (or an explicit spectate_dir), each
resolved turn appends one JSON line to spectate_game{game_id}.jsonl.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat
from foedus.agents.random_agent import RandomAgent
from foedus.core import GameConfig
from foedus.loop import play_game
from foedus.spectate.emit import spectate_turn_emitter

import foedus_llm_diplomat_run as harness


def test_spectate_turn_emitter_writes_one_line_per_turn(tmp_path) -> None:
    cfg = GameConfig(num_players=2, seed=7, max_turns=3, build_period=999)
    agents = {0: RandomAgent(seed=0), 1: RandomAgent(seed=1)}
    emit = spectate_turn_emitter(tmp_path, game_id=5)

    final = play_game(agents, config=cfg, on_turn_resolved=emit)

    out = tmp_path / "spectate_game5.jsonl"
    assert out.exists()
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    for i, rec in enumerate(records):
        assert rec["game_id"] == 5
        assert rec["turn"] == i + 1
        assert "stances" in rec and "0" in rec["stances"] and "1" in rec["stances"]
        assert "intents" in rec
        assert "orders" in rec and "0" in rec["orders"] and "1" in rec["orders"]
        assert "scores" in rec
        assert "eliminated" in rec
    assert records[-1]["scores"] == {str(k): v for k, v in final.scores.items()}


def test_spectate_turn_emitter_orders_are_wire_serializable(tmp_path) -> None:
    """Orders must round-trip through the same tagged-union shape wire.py
    uses ({"type": "Hold"|"Move"|"Support", ...}), not raw dataclass reprs."""
    cfg = GameConfig(num_players=2, seed=7, max_turns=1, build_period=999)
    agents = {0: RandomAgent(seed=0), 1: RandomAgent(seed=1)}
    emit = spectate_turn_emitter(tmp_path, game_id=0)
    play_game(agents, config=cfg, on_turn_resolved=emit)

    rec = json.loads((tmp_path / "spectate_game0.jsonl").read_text().strip())
    for seat_orders in rec["orders"].values():
        for order in seat_orders.values():
            assert "type" in order and order["type"] in ("Hold", "Move", "Support")


def test_spectate_dir_none_writes_nothing(tmp_path) -> None:
    """spectate_turn_emitter is only ever constructed when a dir is given;
    play_game with on_turn_resolved=None (the default) must not touch disk."""
    cfg = GameConfig(num_players=2, seed=7, max_turns=2, build_period=999)
    agents = {0: RandomAgent(seed=0), 1: RandomAgent(seed=1)}
    play_game(agents, config=cfg)
    assert list(tmp_path.iterdir()) == []


def _stub_factory(n_turns: int):
    def factory():
        responses = [
            json.dumps({"press": {"stance": {}, "intents": []},
                        "pacts": {"propose": [], "accept": []}}),
            json.dumps({"orders": {}}),
        ] * n_turns
        return LLMDiplomat(client=StubLLMClient(responses))
    return factory


def test_harness_spectate_dir_env_var_opts_in(tmp_path, monkeypatch) -> None:
    spectate_dir = tmp_path / "spectate"
    monkeypatch.setenv("FOEDUS_SPECTATE_DIR", str(spectate_dir))
    sweep, telemetry, final_state, agent = harness.run_one_llm_game(
        game_id=3, seed=1, llm_seat=0,
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=2,
        llm_agent_factory=_stub_factory(2),
    )
    out = spectate_dir / "spectate_game3.jsonl"
    assert out.exists()
    lines = out.read_text().strip().splitlines()
    assert len(lines) == final_state.turn
    for line in lines:
        json.loads(line)


def test_harness_without_spectate_env_var_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_SPECTATE_DIR", raising=False)
    harness.run_one_llm_game(
        game_id=4, seed=1, llm_seat=0,
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=2,
        llm_agent_factory=_stub_factory(2),
    )
    assert not (tmp_path / "spectate_game4.jsonl").exists()


def test_harness_output_byte_identical_with_and_without_spectate_dir(monkeypatch) -> None:
    """Turning the emitter on must not perturb the harness's own recorded
    sweep/telemetry (same seed, same stub responses -> same numbers)."""
    monkeypatch.delenv("FOEDUS_SPECTATE_DIR", raising=False)
    sweep_off, telemetry_off, state_off, _ = harness.run_one_llm_game(
        game_id=0, seed=1, llm_seat=0,
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=2,
        llm_agent_factory=_stub_factory(2),
    )

    def on_via_tmp(tmp_dir):
        monkeypatch.setenv("FOEDUS_SPECTATE_DIR", str(tmp_dir))
        return harness.run_one_llm_game(
            game_id=0, seed=1, llm_seat=0,
            heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
            max_turns=2,
            llm_agent_factory=_stub_factory(2),
        )

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sweep_on, telemetry_on, state_on, _ = on_via_tmp(d)

    assert sweep_off == sweep_on
    assert telemetry_off == telemetry_on
    assert state_off.scores == state_on.scores
