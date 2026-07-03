"""Tests for foedus.agents.llm.diplomat.LLMDiplomat — the in-process Agent.

Uses StubLLMClient throughout (deterministic, no network/model). Verifies
the Agent-protocol surface, the one-negotiation-call-per-round cache
(shared by choose_press/choose_pacts/accept_pacts), the separate
per-round orders call, robust fallback on malformed output, and the
per-decision log.
"""

from __future__ import annotations

import json

from foedus.agents.base import Agent
from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat
from foedus.core import Hold, Move, PactProposal, Press, Stance

from tests.helpers import simple_two_player_state


def _negotiate_json(**overrides) -> str:
    body = {"press": {"stance": {}, "intents": []},
            "pacts": {"propose": [], "accept": []}}
    body.update(overrides)
    return json.dumps(body)


def _orders_json(orders: dict) -> str:
    return json.dumps({"orders": orders})


def test_llm_diplomat_is_a_valid_agent() -> None:
    diplomat = LLMDiplomat(client=StubLLMClient([]))
    assert isinstance(diplomat, Agent)


def test_choose_press_returns_parsed_press() -> None:
    state = simple_two_player_state()
    raw = _negotiate_json(press={"stance": {"1": "ally"}, "intents": []})
    diplomat = LLMDiplomat(client=StubLLMClient([raw]))
    press = diplomat.choose_press(state, 0)
    assert press.stance == {1: Stance.ALLY}


def test_negotiation_call_is_shared_across_press_pacts_and_accept() -> None:
    """choose_press, choose_pacts, and accept_pacts for the SAME round must
    trigger exactly ONE LLM call — they all read the same fogged view."""
    state = simple_two_player_state()
    own_unit = next(u for u in state.units.values() if u.owner == 0)
    raw = _negotiate_json(pacts={
        "propose": [{"counterparty": 1, "terms": [
            {"player": 0, "unit_id": own_unit.id,
             "declared_order": {"type": "Hold"}},
        ]}],
        "accept": [],
    })
    client = StubLLMClient([raw])
    diplomat = LLMDiplomat(client=client)

    diplomat.choose_press(state, 0)
    diplomat.choose_pacts(state, 0)
    diplomat.accept_pacts(state, 0)

    assert len(client.calls) == 1


def test_choose_pacts_returns_pact_proposals() -> None:
    state = simple_two_player_state()
    own_unit = next(u for u in state.units.values() if u.owner == 0)
    raw = _negotiate_json(pacts={
        "propose": [{"counterparty": 1, "terms": [
            {"player": 0, "unit_id": own_unit.id,
             "declared_order": {"type": "Hold"}},
        ]}],
        "accept": [],
    })
    diplomat = LLMDiplomat(client=StubLLMClient([raw]))
    proposals = diplomat.choose_pacts(state, 0)
    assert len(proposals) == 1
    assert isinstance(proposals[0], PactProposal)
    assert proposals[0].counterparty == 1


def test_accept_pacts_returns_ids() -> None:
    state = simple_two_player_state()
    raw = _negotiate_json(pacts={"propose": [], "accept": [7]})
    diplomat = LLMDiplomat(client=StubLLMClient([raw]))
    assert diplomat.accept_pacts(state, 0) == [7]


def test_choose_orders_is_a_separate_call_from_negotiation() -> None:
    state = simple_two_player_state()
    own_unit = next(u for u in state.units.values() if u.owner == 0)
    client = StubLLMClient([
        _negotiate_json(),
        _orders_json({str(own_unit.id): {"type": "Hold"}}),
    ])
    diplomat = LLMDiplomat(client=client)
    diplomat.choose_press(state, 0)
    orders = diplomat.choose_orders(state, 0)
    assert orders[own_unit.id] == Hold()
    assert len(client.calls) == 2


def test_choose_orders_works_without_a_prior_negotiation_call() -> None:
    """A driver/test may call choose_orders directly; must not crash."""
    state = simple_two_player_state()
    own_unit = next(u for u in state.units.values() if u.owner == 0)
    client = StubLLMClient([_orders_json({str(own_unit.id): {"type": "Hold"}})])
    diplomat = LLMDiplomat(client=client)
    orders = diplomat.choose_orders(state, 0)
    assert orders[own_unit.id] == Hold()


def test_malformed_negotiation_response_falls_back_to_neutral_press() -> None:
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=StubLLMClient(["not json at all"]))
    press = diplomat.choose_press(state, 0)
    assert press == Press(stance={}, intents=[])


