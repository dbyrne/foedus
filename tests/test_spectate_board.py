"""Tests for foedus/spectate/board.py -- building per-turn declared-orders +
support-classification frames from LLM seats' decision logs (the "orders"
half of the replay theater; stances/intents come from transcript.py)."""

from __future__ import annotations

from foedus.spectate.board import build_turn_frames


def _negotiate(turn, player, stance=None, intents=None, fell_back=False):
    return {
        "turn": turn, "phase": "negotiate", "player": player,
        "prompt": {"system": "", "user": ""},
        "raw_response": (
            '{"press": {"stance": %s, "intents": %s}, '
            '"pacts": {"propose": [], "accept": []}}'
            % (stance if stance is not None else "{}",
               intents if intents is not None else "[]")
        ),
        "fell_back": fell_back,
    }


def _orders(turn, player, orders_json, prompt_user="", fell_back=False):
    return {
        "turn": turn, "phase": "orders", "player": player,
        "prompt": {"system": "", "user": prompt_user},
        "raw_response": '{"orders": %s}' % orders_json,
        "fell_back": fell_back,
    }


def test_build_turn_frames_groups_by_turn() -> None:
    decisions_by_seat = {
        0: [_negotiate(1, 0), _orders(1, 0, "{}")],
        1: [_negotiate(1, 1), _orders(1, 1, "{}")],
    }
    frames = build_turn_frames(decisions_by_seat, freerider_seats=[3], llm_seats=[0, 1])
    assert [f["turn"] for f in frames] == [1]


def test_build_turn_frames_captures_orders_per_seat() -> None:
    decisions_by_seat = {
        0: [_orders(1, 0, '{"5": {"type": "Move", "dest": 9}}')],
    }
    frames = build_turn_frames(decisions_by_seat, freerider_seats=[3], llm_seats=[0])
    assert frames[0]["orders"][0] == {"5": {"type": "Move", "dest": 9}}


def test_build_turn_frames_subsidy_counts_support_of_freerider() -> None:
    prompt = "VISIBLE UNITS:\n  u9 at node 3 (player 3)\n"
    decisions_by_seat = {
        0: [_orders(1, 0, '{"5": {"type": "Support", "target": 9}}', prompt_user=prompt)],
    }
    frames = build_turn_frames(decisions_by_seat, freerider_seats=[3], llm_seats=[0, 1])
    assert frames[0]["subsidy"] == 1
    assert frames[0]["llm_llm_supports"] == 0


def test_build_turn_frames_llm_llm_support_excludes_freerider_and_self() -> None:
    prompt = (
        "VISIBLE UNITS:\n"
        "  u9 at node 3 (player 1)\n"
        "  u10 at node 4 (player 3)\n"
    )
    decisions_by_seat = {
        0: [_orders(
            1, 0,
            '{"5": {"type": "Support", "target": 9}, '
            '"6": {"type": "Support", "target": 10}}',
            prompt_user=prompt,
        )],
    }
    frames = build_turn_frames(decisions_by_seat, freerider_seats=[3], llm_seats=[0, 1])
    assert frames[0]["llm_llm_supports"] == 1
    assert frames[0]["subsidy"] == 1


def test_build_turn_frames_fell_back_flag_recorded_per_seat() -> None:
    decisions_by_seat = {
        0: [_orders(1, 0, "{}", fell_back=True)],
        1: [_orders(1, 1, "{}", fell_back=False)],
    }
    frames = build_turn_frames(decisions_by_seat, freerider_seats=[], llm_seats=[0, 1])
    assert frames[0]["fell_back"] == {0: True, 1: False}


def test_build_turn_frames_handles_garbage_raw_response() -> None:
    decisions_by_seat = {0: [_orders(1, 0, "garbage-not-json")]}
    # Manually break the record's raw_response to non-JSON garbage.
    decisions_by_seat[0][0]["raw_response"] = "<client error: timeout>"
    frames = build_turn_frames(decisions_by_seat, freerider_seats=[], llm_seats=[0])
    assert frames[0]["orders"][0] == {}


def test_build_turn_frames_empty_input() -> None:
    assert build_turn_frames({}, freerider_seats=[], llm_seats=[]) == []
