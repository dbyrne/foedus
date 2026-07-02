"""Tests for foedus.agents.llm.parse — robust JSON extraction and
order/press/pact parsing for untrusted LLM output.

Every parse function must degrade to a safe fallback (never raise) and
report `fell_back` honestly — these tests are the ground truth for that
contract.
"""

from __future__ import annotations

import json

from foedus.core import Hold, Move, Support, Unit
from foedus.agents.llm.parse import (
    coerce_id,
    extract_json,
    parse_intent,
    parse_negotiation_response,
    parse_order,
    parse_orders_response,
    parse_pact_term,
    parse_stance,
)

from tests.helpers import line_map, make_state


# --- coerce_id ---------------------------------------------------------


def test_coerce_id_plain_int() -> None:
    assert coerce_id(2) == 2


def test_coerce_id_digit_string() -> None:
    assert coerce_id("2") == 2


def test_coerce_id_prefixed_unit_string() -> None:
    assert coerce_id("u2") == 2
    assert coerce_id("U2") == 2


def test_coerce_id_prefixed_player_string() -> None:
    assert coerce_id("p1") == 1


def test_coerce_id_rejects_garbage() -> None:
    assert coerce_id("abc") is None
    assert coerce_id("u2x") is None
    assert coerce_id(None) is None
    assert coerce_id(True) is None
    assert coerce_id(1.5) is None


def test_coerce_id_huge_digit_string_does_not_crash() -> None:
    """Regression: a repetition-loop id thousands of digits long used to
    hit CPython's int-string conversion length guard (ValueError) with
    nothing to catch it."""
    assert coerce_id("u" + "9" * 5000) is None
    assert coerce_id("9" * 5000) is None


# --- extract_json --------------------------------------------------------


def test_extract_json_plain_object() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced_block() -> None:
    text = 'Sure, here you go:\n```json\n{"a": 1}\n```\nHope that helps!'
    assert extract_json(text) == {"a": 1}


def test_extract_json_bare_fence_no_language_tag() -> None:
    text = '```\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_extract_json_balanced_braces_in_prose() -> None:
    text = 'I will respond with {"a": 1, "b": {"c": 2}} as requested.'
    assert extract_json(text) == {"a": 1, "b": {"c": 2}}


def test_extract_json_returns_none_for_garbage() -> None:
    assert extract_json("no json here at all") is None


def test_extract_json_ignores_braces_inside_strings() -> None:
    text = '{"a": "a string with a } brace inside"}'
    assert extract_json(text) == {"a": "a string with a } brace inside"}


# --- parse_order ---------------------------------------------------------


def _two_unit_state():
    m = line_map(3)
    units = [Unit(0, 0, 0), Unit(1, 1, 2)]
    return make_state(m, units, num_players=2)


def test_parse_order_hold() -> None:
    state = _two_unit_state()
    legal = [Hold(), Move(dest=1)]
    order, was_legal = parse_order({"type": "Hold"}, legal)
    assert order == Hold()
    assert was_legal is True


def test_parse_order_move_legal() -> None:
    legal = [Hold(), Move(dest=1)]
    order, was_legal = parse_order({"type": "Move", "dest": 1}, legal)
    assert order == Move(dest=1)
    assert was_legal is True


def test_parse_order_move_coerces_prefixed_dest() -> None:
    legal = [Hold(), Move(dest=1)]
    order, was_legal = parse_order({"type": "Move", "dest": "n1"}, legal)
    assert order == Move(dest=1)
    assert was_legal is True


def test_parse_order_move_illegal_falls_back_to_hold() -> None:
    legal = [Hold(), Move(dest=1)]
    order, was_legal = parse_order({"type": "Move", "dest": 99}, legal)
    assert order == Hold()
    assert was_legal is False


def test_parse_order_support_with_coerced_unit_id() -> None:
    legal = [Hold(), Support(target=1)]
    order, was_legal = parse_order({"type": "Support", "target": "u1"}, legal)
    assert order == Support(target=1)
    assert was_legal is True


def test_parse_order_support_with_require_dest() -> None:
    legal = [Hold(), Support(target=1, require_dest=2)]
    order, was_legal = parse_order(
        {"type": "Support", "target": 1, "require_dest": 2}, legal
    )
    assert order == Support(target=1, require_dest=2)
    assert was_legal is True


def test_parse_order_unknown_type_falls_back() -> None:
    order, was_legal = parse_order({"type": "Nuke", "dest": 1}, [Hold()])
    assert order == Hold()
    assert was_legal is False


def test_parse_order_not_a_dict_falls_back() -> None:
    order, was_legal = parse_order("garbage", [Hold()])
    assert order == Hold()
    assert was_legal is False


def test_parse_order_missing_type_falls_back() -> None:
    order, was_legal = parse_order({"dest": 1}, [Hold(), Move(dest=1)])
    assert order == Hold()
    assert was_legal is False


