"""Tests for foedus/spectate/replay.py -- View 2's per-game replay data
model, merging the transcript (stance/intents, all seats) with decision-log
derived orders/subsidy (LLM seats only) and that game's self-notes."""

from __future__ import annotations

import json

from foedus.spectate.replay import build_replay

TRANSCRIPT = """\
# Foedus LLM Diplomat transcript — LLM seats 0, 1, 2

Final scores: {0: 2.0, 1: 3.0, 2: 1.0, 3: 6.0}
Eliminated: []
Winners: [3]
Détente reached: False

## Turn 1
- p0 stance: p3=hostile
  - declared u0 -> Move(dest=9) (visible_to=public)
- p1 stance: p3=neutral
- p2 stance: (none)
- p3 stance: (none)

## Betrayals observed
(none)

## Pact breaches observed
(none)

## Final reputation (public)
- p0: 0 intent / 0 pact / 0 total
- p1: 0 intent / 0 pact / 0 total
- p2: 0 intent / 0 pact / 0 total
- p3: 0 intent / 0 pact / 0 total
"""

SWEEP_RECORD = {
    "game_id": 0, "game_index": 0, "seed": 1,
    "agents": ["LLMDiplomat", "LLMDiplomat", "LLMDiplomat", "DishonestCooperator"],
    "llm_seats": [0, 1, 2], "freerider_seats": [3],
    "identity_by_seat": ["Delta", "Echo", "Foxtrot", "Golf"],
    "total_turns": 1, "final_scores": [2.0, 3.0, 1.0, 6.0],
    "eliminated": [], "winners": [3], "detente_reached": False,
}


def test_build_replay_aligns_zero_indexed_decision_turns_with_transcript(tmp_path) -> None:
    """Decision logs stamp turn=state.turn BEFORE finalize_round increments
    it (0-indexed: 0 for the first turn); the transcript's turn labels are
    1-indexed. Turn 1's declarations must merge with the orders logged under
    decision-log turn=0, not sit orphaned as a separate "turn 0"."""
    (tmp_path / "sweep.jsonl").write_text(json.dumps(SWEEP_RECORD) + "\n")
    (tmp_path / "transcript_game0.md").write_text(TRANSCRIPT)
    (tmp_path / "decisions_game0_seat0.jsonl").write_text(
        json.dumps(_orders_record(0, 0, '{"0": {"type": "Move", "dest": 9}}')) + "\n"
    )
    replay = build_replay(tmp_path, game_id=0)
    assert [t["turn"] for t in replay["turns"]] == [1]
    turn1 = replay["turns"][0]
    assert turn1["declarations"][0]["stance"] == {3: "hostile"}
    assert turn1["orders"][0] == {"0": {"type": "Move", "dest": 9}}


def _orders_record(turn, player, orders_json):
    return {
        "turn": turn, "phase": "orders", "player": player,
        "prompt": {"system": "", "user": ""},
        "raw_response": '{"orders": %s}' % orders_json,
        "fell_back": False,
    }


def _write_fixture(tmp_path, *, with_transcript=True, with_decisions=True):
    (tmp_path / "sweep.jsonl").write_text(json.dumps(SWEEP_RECORD) + "\n")
    if with_transcript:
        (tmp_path / "transcript_game0.md").write_text(TRANSCRIPT)
    if with_decisions:
        # Decision logs are 0-indexed (state.turn read before finalize_round
        # increments it) -- turn=0 is transcript "Turn 1".
        (tmp_path / "decisions_game0_seat0.jsonl").write_text(
            json.dumps(_orders_record(0, 0, '{"0": {"type": "Move", "dest": 9}}')) + "\n"
        )


def test_build_replay_merges_transcript_and_orders(tmp_path) -> None:
    _write_fixture(tmp_path)
    replay = build_replay(tmp_path, game_id=0)
    assert replay is not None
    assert replay["identity_by_seat"] == ["Delta", "Echo", "Foxtrot", "Golf"]
    assert replay["freerider_seats"] == [3]
    assert replay["llm_seats"] == [0, 1, 2]
    assert replay["final_scores"] == {0: 2.0, 1: 3.0, 2: 1.0, 3: 6.0}
    assert replay["winners"] == [3]

    turn1 = replay["turns"][0]
    assert turn1["declarations"][0]["stance"] == {3: "hostile"}
    assert turn1["orders"][0] == {"0": {"type": "Move", "dest": 9}}


def test_build_replay_missing_game_returns_none(tmp_path) -> None:
    _write_fixture(tmp_path)
    assert build_replay(tmp_path, game_id=99) is None


def test_build_replay_without_transcript_falls_back_to_orders_only(tmp_path) -> None:
    _write_fixture(tmp_path, with_transcript=False)
    replay = build_replay(tmp_path, game_id=0)
    assert replay is not None
    assert replay["stance_available"] is False
    turn1 = replay["turns"][0]
    assert turn1["declarations"] == {}
    assert turn1["orders"][0] == {"0": {"type": "Move", "dest": 9}}


def test_build_replay_includes_this_games_self_notes_only(tmp_path) -> None:
    _write_fixture(tmp_path)
    payload_game0 = {
        "game_index": 0, "seat": 0, "entrant_identity": "Delta",
        "records": [{"facts": {"game_index": 0}, "self_note": "Golf is generous."}],
    }
    payload_game1 = {
        "game_index": 1, "seat": 0, "entrant_identity": "Delta",
        "records": [
            {"facts": {"game_index": 0}, "self_note": "Golf is generous."},
            {"facts": {"game_index": 1}, "self_note": "Golf betrayed me."},
        ],
    }
    (tmp_path / "campaign_memory_game0_seat0.json").write_text(json.dumps(payload_game0))
    (tmp_path / "campaign_memory_game1_seat0.json").write_text(json.dumps(payload_game1))

    replay = build_replay(tmp_path, game_id=0)
    assert replay["self_notes"] == [{
        "game_index": 0, "seat": 0, "entrant_identity": "Delta",
        "self_note": "Golf is generous.",
    }]
