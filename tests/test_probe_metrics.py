"""Tests for foedus.eval.probe_metrics -- degeneracy flags (all-Hold turns,
repeated identical orders) and self-note extraction for the Haiku fitness
probe report (M-foedus-haiku-fitness-probe).

These supplement the parse-fail / subsidy / coalition metrics already
produced by foedus.eval.memory_metrics.scorecard and
foedus.eval.punishment_metrics -- this module covers only what neither of
those already computes.
"""

from __future__ import annotations

import json

from foedus.eval.probe_metrics import (
    all_hold_turns,
    is_all_hold,
    repeated_identical_order_runs,
    self_notes_for_identity,
)


def _orders(turn, orders_dict):
    return {
        "turn": turn,
        "phase": "orders",
        "raw_response": json.dumps({"orders": orders_dict}),
    }


def _negotiate(turn):
    return {"turn": turn, "phase": "negotiate", "raw_response": "{}"}


class TestIsAllHold:
    def test_empty_orders_dict_counts_as_all_hold(self):
        assert is_all_hold({}) is True

    def test_single_hold_order_is_all_hold(self):
        assert is_all_hold({"1": {"type": "Hold"}}) is True

    def test_mixed_hold_and_move_is_not_all_hold(self):
        assert is_all_hold({
            "1": {"type": "Hold"},
            "2": {"type": "Move", "dest": 4},
        }) is False

    def test_single_move_order_is_not_all_hold(self):
        assert is_all_hold({"1": {"type": "Move", "dest": 4}}) is False


class TestAllHoldTurns:
    def test_flags_only_orders_phase_all_hold_turns(self):
        decisions = [
            _negotiate(1),
            _orders(1, {"1": {"type": "Hold"}}),
            _orders(2, {"1": {"type": "Move", "dest": 4}}),
            _orders(3, {}),
        ]
        assert all_hold_turns(decisions) == [1, 3]

    def test_no_all_hold_turns_returns_empty_list(self):
        decisions = [_orders(1, {"1": {"type": "Move", "dest": 4}})]
        assert all_hold_turns(decisions) == []

    def test_unparseable_raw_response_is_skipped_not_flagged(self):
        decisions = [
            {"turn": 1, "phase": "orders", "raw_response": "not json"},
        ]
        assert all_hold_turns(decisions) == []


class TestRepeatedIdenticalOrderRuns:
    def test_three_consecutive_identical_turns_is_one_run(self):
        same = {"1": {"type": "Move", "dest": 4}}
        decisions = [_orders(1, same), _orders(2, same), _orders(3, same)]
        assert repeated_identical_order_runs(decisions, min_repeat=3) == [[1, 2, 3]]

    def test_two_consecutive_identical_turns_below_threshold_not_flagged(self):
        same = {"1": {"type": "Move", "dest": 4}}
        decisions = [_orders(1, same), _orders(2, same)]
        assert repeated_identical_order_runs(decisions, min_repeat=3) == []

    def test_varying_orders_produces_no_runs(self):
        decisions = [
            _orders(1, {"1": {"type": "Move", "dest": 4}}),
            _orders(2, {"1": {"type": "Move", "dest": 5}}),
            _orders(3, {"1": {"type": "Hold"}}),
        ]
        assert repeated_identical_order_runs(decisions, min_repeat=3) == []

    def test_a_gap_in_turn_numbers_breaks_the_run(self):
        same = {"1": {"type": "Move", "dest": 4}}
        # turn 5 is missing -- decisions from turns 3 and 4 don't chain into 6/7
        decisions = [
            _orders(3, same), _orders(4, same),
            _orders(6, same), _orders(7, same),
        ]
        assert repeated_identical_order_runs(decisions, min_repeat=3) == []


class TestSelfNotesForIdentity:
    def test_reads_self_notes_from_highest_numbered_game_file(self, tmp_path):
        # Real shape (foedus.agents.llm.campaign_memory.GameRecord.to_dict):
        # game_index lives under "facts", not on the record itself.
        (tmp_path / "campaign_memory_game0_seat0.json").write_text(json.dumps({
            "game_index": 0, "seat": 0, "entrant_identity": "Delta",
            "records": [{"facts": {"game_index": 0}, "self_note": "first game note"}],
        }))
        (tmp_path / "campaign_memory_game1_seat2.json").write_text(json.dumps({
            "game_index": 1, "seat": 2, "entrant_identity": "Delta",
            "records": [
                {"facts": {"game_index": 0}, "self_note": "first game note"},
                {"facts": {"game_index": 1}, "self_note": "second game note"},
            ],
        }))
        (tmp_path / "campaign_memory_game1_seat0.json").write_text(json.dumps({
            "game_index": 1, "seat": 0, "entrant_identity": "Echo",
            "records": [{"facts": {"game_index": 1}, "self_note": "echo's note"}],
        }))

        notes = self_notes_for_identity(tmp_path, "Delta")

        assert notes == [
            {"game_index": 0, "entrant_identity": "Delta", "self_note": "first game note"},
            {"game_index": 1, "entrant_identity": "Delta", "self_note": "second game note"},
        ]

    def test_missing_identity_returns_empty_list(self, tmp_path):
        (tmp_path / "campaign_memory_game0_seat0.json").write_text(json.dumps({
            "game_index": 0, "seat": 0, "entrant_identity": "Delta",
            "records": [{"facts": {"game_index": 0}, "self_note": "note"}],
        }))
        assert self_notes_for_identity(tmp_path, "Foxtrot") == []
