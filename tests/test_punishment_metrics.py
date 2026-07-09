"""Tests for foedus.eval.punishment_metrics -- the S1 corpus-autopsy classifier
(M-foedus-s1-corpus-autopsy).

Classifies, from the same self-contained JSON the canonical-campaign harness
already emits (decision-log `raw_response` + `prompt`), whether punishing a
freerider was ever PROPOSED in press (hostile stance / a declared attack-move
intent / an attack-shaped pact proposal), EXECUTED as a real order (an attack
Move onto a freerider-occupied node, or a Support of one), and whether an
execution PAID (the freerider's own per-turn income -- carried in every
negotiate prompt's public `Scores` dict -- actually dropped).

All inputs are scripted; no model or corpus files needed for these unit tests.
"""

from __future__ import annotations

import json

import pytest

from foedus.eval.punishment_metrics import (
    classify_game_punishment,
    classify_negotiate_proposal,
    classify_orders_execution,
    golf_occupied_nodes,
    income_drop_turns,
    income_series,
    parse_scores,
    parse_visible_units,
    pearson_correlation,
)


def _visible_units_prompt(units: list[tuple[int, int, int, int]]) -> str:
    """`units` = [(unit_id, node, owner, me_seat)] -> a VISIBLE UNITS block."""
    lines = ["VISIBLE UNITS:"]
    for uid, node, owner, me in units:
        marker = "(YOURS)" if owner == me else f"(player {owner})"
        lines.append(f"  u{uid} at node {node} {marker}")
    return "\n".join(lines)


# --- parse_visible_units ------------------------------------------------------


def test_parse_visible_units_reads_owner_and_node() -> None:
    prompt = _visible_units_prompt([(1, 7, 0, 0), (5, 11, 3, 0), (8, 12, 3, 0)])
    units = parse_visible_units(prompt, me_seat=0)
    assert units == {
        1: {"owner": 0, "node": 7},
        5: {"owner": 3, "node": 11},
        8: {"owner": 3, "node": 12},
    }


def test_parse_visible_units_identity_annotated_marker() -> None:
    prompt = "VISIBLE UNITS:\n  u3 at node 6 (p1 (Echo))\n  u0 at node 4 (p3 (Golf))\n"
    units = parse_visible_units(prompt, me_seat=0)
    assert units == {3: {"owner": 1, "node": 6}, 0: {"owner": 3, "node": 4}}


def test_parse_visible_units_empty_when_absent() -> None:
    assert parse_visible_units("no such block here", me_seat=0) == {}


# --- golf_occupied_nodes -------------------------------------------------------


def test_golf_occupied_nodes_filters_by_freerider_seats() -> None:
    units = {
        1: {"owner": 0, "node": 7},
        5: {"owner": 3, "node": 11},
        8: {"owner": 3, "node": 12},
    }
    assert golf_occupied_nodes(units, {3}) == {11, 12}


def test_golf_occupied_nodes_empty_when_not_visible() -> None:
    units = {1: {"owner": 0, "node": 7}}
    assert golf_occupied_nodes(units, {3}) == set()


# --- parse_scores --------------------------------------------------------------


def test_parse_scores_reads_public_scores_dict() -> None:
    prompt = "Scores: {0: 3.0, 1: 3.0, 2: 4.0, 3: 2.0}\nYour supply count: 2\n"
    assert parse_scores(prompt) == {0: 3.0, 1: 3.0, 2: 4.0, 3: 2.0}


def test_parse_scores_none_when_absent() -> None:
    assert parse_scores("nothing here") is None


# --- classify_negotiate_proposal ------------------------------------------------


def test_classify_negotiate_hostile_stance_toward_freerider() -> None:
    raw = json.dumps({"press": {"stance": {"3": "hostile"}, "intents": []},
                       "pacts": {"propose": [], "accept": []}})
    out = classify_negotiate_proposal(raw, freerider_seats={3}, golf_nodes=set())
    assert out["hostile_toward_freerider"] is True
    assert out["attack_move_units"] == []


def test_classify_negotiate_non_hostile_stance_toward_freerider() -> None:
    raw = json.dumps({"press": {"stance": {"3": "ally"}, "intents": []},
                       "pacts": {"propose": [], "accept": []}})
    out = classify_negotiate_proposal(raw, freerider_seats={3}, golf_nodes=set())
    assert out["hostile_toward_freerider"] is False


def test_classify_negotiate_declared_attack_move_intent() -> None:
    raw = json.dumps({
        "press": {
            "stance": {"3": "neutral"},
            "intents": [
                {"unit_id": 1, "declared_order": {"type": "Move", "dest": 11},
                 "visible_to": None},
            ],
        },
        "pacts": {"propose": [], "accept": []},
    })
    out = classify_negotiate_proposal(raw, freerider_seats={3}, golf_nodes={11})
    assert out["attack_move_units"] == [1]


