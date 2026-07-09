"""Tests for foedus.eval.punishment_metrics's Check 2 helpers
(M-foedus-s1-5-confound-check): fell_back_by_seat_turn / clean_call_subset /
match_paid_execution_turns.

Confound #2 (autopsy-s1.md section 4): the corpus's ~8.2% parse/timeout-fail
rate is a candidate explanation for the near-zero executed->paid conversion
independent of combat economics. These helpers restrict the executed/paid
counts to attack-turns where every INVOLVED seat's call (negotiate AND
orders) that turn had no fallback, so the conversion rate can be recomputed
on a clean subset. All inputs are scripted; no corpus files needed.
"""

from __future__ import annotations

import json

from foedus.eval.punishment_metrics import (
    classify_game_punishment,
    clean_call_subset,
    client_error_by_seat_turn,
    fell_back_by_seat_turn,
    match_paid_execution_turns,
)


def _negotiate_rec(turn: int, player: int, raw: str, prompt_user: str = "",
                   fell_back: bool = False) -> dict:
    return {"turn": turn, "phase": "negotiate", "player": player,
            "prompt": {"user": prompt_user}, "raw_response": raw,
            "fell_back": fell_back}


def _orders_rec(turn: int, player: int, raw: str, prompt_user: str = "",
                fell_back: bool = False) -> dict:
    return {"turn": turn, "phase": "orders", "player": player,
            "prompt": {"user": prompt_user}, "raw_response": raw,
            "fell_back": fell_back}


def _visible_units_prompt(units: list[tuple[int, int, int, int]]) -> str:
    lines = ["VISIBLE UNITS:"]
    for uid, node, owner, me in units:
        marker = "(YOURS)" if owner == me else f"(player {owner})"
        lines.append(f"  u{uid} at node {node} {marker}")
    return "\n".join(lines)


# --- match_paid_execution_turns --------------------------------------------


def test_match_paid_execution_turns_pairs_latest_qualifying_execution() -> None:
    paid_drop, paid_exec = match_paid_execution_turns(
        drop_turns=[7, 11], exec_turns=[5, 6, 9])
    # 7 qualifies for both 5 (5+2=7) and 6 (6+1=7) -> latest (6) wins.
    assert paid_drop == {7, 11}
    assert paid_exec == {6, 9}


def test_match_paid_execution_turns_drop_with_no_candidate_is_unpaid() -> None:
    paid_drop, paid_exec = match_paid_execution_turns(
        drop_turns=[20], exec_turns=[5])
    assert paid_drop == set()
    assert paid_exec == set()


# --- fell_back_by_seat_turn --------------------------------------------------


def test_fell_back_by_seat_turn_true_if_either_phase_fell_back() -> None:
    decisions_by_seat = {
        0: [
            _negotiate_rec(5, 0, "{}", fell_back=False),
            _orders_rec(5, 0, "{}", fell_back=True),
            _negotiate_rec(6, 0, "{}", fell_back=False),
            _orders_rec(6, 0, "{}", fell_back=False),
        ],
    }
    lookup = fell_back_by_seat_turn(decisions_by_seat)
    assert lookup[(0, 5)] is True
    assert lookup[(0, 6)] is False
    assert (0, 7) not in lookup


def test_client_error_by_seat_turn_ignores_sanitizer_only_fallback() -> None:
    """fell_back=True from a successful sanitizer recovery (real JSON, just
    needed a node-label fix) is NOT a client error; only a literal
    `<client error: ...>` raw_response counts."""
    decisions_by_seat = {
        0: [
            _orders_rec(5, 0, json.dumps({"orders": {"1": {"type": "Hold"}}}),
                        fell_back=True),  # sanitizer-recovered, not a transport failure
            _orders_rec(6, 0, "<client error: RuntimeError('timed out')>",
                        fell_back=True),
        ],
    }
    lookup = client_error_by_seat_turn(decisions_by_seat)
    assert lookup[(0, 5)] is False
    assert lookup[(0, 6)] is True


# --- clean_call_subset -------------------------------------------------------


def _build_two_attack_turn_report():
    """Seat 0 attacks Golf (seat 3, unit 5 at node 11) at turn 5 (clean call)
    and again at turn 9 (dirty: orders-phase fell_back=True). Golf's income
    drops at turn 7 (pairs with the turn-5 execution: 7 in {6,7}) and at
    turn 11 (pairs with the turn-9 execution: 11 in {10,11}). Deltas are
    engineered so ONLY turns 7 and 11 register as drops (see the confound-
    check module docstring's worked trace)."""
    vis = _visible_units_prompt([(5, 11, 3, 0)])
    cumulative = {5: 10.0, 6: 13.0, 7: 14.0, 8: 15.0, 9: 16.0, 10: 19.0, 11: 20.0}

    def scores_text(turn: int) -> str:
        v = cumulative[turn]
        return f"Scores: {{0: 1.0, 1: 1.0, 2: 1.0, 3: {v}}}\n"

    decisions_by_seat = {
        0: [
            _negotiate_rec(5, 0, "{}", prompt_user=scores_text(5)),
            _orders_rec(5, 0, json.dumps({"orders": {"1": {"type": "Move", "dest": 11}}}),
                        prompt_user=vis),
            _negotiate_rec(6, 0, "{}", prompt_user=scores_text(6)),
            _negotiate_rec(7, 0, "{}", prompt_user=scores_text(7)),
            _negotiate_rec(8, 0, "{}", prompt_user=scores_text(8)),
            _negotiate_rec(9, 0, "{}", prompt_user=scores_text(9)),
            _orders_rec(9, 0, json.dumps({"orders": {"1": {"type": "Move", "dest": 11}}}),
                        prompt_user=vis, fell_back=True),
            _negotiate_rec(10, 0, "{}", prompt_user=scores_text(10)),
            _negotiate_rec(11, 0, "{}", prompt_user=scores_text(11)),
        ],
    }
    report = classify_game_punishment(
        decisions_by_seat=decisions_by_seat, llm_seats=[0], freerider_seats={3})
    return decisions_by_seat, report


def test_clean_call_subset_full_report_sees_both_attack_turns_as_paid() -> None:
    _decisions, report = _build_two_attack_turn_report()
    assert report["golf_income_drop_turns"] == [7, 11]
    assert report["executed_count"] == 2
    assert report["paid_count"] == 2


def test_clean_call_subset_drops_the_dirty_turn_and_its_paid_credit() -> None:
    decisions_by_seat, report = _build_two_attack_turn_report()
    fell_back = fell_back_by_seat_turn(decisions_by_seat)
    clean = clean_call_subset(report, fell_back)
    assert clean["executed_count"] == 1
    assert clean["paid_count"] == 1
    assert clean["paid_execution_turns"] == [5]
    assert clean["dirty_turns_excluded"] == [9]


def test_clean_call_subset_no_dirty_turns_is_a_no_op() -> None:
    decisions_by_seat, report = _build_two_attack_turn_report()
    # Manually clear the dirty flag to simulate an all-clean corpus subset.
    for rec in decisions_by_seat[0]:
        rec["fell_back"] = False
    fell_back = fell_back_by_seat_turn(decisions_by_seat)
    clean = clean_call_subset(report, fell_back)
    assert clean["executed_count"] == report["executed_count"]
    assert clean["paid_count"] == report["paid_count"]
    assert clean["dirty_turns_excluded"] == []
