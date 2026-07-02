"""Deterministic integration tests for LLMDiplomat, driven end-to-end
through foedus.loop.play_game with StubLLMClient (no real model, CI-able).

Three ground-truth checks (First Light Phase 1 acceptance, see the
llm-diplomat design brief §7):
  1. A full game (1 LLMDiplomat vs 3 heuristics) completes without crashing.
  2. A scripted pact propose -> accept round-trips through the engine's
     Pact lifecycle correctly (status flips PROPOSED -> ACCEPTED).
  3. A scripted lie (declare ALLY + a Hold intent, then actually dislodge
     that same ally) produces exactly one captured BetrayalObservation /
     reputation increment matching the script -- proving the parse/dispatch
     pipeline doesn't lose or corrupt the signal the engine already computes.
"""

from __future__ import annotations

import json

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat
from foedus.core import GameConfig, PactStatus, ReputationTally, Unit
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import initial_state

from tests.helpers import harm_map, make_state


def _negotiate_json(**overrides) -> str:
    body = {"press": {"stance": {}, "intents": []},
            "pacts": {"propose": [], "accept": []}}
    body.update(overrides)
    return json.dumps(body)


def _orders_json(orders: dict) -> str:
    return json.dumps({"orders": orders})


# --- 1. full game vs 3 heuristics ------------------------------------------


def test_full_game_vs_three_heuristics_completes() -> None:
    cfg = GameConfig(num_players=4, seed=11, max_turns=3, build_period=999)
    m = generate_map(4, seed=11, archetype=cfg.archetype, map_radius=cfg.map_radius)
    state = initial_state(cfg, m)

    # Constant no-op responses: neutral press, no pacts, all-Hold orders.
    # Both are turn-invariant (no ids referenced), so max_turns pairs of
    # (negotiate, orders) responses suffice regardless of map layout.
    responses = [_negotiate_json(), _orders_json({})] * cfg.max_turns
    llm = LLMDiplomat(client=StubLLMClient(responses))
    agents = {0: llm, 1: GreedyHold(), 2: GreedyHold(), 3: GreedyHold()}

    final = play_game(agents, state=state)

    assert final.is_terminal()
    assert llm.decision_log, "LLM seat should have made at least one decision"
    assert not any(r["fell_back"] for r in llm.decision_log)
    assert len(llm.decision_log) % 2 == 0, (
        "each round contributes exactly one negotiate + one orders record"
    )


# --- 2. scripted pact propose -> accept -------------------------------------


def test_scripted_pact_propose_then_accept_round_trips() -> None:
    cfg = GameConfig(num_players=2, max_turns=2, build_period=999,
                     detente_threshold=0)
    m = generate_map(2, seed=3, map_radius=2)
    state = initial_state(cfg, m)
    own_unit_p0 = next(u for u in state.units.values() if u.owner == 0)
    own_unit_p1 = next(u for u in state.units.values() if u.owner == 1)

    propose_raw = _negotiate_json(pacts={
        "propose": [{
            "counterparty": 1,
            "terms": [
                {"player": 0, "unit_id": own_unit_p0.id,
                 "declared_order": {"type": "Hold"}},
                {"player": 1, "unit_id": own_unit_p1.id,
                 "declared_order": {"type": "Hold"}},
            ],
        }],
        "accept": [],
    })
    no_op = _negotiate_json()
    hold_orders = _orders_json({})

    # p0: turn0 propose, turn0 orders, turn1 no-op, turn1 orders.
    p0_client = StubLLMClient([propose_raw, hold_orders, no_op, hold_orders])
    # p1: turn0 no-op (pact doesn't exist yet at p1's turn-0 negotiate call),
    # turn0 orders, turn1 ACCEPT (pact 0 now visible, proposed last round),
    # turn1 orders.
    accept_raw = _negotiate_json(pacts={"propose": [], "accept": [0]})
    p1_client = StubLLMClient([no_op, hold_orders, accept_raw, hold_orders])

    agents = {0: LLMDiplomat(client=p0_client), 1: LLMDiplomat(client=p1_client)}
    final = play_game(agents, state=state)

    # The pact was proposed turn 0, accepted turn 1, both parties Held
    # (honoring it) -> consumed as an honored ACCEPTED pact, no breach.
    assert final.pacts == []
    assert final.pact_breaches == {}


# --- 3. scripted lie -> ground-truth breach ---------------------------------


def test_scripted_lie_produces_exactly_one_betrayal_matching_the_script() -> None:
    """p0 declares ALLY toward p1 + a Hold intent for u0, then actually
    submits Move(u0->n1)+Support(u2->u0), dislodging p1's unit at n1 -- H1
    aggression against a declared ally. Reuses tests/helpers.harm_map(),
    the shared fixture for harm-typed breach scenarios.
    """
    m = harm_map()
    units = [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)]
    state = make_state(m, units, num_players=2, max_turns=1)

    lie_negotiate = _negotiate_json(
        press={"stance": {"1": "ally"}, "intents": [
            {"unit_id": 0, "declared_order": {"type": "Hold"},
             "visible_to": None},
        ]},
    )
    lie_orders = _orders_json({
        "0": {"type": "Move", "dest": 1},
        "2": {"type": "Support", "target": 0},
    })
    p0_client = StubLLMClient([lie_negotiate, lie_orders])
    p1_client = StubLLMClient([_negotiate_json(), _orders_json({"1": {"type": "Hold"}})])

    agents = {0: LLMDiplomat(client=p0_client), 1: LLMDiplomat(client=p1_client)}
    final = play_game(agents, state=state)

    assert final.reputation.get(0, ReputationTally()).intent_breaches == 1
    betrayals_seen_by_p1 = final.betrayals.get(1, [])
    assert len(betrayals_seen_by_p1) == 1
    obs = betrayals_seen_by_p1[0]
    assert obs.betrayer == 0
    assert obs.intent.unit_id == 0
    from foedus.core import Hold as _Hold
    assert obs.intent.declared_order == _Hold()