# --- parse_stance ----------------------------------------------------------


def test_parse_stance_valid() -> None:
    out = parse_stance({"1": "ally", "2": "hostile"})
    from foedus.core import Stance
    assert out == {1: Stance.ALLY, 2: Stance.HOSTILE}


def test_parse_stance_coerces_prefixed_keys() -> None:
    from foedus.core import Stance
    out = parse_stance({"p1": "ally"})
    assert out == {1: Stance.ALLY}


def test_parse_stance_skips_bad_entries() -> None:
    out = parse_stance({"1": "ally", "abc": "hostile", "2": "not-a-stance"})
    from foedus.core import Stance
    assert out == {1: Stance.ALLY}


def test_parse_stance_not_a_dict_returns_empty() -> None:
    assert parse_stance("garbage") == {}
    assert parse_stance(None) == {}


# --- parse_intent ------------------------------------------------------


def test_parse_intent_valid() -> None:
    state = _two_unit_state()
    d = {"unit_id": 0, "declared_order": {"type": "Move", "dest": 1},
         "visible_to": None}
    intent = parse_intent(d, state, player=0)
    assert intent is not None
    assert intent.unit_id == 0
    assert intent.declared_order == Move(dest=1)
    assert intent.visible_to is None


def test_parse_intent_coerces_unit_id_and_visible_to() -> None:
    state = _two_unit_state()
    d = {"unit_id": "u0", "declared_order": {"type": "Hold"},
         "visible_to": ["p1"]}
    intent = parse_intent(d, state, player=0)
    assert intent is not None
    assert intent.unit_id == 0
    assert intent.visible_to == frozenset({1})


def test_parse_intent_rejects_unowned_unit() -> None:
    state = _two_unit_state()
    d = {"unit_id": 1, "declared_order": {"type": "Hold"}, "visible_to": None}
    assert parse_intent(d, state, player=0) is None


def test_parse_intent_rejects_unknown_unit() -> None:
    state = _two_unit_state()
    d = {"unit_id": 99, "declared_order": {"type": "Hold"}, "visible_to": None}
    assert parse_intent(d, state, player=0) is None


def test_parse_intent_illegal_order_coerces_to_hold() -> None:
    state = _two_unit_state()
    d = {"unit_id": 0, "declared_order": {"type": "Move", "dest": 99},
         "visible_to": None}
    intent = parse_intent(d, state, player=0)
    assert intent is not None
    assert intent.declared_order == Hold()


# --- parse_pact_term ---------------------------------------------------


def test_parse_pact_term_valid() -> None:
    state = _two_unit_state()
    d = {"player": 0, "unit_id": 0, "declared_order": {"type": "Hold"}}
    term = parse_pact_term(d, state)
    assert term is not None
    assert term.player == 0
    assert term.unit_id == 0
    assert term.declared_order == Hold()


def test_parse_pact_term_rejects_mismatched_owner() -> None:
    state = _two_unit_state()
    d = {"player": 0, "unit_id": 1, "declared_order": {"type": "Hold"}}
    assert parse_pact_term(d, state) is None


def test_parse_pact_term_coerces_prefixed_ids() -> None:
    state = _two_unit_state()
    d = {"player": "p0", "unit_id": "u0", "declared_order": {"type": "Hold"}}
    term = parse_pact_term(d, state)
    assert term is not None
    assert term.player == 0
    assert term.unit_id == 0


# --- parse_negotiation_response -----------------------------------------


def test_parse_negotiation_response_full_valid_document() -> None:
    state = _two_unit_state()
    raw = json.dumps({
        "press": {
            "stance": {"1": "ally"},
            "intents": [
                {"unit_id": 0, "declared_order": {"type": "Hold"},
                 "visible_to": None},
            ],
        },
        "pacts": {
            "propose": [
                {"counterparty": 1, "terms": [
                    {"player": 0, "unit_id": 0,
                     "declared_order": {"type": "Hold"}},
                    {"player": 1, "unit_id": 1,
                     "declared_order": {"type": "Hold"}},
                ]},
            ],
            "accept": [3],
        },
    })
    decision = parse_negotiation_response(raw, state, player=0)
    assert decision.fell_back is False
    from foedus.core import Stance
    assert decision.press.stance == {1: Stance.ALLY}
    assert len(decision.press.intents) == 1
    assert len(decision.proposals) == 1
    assert decision.proposals[0].counterparty == 1
    assert len(decision.proposals[0].terms) == 2
    assert decision.accept_ids == [3]


def test_parse_negotiation_response_malformed_json_falls_back_safely() -> None:
    state = _two_unit_state()
    decision = parse_negotiation_response("not json at all { {{", state, player=0)
    assert decision.fell_back is True
    assert decision.press.stance == {}
    assert decision.press.intents == []
    assert decision.proposals == []
    assert decision.accept_ids == []