def test_classify_negotiate_move_intent_to_non_golf_node_not_an_attack() -> None:
    raw = json.dumps({
        "press": {"stance": {}, "intents": [
            {"unit_id": 1, "declared_order": {"type": "Move", "dest": 9},
             "visible_to": None},
        ]},
        "pacts": {"propose": [], "accept": []},
    })
    out = classify_negotiate_proposal(raw, freerider_seats={3}, golf_nodes={11})
    assert out["attack_move_units"] == []


def test_classify_negotiate_support_intent_recorded_for_cross_reference() -> None:
    raw = json.dumps({
        "press": {"stance": {}, "intents": [
            {"unit_id": 4, "declared_order": {"type": "Support", "target": 1},
             "visible_to": None},
        ]},
        "pacts": {"propose": [], "accept": []},
    })
    out = classify_negotiate_proposal(raw, freerider_seats={3}, golf_nodes=set())
    assert out["support_intents"] == [(4, 1)]


def test_classify_negotiate_pact_proposal_with_golf_as_counterparty_not_coordination() -> None:
    raw = json.dumps({
        "press": {"stance": {}, "intents": []},
        "pacts": {"propose": [{
            "counterparty": 3,
            "terms": [
                {"player": 0, "unit_id": 1, "declared_order": {"type": "Move", "dest": 11}},
                {"player": 3, "unit_id": 0, "declared_order": {"type": "Hold"}},
            ],
        }], "accept": []},
    })
    out = classify_negotiate_proposal(raw, freerider_seats={3}, golf_nodes={11})
    assert out["attack_pact_proposals"] == []


def test_classify_negotiate_pact_proposal_attacking_golf_between_two_llms() -> None:
    raw = json.dumps({
        "press": {"stance": {}, "intents": []},
        "pacts": {"propose": [{
            "counterparty": 1,
            "terms": [
                {"player": 0, "unit_id": 1, "declared_order": {"type": "Move", "dest": 11}},
                {"player": 1, "unit_id": 3, "declared_order": {"type": "Support", "target": 1}},
            ],
        }], "accept": []},
    })
    out = classify_negotiate_proposal(raw, freerider_seats={3}, golf_nodes={11})
    assert len(out["attack_pact_proposals"]) == 1
    prop = out["attack_pact_proposals"][0]
    assert prop["counterparty"] == 1
    assert prop["attacking_units"] == [1]
    assert prop["coordinated"] is True


def test_classify_negotiate_pact_proposal_single_party_attack_not_coordinated() -> None:
    raw = json.dumps({
        "press": {"stance": {}, "intents": []},
        "pacts": {"propose": [{
            "counterparty": 1,
            "terms": [
                {"player": 0, "unit_id": 1, "declared_order": {"type": "Move", "dest": 11}},
                {"player": 1, "unit_id": 3, "declared_order": {"type": "Hold"}},
            ],
        }], "accept": []},
    })
    out = classify_negotiate_proposal(raw, freerider_seats={3}, golf_nodes={11})
    prop = out["attack_pact_proposals"][0]
    assert prop["coordinated"] is False


def test_classify_negotiate_unparseable_raw_is_empty() -> None:
    out = classify_negotiate_proposal("<client error: boom>", freerider_seats={3},
                                       golf_nodes={11})
    assert out == {
        "hostile_toward_freerider": False,
        "attack_move_units": [],
        "support_intents": [],
        "attack_pact_proposals": [],
    }


# --- classify_orders_execution --------------------------------------------------


def test_classify_orders_execution_direct_attack_move() -> None:
    raw = json.dumps({"orders": {"1": {"type": "Move", "dest": 11}}})
    out = classify_orders_execution(raw, golf_nodes={11})
    assert out["attack_moves"] == [1]
    assert out["supports"] == []


def test_classify_orders_execution_move_elsewhere_not_an_attack() -> None:
    raw = json.dumps({"orders": {"1": {"type": "Move", "dest": 9}}})
    out = classify_orders_execution(raw, golf_nodes={11})
    assert out["attack_moves"] == []


def test_classify_orders_execution_records_supports_for_cross_reference() -> None:
    raw = json.dumps({"orders": {"4": {"type": "Support", "target": 1}}})
    out = classify_orders_execution(raw, golf_nodes={11})
    assert out["supports"] == [(4, 1)]


def test_classify_orders_execution_unparseable_raw_is_empty() -> None:
    out = classify_orders_execution("<client error: boom>", golf_nodes={11})
    assert out == {"attack_moves": [], "supports": []}


