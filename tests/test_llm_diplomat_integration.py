"""Deterministic integration tests for LLMDiplomat, driven end-to-end
through foedus.loop.play_game with StubLLMClient (no real model, CI-able).

Three ground-truth checks (First Light Phase 1 acceptance, see the
llm-diplomat design brief §7):
  1. A full game (1 LLMDiplomat vs 3 heuristics) completes without crashing.
  2. A scripted pact propose -> accept -> breach: p0 proposes a non-
     aggression pact, p1 accepts it next round, then p0 breaks it by
     attacking p1. A PactBreach only fires on a truly ACCEPTED pact, so
     seeing one is ground truth that acceptance -- not just proposal --
     actually happened (a proposed-then-never-accepted pact would simply
     expire with no signal at all, indistinguishable from "honored" on a
     weaker assertion).
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
from foedus.core import GameConfig, ReputationTally, Unit
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


def test_scripted_pact_propose_then_accept_then_breach_registers() -> None:
    """Proves the pact actually reached ACCEPTED, not just that a record
    was proposed and later expired -- both paths would otherwise leave
    `final.pacts == []` and `final.pact_breaches == {}` indistinguishably
    (a PROPOSED-only pact simply expires with no signal at all). Scripting
    p0 to break its ACCEPTED term in a way that harms p1 (H1 aggression,
    same harm_map() fixture as the intent-breach test below) only produces
    a PactBreach if `_verify_pact_terms` actually saw status ACCEPTED --
    ground truth for the accept, not just the propose.
    """
    m = harm_map()
    units = [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)]
    state = make_state(m, units, num_players=2, max_turns=2)

    propose_raw = _negotiate_json(pacts={
        "propose": [{
            "counterparty": 1,
            "terms": [
                {"player": 0, "unit_id": 0, "declared_order": {"type": "Hold"}},
                {"player": 1, "unit_id": 1, "declared_order": {"type": "Hold"}},
            ],
        }],
        "accept": [],
    })
    no_op = _negotiate_json()
    hold_orders = _orders_json({})
    # Turn 1: p0 breaks its ACCEPTED Hold term by attacking n1 (u0 Move +
    # u2 Support), dislodging p1's u1 -- the same H1 aggression pattern as
    # the intent-breach test, but against a pact term instead.
    breach_orders = _orders_json({
        "0": {"type": "Move", "dest": 1},
        "2": {"type": "Support", "target": 0},
    })

    # p0: turn0 propose+hold, turn1 no-op negotiate + the breaching orders.
    p0_client = StubLLMClient([propose_raw, hold_orders, no_op, breach_orders])
    # p1: turn0 no-op (pact doesn't exist yet at p1's turn-0 negotiate call),
    # turn0 orders, turn1 ACCEPT (pact 0 now visible, proposed last round),
    # turn1 orders.
    accept_raw = _negotiate_json(pacts={"propose": [], "accept": [0]})
    p1_client = StubLLMClient([no_op, hold_orders, accept_raw, hold_orders])

    agents = {0: LLMDiplomat(client=p0_client), 1: LLMDiplomat(client=p1_client)}
    final = play_game(agents, state=state)

    assert final.pacts == []  # consumed at finalize regardless of outcome
    breaches_seen_by_p1 = final.pact_breaches.get(1, [])
    assert len(breaches_seen_by_p1) == 1
    breach = breaches_seen_by_p1[0]
    assert breach.pact_id == 0
    assert breach.breacher == 0
    assert breach.term.unit_id == 0
    from foedus.core import Hold as _Hold
    assert breach.term.declared_order == _Hold()
    assert final.reputation.get(0, ReputationTally()).pact_breaches == 1


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