def test_malformed_orders_response_falls_back_to_all_hold() -> None:
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=StubLLMClient(["not json at all"]))
    orders = diplomat.choose_orders(state, 0)
    own_unit_ids = {u.id for u in state.units.values() if u.owner == 0}
    assert set(orders) == own_unit_ids
    assert all(o == Hold() for o in orders.values())


def test_chat_drafts_defaults_to_empty() -> None:
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=StubLLMClient([]))
    assert diplomat.chat_drafts(state, 0) == []


def test_decision_log_records_negotiate_and_orders_phases() -> None:
    state = simple_two_player_state()
    own_unit = next(u for u in state.units.values() if u.owner == 0)
    client = StubLLMClient([
        _negotiate_json(),
        _orders_json({str(own_unit.id): {"type": "Hold"}}),
    ])
    diplomat = LLMDiplomat(client=client)
    diplomat.choose_press(state, 0)
    diplomat.choose_orders(state, 0)

    assert len(diplomat.decision_log) == 2
    phases = [r["phase"] for r in diplomat.decision_log]
    assert phases == ["negotiate", "orders"]
    for record in diplomat.decision_log:
        assert record["turn"] == state.turn
        assert record["player"] == 0
        assert "prompt" in record
        assert "raw_response" in record
        assert "fell_back" in record


def test_decision_log_flags_fell_back_on_malformed_output() -> None:
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=StubLLMClient(["garbage"]))
    diplomat.choose_press(state, 0)
    assert diplomat.decision_log[0]["fell_back"] is True


class _RaisingClient:
    """Simulates a transport/backend failure (network error, timeout,
    non-2xx response) rather than a bad-but-present LLM response."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        raise self._exc


def test_negotiate_transport_error_falls_back_to_neutral_press() -> None:
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=_RaisingClient(ConnectionError("refused")))
    press = diplomat.choose_press(state, 0)
    assert press == Press(stance={}, intents=[])
    assert diplomat.decision_log[0]["fell_back"] is True
    assert "refused" in diplomat.decision_log[0]["raw_response"]


def test_orders_transport_error_falls_back_to_all_hold() -> None:
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=_RaisingClient(TimeoutError("timed out")))
    orders = diplomat.choose_orders(state, 0)
    own_unit_ids = {u.id for u in state.units.values() if u.owner == 0}
    assert set(orders) == own_unit_ids
    assert all(o == Hold() for o in orders.values())
    assert diplomat.decision_log[0]["fell_back"] is True


def test_transport_error_does_not_prevent_a_later_successful_call() -> None:
    """A game must survive one bad turn, not just one bad decision."""
    state = simple_two_player_state()
    client = _RaisingClient(ConnectionError("refused"))
    diplomat = LLMDiplomat(client=client)
    diplomat.choose_press(state, 0)
    assert diplomat.decision_log[0]["fell_back"] is True
    assert client.calls == 1


def test_caches_are_keyed_by_turn_and_player_not_turn_alone() -> None:
    """Regression: a single LLMDiplomat instance handed to two seats must
    not leak one player's negotiate/orders decision to the other."""
    state = simple_two_player_state()
    own_unit_p0 = next(u for u in state.units.values() if u.owner == 0)
    own_unit_p1 = next(u for u in state.units.values() if u.owner == 1)

    p0_negotiate = json.dumps({
        "press": {"stance": {"1": "hostile"}, "intents": []},
        "pacts": {"propose": [], "accept": []},
    })
    p1_negotiate = json.dumps({
        "press": {"stance": {"0": "ally"}, "intents": []},
        "pacts": {"propose": [], "accept": []},
    })
    p0_orders = json.dumps({"orders": {str(own_unit_p0.id): {"type": "Hold"}}})
    p1_orders = json.dumps({"orders": {str(own_unit_p1.id): {"type": "Hold"}}})

    client = StubLLMClient([p0_negotiate, p1_negotiate, p0_orders, p1_orders])
    diplomat = LLMDiplomat(client=client)

    press0 = diplomat.choose_press(state, 0)
    press1 = diplomat.choose_press(state, 1)
    assert press0.stance == {1: Stance.HOSTILE}
    assert press1.stance == {0: Stance.ALLY}

    orders0 = diplomat.choose_orders(state, 0)
    orders1 = diplomat.choose_orders(state, 1)
    assert set(orders0) == {own_unit_p0.id}
    assert set(orders1) == {own_unit_p1.id}
    assert len(client.calls) == 4