def test_classify_orders_execution_hold_orders_ignored() -> None:
    raw = json.dumps({"orders": {"1": {"type": "Hold"}}})
    out = classify_orders_execution(raw, golf_nodes={11})
    assert out == {"attack_moves": [], "supports": []}


# --- income_series / income_drop_turns ------------------------------------------


def test_income_series_computes_per_turn_deltas() -> None:
    scores_by_turn = {
        0: {3: 0.0}, 1: {3: 1.0}, 2: {3: 2.0}, 3: {3: 4.0}, 4: {3: 6.0},
    }
    assert income_series(scores_by_turn, freerider_seat=3) == {
        1: 1.0, 2: 1.0, 3: 2.0, 4: 2.0,
    }


def test_income_series_skips_turns_missing_the_freerider() -> None:
    scores_by_turn = {0: {3: 0.0}, 1: {}, 2: {3: 3.0}}
    # turn 1 has no observation -> no delta computed into/out of it
    assert income_series(scores_by_turn, freerider_seat=3) == {}


def test_income_drop_turns_flags_decrease_from_prior_income() -> None:
    # income steady at 2, then drops to 1 at turn 5 -> a center was lost
    series = {1: 1.0, 2: 1.0, 3: 2.0, 4: 2.0, 5: 1.0}
    assert income_drop_turns(series) == [5]


def test_income_drop_turns_empty_when_monotonic_non_decreasing() -> None:
    series = {1: 1.0, 2: 1.0, 3: 2.0, 4: 2.0}
    assert income_drop_turns(series) == []


def test_income_drop_turns_empty_series() -> None:
    assert income_drop_turns({}) == []


# --- classify_game_punishment (integration across seats/turns) -----------------


def _negotiate_rec(turn: int, player: int, raw: str, prompt_user: str = "") -> dict:
    return {"turn": turn, "phase": "negotiate", "player": player,
            "prompt": {"user": prompt_user}, "raw_response": raw, "fell_back": False}


def _orders_rec(turn: int, player: int, raw: str, prompt_user: str = "") -> dict:
    return {"turn": turn, "phase": "orders", "player": player,
            "prompt": {"user": prompt_user}, "raw_response": raw, "fell_back": False}


def test_classify_game_punishment_counts_proposed_executed_and_solo_when_no_drop() -> None:
    # Seat 0 sees golf's unit u5 at node 11, declares a hostile stance and an
    # attack-move intent against it at turn 2, then actually executes the Move
    # at turn 2's orders phase. Golf's income never drops -> not "paid".
    vis = _visible_units_prompt([(1, 7, 0, 0), (5, 11, 3, 0)])
    decisions_by_seat = {
        0: [
            _negotiate_rec(2, 0, json.dumps({
                "press": {"stance": {"3": "hostile"}, "intents": [
                    {"unit_id": 1, "declared_order": {"type": "Move", "dest": 11},
                     "visible_to": None},
                ]}, "pacts": {"propose": [], "accept": []},
            }), prompt_user=vis + "\nScores: {0: 3.0, 1: 3.0, 2: 4.0, 3: 2.0}\n"),
            _orders_rec(2, 0, json.dumps({"orders": {"1": {"type": "Move", "dest": 11}}}),
                        prompt_user=vis),
            _negotiate_rec(3, 0, "{}", prompt_user="Scores: {0: 5.0, 1: 5.0, 2: 7.0, 3: 4.0}\n"),
        ],
    }
    report = classify_game_punishment(
        decisions_by_seat=decisions_by_seat, llm_seats=[0], freerider_seats={3})
    assert report["proposed_count"] == 1
    assert report["executed_count"] == 1
    assert report["paid_count"] == 0
    assert report["golf_income_drop_turns"] == []
    citation = report["executions"][0]
    assert (citation["game_turn"], citation["seat"], citation["unit_id"]) == (2, 0, 1)


def test_classify_game_punishment_paid_when_income_drops_after_execution() -> None:
    vis = _visible_units_prompt([(5, 11, 3, 0)])
    decisions_by_seat = {
        0: [
            # turn1 -> turn2 income = 2.0 (owns 2 centers)
            _negotiate_rec(1, 0, "{}",
                           prompt_user="Scores: {0: 1.0, 1: 1.0, 2: 1.0, 3: 2.0}\n"),
            _negotiate_rec(2, 0, "{}",
                           prompt_user="Scores: {0: 3.0, 1: 3.0, 2: 4.0, 3: 4.0}\n"),
            _orders_rec(2, 0, json.dumps({"orders": {"1": {"type": "Move", "dest": 11}}}),
                        prompt_user=vis),
            # turn2 -> turn3 income drops to 1.0: the attack executed at turn
            # 2 dislodged/captured one of the freerider's centers.
            _negotiate_rec(3, 0, "{}",
                           prompt_user="Scores: {0: 5.0, 1: 5.0, 2: 7.0, 3: 5.0}\n"),
            _negotiate_rec(4, 0, "{}",
                           prompt_user="Scores: {0: 7.0, 1: 7.0, 2: 9.0, 3: 6.0}\n"),
        ],
    }
    report = classify_game_punishment(
        decisions_by_seat=decisions_by_seat, llm_seats=[0], freerider_seats={3})
    assert report["golf_income_drop_turns"] == [3]
    assert report["executed_count"] == 1
    assert report["paid_count"] == 1


