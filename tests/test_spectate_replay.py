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


def test_build_replay_includes_support_targets_per_turn(tmp_path) -> None:
    """support_targets is per-order classification (not just the aggregate
    subsidy/llm_llm_supports ints), so the UI can badge a specific order."""
    (tmp_path / "sweep.jsonl").write_text(json.dumps(SWEEP_RECORD) + "\n")
    (tmp_path / "transcript_game0.md").write_text(TRANSCRIPT)
    prompt = "VISIBLE UNITS:\n  u9 at node 3 (player 3)\n"
    (tmp_path / "decisions_game0_seat0.jsonl").write_text(
        json.dumps({
            "turn": 0, "phase": "orders", "player": 0,
            "prompt": {"system": "", "user": prompt},
            "raw_response": '{"orders": {"0": {"type": "Support", "target": 9}}}',
            "fell_back": False,
        }) + "\n"
    )
    replay = build_replay(tmp_path, game_id=0)
    turn1 = replay["turns"][0]
    assert turn1["support_targets"][0] == {"0": "freerider"}


def test_build_replay_falls_back_to_plan_seatings_when_sweep_lacks_metadata(tmp_path) -> None:
    """Symmetry with dashboard.py: identity_by_seat/freerider_seats/llm_seats
    should fall back to campaign_plan.json's seatings, not just the sweep
    record, so a base-harness run (sweep without these fields) still resolves
    seat metadata when a campaign_plan.json is present."""
    bare_sweep = {k: v for k, v in SWEEP_RECORD.items()
                  if k not in ("identity_by_seat", "freerider_seats", "llm_seats")}
    (tmp_path / "sweep.jsonl").write_text(json.dumps(bare_sweep) + "\n")
    (tmp_path / "campaign_plan.json").write_text(json.dumps({
        "seatings": [{
            "game_index": 0,
            "identity_by_seat": ["Delta", "Echo", "Foxtrot", "Golf"],
            "freerider_seats": [3], "llm_seats": [0, 1, 2],
        }],
    }))
    replay = build_replay(tmp_path, game_id=0)
    assert replay["identity_by_seat"] == ["Delta", "Echo", "Foxtrot", "Golf"]
    assert replay["freerider_seats"] == [3]
    assert replay["llm_seats"] == [0, 1, 2]


def test_build_replay_live_stream_for_unfinished_game(tmp_path) -> None:
    """Brief requirement: 'the spectator server auto-upgrades to live
    turn-by-turn when the stream exists' -- a game with no sweep record yet
    (still in flight) but a spectate_game{g}.jsonl stream must still replay,
    marked live, built straight from the stream (which has real orders for
    ALL seats, not just LLM ones)."""
    stream_records = [
        {
            "game_id": 5, "turn": 1,
            "stances": {"0": {"1": "ally"}, "1": {"0": "ally"}},
            "intents": {"0": [{"unit_id": 2, "declared_order": {"type": "Hold"},
                                "visible_to": None}]},
            "orders": {"0": {"2": {"type": "Hold"}}, "1": {"3": {"type": "Move", "dest": 9}}},
            "scores": {"0": 1.0, "1": 1.0},
            "eliminated": [],
        },
        {
            "game_id": 5, "turn": 2,
            "stances": {"0": {"1": "hostile"}},
            "intents": {},
            "orders": {"0": {"2": {"type": "Move", "dest": 4}}},
            "scores": {"0": 2.0, "1": 1.0},
            "eliminated": [],
        },
    ]
    (tmp_path / "spectate_game5.jsonl").write_text(
        "\n".join(json.dumps(r) for r in stream_records) + "\n"
    )
    replay = build_replay(tmp_path, game_id=5)
    assert replay is not None
    assert replay["live"] is True
    assert [t["turn"] for t in replay["turns"]] == [1, 2]
    assert replay["turns"][0]["declarations"][0]["stance"] == {1: "ally"}
    assert replay["turns"][0]["declarations"][0]["intents"][0]["order"] == {"type": "Hold"}
    assert replay["turns"][0]["orders"][1] == {"3": {"type": "Move", "dest": 9}}
    assert replay["final_scores"] == {0: 2.0, 1: 1.0}  # latest stream turn's scores


def test_build_replay_live_stream_uses_plan_seatings_for_identities(tmp_path) -> None:
    (tmp_path / "campaign_plan.json").write_text(json.dumps({
        "seatings": [{
            "game_index": 7,
            "identity_by_seat": ["Delta", "Golf"],
            "freerider_seats": [1], "llm_seats": [0],
        }],
    }))
    (tmp_path / "spectate_game7.jsonl").write_text(json.dumps({
        "game_id": 7, "turn": 1, "stances": {}, "intents": {}, "orders": {},
        "scores": {"0": 1.0, "1": 2.0}, "eliminated": [],
    }) + "\n")
    replay = build_replay(tmp_path, game_id=7)
    assert replay["identity_by_seat"] == ["Delta", "Golf"]
    assert replay["freerider_seats"] == [1]


def test_build_replay_neither_sweep_nor_stream_returns_none(tmp_path) -> None:
    assert build_replay(tmp_path, game_id=0) is None


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