def test_parse_negotiation_response_missing_fields_defaults_empty() -> None:
    state = _two_unit_state()
    decision = parse_negotiation_response("{}", state, player=0)
    assert decision.press.stance == {}
    assert decision.press.intents == []
    assert decision.proposals == []
    assert decision.accept_ids == []


def test_parse_negotiation_response_drops_proposal_with_no_valid_terms() -> None:
    state = _two_unit_state()
    raw = json.dumps({
        "pacts": {"propose": [{"counterparty": 1, "terms": []}]},
    })
    decision = parse_negotiation_response(raw, state, player=0)
    assert decision.proposals == []


def test_parse_negotiation_response_wraps_prose_and_fences() -> None:
    state = _two_unit_state()
    raw = 'Here is my move:\n```json\n{"press": {"stance": {"1": "hostile"}}}\n```'
    decision = parse_negotiation_response(raw, state, player=0)
    from foedus.core import Stance
    assert decision.press.stance == {1: Stance.HOSTILE}
    assert decision.fell_back is False


def test_parse_negotiation_response_non_list_propose_does_not_crash() -> None:
    """Regression: a non-list truthy value for pacts.propose used to hit
    `raw or []` and crash iterating a scalar (`for x in 42`)."""
    state = _two_unit_state()
    raw = json.dumps({"pacts": {"propose": 42, "accept": []}})
    decision = parse_negotiation_response(raw, state, player=0)
    assert decision.proposals == []
    assert decision.fell_back is True


def test_parse_negotiation_response_non_list_accept_does_not_crash() -> None:
    state = _two_unit_state()
    raw = json.dumps({"pacts": {"propose": [], "accept": True}})
    decision = parse_negotiation_response(raw, state, player=0)
    assert decision.accept_ids == []
    assert decision.fell_back is True


def test_parse_negotiation_response_non_list_terms_does_not_crash() -> None:
    state = _two_unit_state()
    raw = json.dumps({
        "pacts": {"propose": [{"counterparty": 1, "terms": 3.14}], "accept": []},
    })
    decision = parse_negotiation_response(raw, state, player=0)
    assert decision.proposals == []
    assert decision.fell_back is True


def test_parse_negotiation_response_non_list_intents_does_not_crash() -> None:
    state = _two_unit_state()
    raw = json.dumps({"press": {"stance": {}, "intents": "not-a-list"}})
    decision = parse_negotiation_response(raw, state, player=0)
    assert decision.press.intents == []
    assert decision.fell_back is True


# --- parse_orders_response -----------------------------------------------


def test_parse_orders_response_valid() -> None:
    state = _two_unit_state()
    raw = json.dumps({"orders": {"0": {"type": "Move", "dest": 1}}})
    orders, fell_back, n_coerced = parse_orders_response(raw, state, player=0)
    assert orders == {0: Move(dest=1)}
    assert fell_back is False


def test_parse_orders_response_coerces_prefixed_unit_key() -> None:
    state = _two_unit_state()
    raw = json.dumps({"orders": {"u0": {"type": "Hold"}}})
    orders, fell_back, n_coerced = parse_orders_response(raw, state, player=0)
    assert orders == {0: Hold()}
    assert fell_back is False


def test_parse_orders_response_illegal_order_falls_back_to_hold() -> None:
    state = _two_unit_state()
    raw = json.dumps({"orders": {"0": {"type": "Move", "dest": 999}}})
    orders, fell_back, n_coerced = parse_orders_response(raw, state, player=0)
    assert orders == {0: Hold()}
    assert fell_back is True
    assert n_coerced >= 1


def test_parse_orders_response_omitted_unit_defaults_to_hold_without_fallback() -> None:
    """Omitting an owned unit is documented client shorthand for Hold (see
    foedus_press_play.py's own apply_commit), not a parse failure."""
    state = _two_unit_state()
    raw = json.dumps({"orders": {}})
    orders, fell_back, n_coerced = parse_orders_response(raw, state, player=0)
    assert orders == {0: Hold()}
    assert fell_back is False


def test_parse_orders_response_rejects_unowned_unit() -> None:
    state = _two_unit_state()
    raw = json.dumps({"orders": {"1": {"type": "Hold"}}})
    orders, fell_back, n_coerced = parse_orders_response(raw, state, player=0)
    # unit 1 isn't owned by player 0 -> dropped, own unit 0 defaults to Hold.
    assert orders == {0: Hold()}
    assert fell_back is True


def test_parse_orders_response_malformed_json_falls_back_all_hold() -> None:
    state = _two_unit_state()
    orders, fell_back, n_coerced = parse_orders_response("garbage", state, player=0)
    assert orders == {0: Hold()}
    assert fell_back is True