def test_classify_game_punishment_counts_declared_support_intent_of_an_attack() -> None:
    # Seat 0 declares an attack-move intent AND a companion Support intent
    # targeting it (its own second unit) -- a self-coordinated attack
    # proposal, distinct from a formal pact but still a concrete proposal.
    vis = _visible_units_prompt([(1, 7, 0, 0), (4, 3, 0, 0), (5, 11, 3, 0)])
    decisions_by_seat = {
        0: [
            _negotiate_rec(4, 0, json.dumps({
                "press": {"stance": {}, "intents": [
                    {"unit_id": 1, "declared_order": {"type": "Move", "dest": 11},
                     "visible_to": None},
                    {"unit_id": 4, "declared_order": {"type": "Support", "target": 1},
                     "visible_to": None},
                ]}, "pacts": {"propose": [], "accept": []},
            }), prompt_user=vis),
        ],
    }
    report = classify_game_punishment(
        decisions_by_seat=decisions_by_seat, llm_seats=[0], freerider_seats={3})
    kinds = sorted(p["kind"] for p in report["proposals"])
    assert kinds == ["attack_move_intent", "attack_support_intent"]
    support_prop = next(p for p in report["proposals"] if p["kind"] == "attack_support_intent")
    assert support_prop["unit_id"] == 4
    assert support_prop["target_unit_id"] == 1


def test_classify_game_punishment_support_intent_not_matching_any_attack_not_counted() -> None:
    raw = json.dumps({
        "press": {"stance": {}, "intents": [
            {"unit_id": 4, "declared_order": {"type": "Support", "target": 99},
             "visible_to": None},
        ]}, "pacts": {"propose": [], "accept": []},
    })
    decisions_by_seat = {0: [_negotiate_rec(4, 0, raw)]}
    report = classify_game_punishment(
        decisions_by_seat=decisions_by_seat, llm_seats=[0], freerider_seats={3})
    assert report["proposals"] == []


def test_classify_game_punishment_coordinated_support_execution_cross_seat() -> None:
    # Seat 0 executes the attack Move; seat 1 (a different unit) executes a
    # Support targeting seat 0's attacking unit in the SAME turn -> counted as
    # an executed coordinated attack-support, even though seat 1 never itself
    # saw golf's unit.
    vis0 = _visible_units_prompt([(1, 11, 0, 0), (5, 11, 3, 0)])
    decisions_by_seat = {
        0: [
            _orders_rec(4, 0, json.dumps({"orders": {"1": {"type": "Move", "dest": 11}}}),
                        prompt_user=vis0),
        ],
        1: [
            _orders_rec(4, 1, json.dumps({"orders": {"3": {"type": "Support", "target": 1}}}),
                        prompt_user="VISIBLE UNITS:\n  u3 at node 6 (YOURS)\n"),
        ],
    }
    report = classify_game_punishment(
        decisions_by_seat=decisions_by_seat, llm_seats=[0, 1], freerider_seats={3})
    # one attack move + one supporting Support of it = 2 executed actions
    assert report["executed_count"] == 2
    kinds = sorted(e["kind"] for e in report["executions"])
    assert kinds == ["attack_move", "attack_support"]


def test_classify_game_punishment_no_data_is_all_zero() -> None:
    report = classify_game_punishment(decisions_by_seat={}, llm_seats=[], freerider_seats={3})
    assert report["proposed_count"] == 0
    assert report["executed_count"] == 0
    assert report["paid_count"] == 0


# --- pearson_correlation ---------------------------------------------------


def test_pearson_correlation_perfect_positive() -> None:
    assert pearson_correlation([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)


def test_pearson_correlation_perfect_negative() -> None:
    assert pearson_correlation([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_correlation_none_on_zero_variance() -> None:
    assert pearson_correlation([1, 1, 1], [1, 2, 3]) is None


def test_pearson_correlation_none_on_mismatched_length() -> None:
    assert pearson_correlation([1, 2], [1, 2, 3]) is None


def test_pearson_correlation_none_on_fewer_than_two_points() -> None:
    assert pearson_correlation([1], [1]) is None
