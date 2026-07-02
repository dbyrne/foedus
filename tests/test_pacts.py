"""Pact lifecycle: propose -> accept -> honor/breach at finalize.

Mirrors the rigor of tests/test_score_delta.py: constructs a Pact, plays
honored vs breached orders, and asserts exactly the right breach signals,
plus the load-bearing invariant that a Pact is a *commitment record* — it
never changes how orders resolve.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    Hold,
    Move,
    Pact,
    PactStatus,
    PactTerm,
    Phase,
    Press,
    Support,
    Unit,
)
from foedus.fog import visible_state_for
from foedus.press import (
    accept_pact,
    finalize_round,
    propose_pact,
    signal_done,
    submit_press_tokens,
)

from tests.helpers import line_map, make_state


# --- fixtures ---------------------------------------------------------------


def _joint_move_state():
    """line_map(5): 0(H,p0)-1$-2$-3$-4(H,p1), 3 players.

    p0 attacker u3@n1, p1 supporter u4@n3, p2 defender u2@n2. Mirrors the
    combat+cross-player-support scenario in test_score_delta so the honored
    resolution is a known-good reference.
    """
    m = line_map(5)
    u0 = Unit(0, 0, 0)   # p0 home
    u1 = Unit(1, 1, 4)   # p1 home
    u2 = Unit(2, 2, 2)   # p2 defender
    u3 = Unit(3, 0, 1)   # p0 attacker
    u4 = Unit(4, 1, 3)   # p1 supporter
    return make_state(m, [u0, u1, u2, u3, u4], num_players=3)


def _pact_terms_p0_p1():
    return (
        PactTerm(player=0, unit_id=3, declared_order=Move(dest=2)),
        PactTerm(player=1, unit_id=4, declared_order=Support(target=3)),
    )


# --- harm-typed breach fixture ----------------------------------------------
#
# Post-2026-07-02, a pact breach only registers when it HARMS the co-signer
# (Primitive A). The joint-MOVE pact above is breached by a harmless no-show
# (the attack merely fizzles), which is no longer a breach. This symmetric
# non-aggression fixture lets EITHER party breach by actually stabbing the
# other: each has a stationary "target" unit the other can gang 2-vs-1.
#
#   p0: target uT0@10 (+home), attackers uA@21,uB@22 flanking p1's target @20
#   p1: target uT1@20 (+home), attackers uC@11,uD@12 flanking p0's target @10
#   p2: isolated observer uP2@99 (sees nothing) — keeps the 3-player fog checks

from foedus.core import GameState, Map, NodeType  # noqa: E402


def _pact_harm_map() -> Map:
    coords = {10: (0, 0), 20: (5, 0), 21: (5, 1), 22: (6, 0),
              11: (0, 1), 12: (1, 0), 99: (9, 9)}
    edges = {
        10: frozenset({11, 12}),
        20: frozenset({21, 22}),
        21: frozenset({20}), 22: frozenset({20}),
        11: frozenset({10}), 12: frozenset({10}),
        99: frozenset(),
    }
    node_types = {10: NodeType.SUPPLY, 20: NodeType.SUPPLY,
                  21: NodeType.PLAIN, 22: NodeType.PLAIN,
                  11: NodeType.PLAIN, 12: NodeType.PLAIN,
                  99: NodeType.HOME}
    return Map(coords=coords, edges=edges, node_types=node_types,
               home_assignments={99: 2})


def _pact_harm_state() -> GameState:
    m = _pact_harm_map()
    units = [
        Unit(0, 0, 10), Unit(1, 0, 21), Unit(2, 0, 22),   # p0: target + 2 attackers
        Unit(3, 1, 20), Unit(4, 1, 11), Unit(5, 1, 12),   # p1: target + 2 attackers
        Unit(6, 2, 99),                                    # p2: isolated observer
    ]
    ownership = {n: None for n in m.nodes}
    ownership[99] = 2
    for u in units:
        ownership[u.location] = u.owner
    cfg = GameConfig(num_players=3, max_turns=50, build_period=999,
                     detente_threshold=0, high_value_supply_fraction=0.0)
    return GameState(
        turn=0, map=m, units={u.id: u for u in units}, ownership=ownership,
        scores={p: 0.0 for p in range(3)}, eliminated=set(),
        next_unit_id=7, config=cfg,
    )


# Non-aggression pact: each party's forward attacker promises to Hold.
def _nonaggression_terms():
    return (
        PactTerm(player=0, unit_id=1, declared_order=Hold()),
        PactTerm(player=1, unit_id=4, declared_order=Hold()),
    )


# p0 stabs p1's target @20 (uA moves in, uB backs); p1 honors.
_P0_STAB = {
    0: {0: Hold(), 1: Move(dest=20), 2: Support(target=1)},
    1: {3: Hold(), 4: Hold(), 5: Hold()},
    2: {6: Hold()},
}
# p1 stabs p0's target @10 (uC moves in, uD backs); p0 honors.
_P1_STAB = {
    0: {0: Hold(), 1: Hold(), 2: Hold()},
    1: {3: Hold(), 4: Move(dest=10), 5: Support(target=4)},
    2: {6: Hold()},
}
# Both stab simultaneously.
_BOTH_STAB = {
    0: {0: Hold(), 1: Move(dest=20), 2: Support(target=1)},
    1: {3: Hold(), 4: Move(dest=10), 5: Support(target=4)},
    2: {6: Hold()},
}


def _run_finalize(state, orders):
    """Submit empty press + signal done for all survivors, then finalize."""
    for p in range(state.config.num_players):
        if p in state.eliminated:
            continue
        if p not in state.round_press_pending:
            state = submit_press_tokens(state, p, Press(stance={}, intents=[]))
        state = signal_done(state, p)
    return finalize_round(state, orders)


# --- propose_pact -----------------------------------------------------------


def test_propose_pact_creates_proposed_pact() -> None:
    s = _joint_move_state()
    s2 = propose_pact(s, proposer=0, counterparty=1, terms=_pact_terms_p0_p1())
    assert len(s2.pacts) == 1
    p = s2.pacts[0]
    assert p.proposer == 0
    assert p.counterparty == 1
    assert p.status == PactStatus.PROPOSED
    assert p.proposed_turn == s.turn
    assert p.pact_id == 0
    assert s2.next_pact_id == 1


def test_propose_pact_assigns_monotonic_ids() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s = propose_pact(s, 0, 2, (
        PactTerm(player=0, unit_id=3, declared_order=Hold()),
        PactTerm(player=2, unit_id=2, declared_order=Hold()),
    ))
    assert [p.pact_id for p in s.pacts] == [0, 1]
    assert s.next_pact_id == 2


def test_propose_pact_drops_terms_for_third_parties() -> None:
    s = _joint_move_state()
    terms = (
        PactTerm(player=0, unit_id=3, declared_order=Move(dest=2)),
        PactTerm(player=1, unit_id=4, declared_order=Support(target=3)),
        PactTerm(player=2, unit_id=2, declared_order=Hold()),  # third party!
    )
    s2 = propose_pact(s, 0, 1, terms)
    assert len(s2.pacts) == 1
    kept = {(t.player, t.unit_id) for t in s2.pacts[0].terms}
    assert kept == {(0, 3), (1, 4)}


def test_propose_pact_drops_terms_for_unowned_units() -> None:
    s = _joint_move_state()
    terms = (
        PactTerm(player=0, unit_id=3, declared_order=Move(dest=2)),
        # p1 claims p0's unit u3 -> ownership mismatch, dropped.
        PactTerm(player=1, unit_id=3, declared_order=Hold()),
        PactTerm(player=1, unit_id=4, declared_order=Support(target=3)),
    )
    s2 = propose_pact(s, 0, 1, terms)
    kept = {(t.player, t.unit_id) for t in s2.pacts[0].terms}
    assert kept == {(0, 3), (1, 4)}


def test_propose_pact_dedupes_conflicting_terms_on_same_unit() -> None:
    """Review I1: a proposer must not be able to stack two obligations on one
    unit. Duplicate unit_ids keep the first term; later ones are dropped."""
    s = _joint_move_state()
    terms = (
        PactTerm(player=0, unit_id=3, declared_order=Move(dest=2)),
        PactTerm(player=1, unit_id=4, declared_order=Support(target=3)),
        PactTerm(player=1, unit_id=4, declared_order=Hold()),  # conflicts
    )
    s2 = propose_pact(s, 0, 1, terms)
    u4_terms = [t for t in s2.pacts[0].terms if t.unit_id == 4]
    assert len(u4_terms) == 1
    assert u4_terms[0].declared_order == Support(target=3)


def test_conflicting_terms_cannot_manufacture_false_breach() -> None:
    """Review I1: with conflicting terms deduped, a fully-complying
    counterparty must never be reported as a breacher."""
    s = _joint_move_state()
    terms = (
        PactTerm(player=0, unit_id=3, declared_order=Move(dest=2)),
        PactTerm(player=1, unit_id=4, declared_order=Support(target=3)),
        PactTerm(player=1, unit_id=4, declared_order=Hold()),
    )
    s = propose_pact(s, 0, 1, terms)
    s = accept_pact(s, 0, 1)
    orders = {
        0: {3: Move(dest=2), 0: Hold()},
        1: {4: Support(target=3), 1: Hold()},  # complies with the one term
        2: {2: Hold()},
    }
    s2 = _run_finalize(s, orders)
    assert s2.pact_breaches == {}


def test_propose_pact_dropped_when_a_party_has_no_valid_term() -> None:
    """A genuine joint commitment needs >=1 term from EACH party."""
    s = _joint_move_state()
    one_sided = (PactTerm(player=0, unit_id=3, declared_order=Move(dest=2)),)
    s2 = propose_pact(s, 0, 1, one_sided)
    assert s2.pacts == []
    assert s2.next_pact_id == 0


def test_propose_pact_noop_when_not_negotiation() -> None:
    s = replace(_joint_move_state(), phase=Phase.ORDERS)
    s2 = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    assert s2.pacts == []


def test_propose_pact_noop_when_proposer_done() -> None:
    s = _joint_move_state()
    s = signal_done(s, 0)
    s2 = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    assert s2.pacts == []


def test_propose_pact_noop_when_self_pact() -> None:
    s = _joint_move_state()
    s2 = propose_pact(s, 0, 0, _pact_terms_p0_p1())
    assert s2.pacts == []


def test_propose_pact_noop_when_counterparty_eliminated() -> None:
    s = _joint_move_state()
    s.eliminated.add(1)
    s2 = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    assert s2.pacts == []


# --- accept_pact ------------------------------------------------------------


def test_accept_pact_flips_status() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s2 = accept_pact(s, pact_id=0, accepter=1)
    assert s2.pacts[0].status == PactStatus.ACCEPTED


def test_accept_pact_noop_for_non_counterparty() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s2 = accept_pact(s, pact_id=0, accepter=2)
    assert s2.pacts[0].status == PactStatus.PROPOSED


def test_accept_pact_noop_for_unknown_id() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s2 = accept_pact(s, pact_id=99, accepter=1)
    assert s2.pacts[0].status == PactStatus.PROPOSED


def test_accept_pact_noop_when_accepter_done() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s = signal_done(s, 1)
    s2 = accept_pact(s, pact_id=0, accepter=1)
    assert s2.pacts[0].status == PactStatus.PROPOSED


def test_accept_pact_noop_when_proposer_eliminated() -> None:
    """Review (minor): you can't ratify a commitment with a party who no
    longer exists."""
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s.eliminated.add(0)
    s2 = accept_pact(s, pact_id=0, accepter=1)
    assert s2.pacts[0].status == PactStatus.PROPOSED


def test_proposal_with_eliminated_party_not_carried_forward() -> None:
    """Review (minor): a dangling proposal whose counterparty was eliminated
    this round must not linger (it would render 'awaiting p<dead>' next
    round). It's dropped at finalize rather than surviving."""
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    # p1 eliminated before this round resolves (units + a lost home).
    s.eliminated.add(1)
    del s.units[1]
    del s.units[4]
    orders = {0: {3: Hold(), 0: Hold()}, 2: {2: Hold()}}
    s2 = _run_finalize(s, orders)
    assert 1 in s2.eliminated
    assert s2.pacts == []


def test_accept_pact_idempotent() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s = accept_pact(s, 0, 1)
    s2 = accept_pact(s, 0, 1)
    assert s2.pacts[0].status == PactStatus.ACCEPTED
    assert len(s2.pacts) == 1


# --- breach detection at finalize -------------------------------------------


def test_honored_pact_emits_no_breach() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s = accept_pact(s, 0, 1)
    orders = {
        0: {3: Move(dest=2), 0: Hold()},
        1: {4: Support(target=3), 1: Hold()},
        2: {2: Hold()},
    }
    s2 = _run_finalize(s, orders)
    assert s2.pact_breaches == {}


def test_breach_by_counterparty_observed_by_proposer() -> None:
    s = _pact_harm_state()
    s = propose_pact(s, 0, 1, _nonaggression_terms())
    s = accept_pact(s, 0, 1)
    # p1 breaches its non-aggression term by STABBING p0's target unit.
    s2 = _run_finalize(s, _P1_STAB)
    # Proposer p0 (the harmed party) observes; breacher p1 does not.
    assert set(s2.pact_breaches) == {0}
    breaches = s2.pact_breaches[0]
    assert len(breaches) == 1
    b = breaches[0]
    assert b.breacher == 1
    assert b.pact_id == 0
    assert b.term == PactTerm(player=1, unit_id=4, declared_order=Hold())
    assert b.actual_order == Move(dest=10)
    assert b.turn == s.turn + 1


def test_breach_by_proposer_observed_by_counterparty() -> None:
    s = _pact_harm_state()
    s = propose_pact(s, 0, 1, _nonaggression_terms())
    s = accept_pact(s, 0, 1)
    # p0 breaches by stabbing p1's target unit.
    s2 = _run_finalize(s, _P0_STAB)
    assert set(s2.pact_breaches) == {1}
    b = s2.pact_breaches[1][0]
    assert b.breacher == 0
    assert b.term.unit_id == 1
    assert b.actual_order == Move(dest=20)


def test_both_parties_breach_each_observes_the_other() -> None:
    s = _pact_harm_state()
    s = propose_pact(s, 0, 1, _nonaggression_terms())
    s = accept_pact(s, 0, 1)
    # Both stab simultaneously -> both breaches harm the co-signer.
    s2 = _run_finalize(s, _BOTH_STAB)
    assert set(s2.pact_breaches) == {0, 1}
    assert s2.pact_breaches[0][0].breacher == 1
    assert s2.pact_breaches[1][0].breacher == 0


def test_proposed_but_unaccepted_pact_is_not_breach_checked() -> None:
    """Only ACCEPTED pacts bind. A dangling proposal is never a breach."""
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    # never accepted
    orders = {
        0: {3: Hold(), 0: Hold()},
        1: {4: Hold(), 1: Hold()},
        2: {2: Hold()},
    }
    s2 = _run_finalize(s, orders)
    assert s2.pact_breaches == {}


def test_void_term_when_unit_lost_is_not_breach() -> None:
    """A term for a unit the party no longer owns at finalize is void."""
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s = accept_pact(s, 0, 1)
    # Remove p1's supporter unit before finalize (as if lost). p1 can't
    # fulfil a term for a unit it doesn't own -> no breach.
    del s.units[4]
    orders = {
        0: {3: Move(dest=2), 0: Hold()},
        1: {1: Hold()},
        2: {2: Hold()},
    }
    s2 = _run_finalize(s, orders)
    assert s2.pact_breaches == {}


# --- consumption + expiry ---------------------------------------------------


def test_accepted_pact_consumed_after_finalize() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s = accept_pact(s, 0, 1)
    orders = {
        0: {3: Move(dest=2), 0: Hold()},
        1: {4: Support(target=3), 1: Hold()},
        2: {2: Hold()},
    }
    s2 = _run_finalize(s, orders)
    assert s2.pacts == []


def test_unaccepted_proposal_survives_one_round_then_expires() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    hold_orders = {
        0: {3: Hold(), 0: Hold()},
        1: {4: Hold(), 1: Hold()},
        2: {2: Hold()},
    }
    # Round 0 finalize: proposed this round -> survives.
    s1 = _run_finalize(s, hold_orders)
    assert len(s1.pacts) == 1
    assert s1.pacts[0].status == PactStatus.PROPOSED
    assert s1.turn == 1
    # Round 1 finalize without acceptance: proposed_turn(0) < turn(1) -> expires.
    s2 = _run_finalize(s1, hold_orders)
    assert s2.pacts == []


def test_proposal_accepted_next_round_binds() -> None:
    s = _pact_harm_state()
    s = propose_pact(s, 0, 1, _nonaggression_terms())
    all_hold = {
        0: {0: Hold(), 1: Hold(), 2: Hold()},
        1: {3: Hold(), 4: Hold(), 5: Hold()},
        2: {6: Hold()},
    }
    s1 = _run_finalize(s, all_hold)   # turn -> 1, pact still PROPOSED
    s1 = accept_pact(s1, 0, 1)
    assert s1.pacts[0].status == PactStatus.ACCEPTED
    # p1 now breaches at round 1's resolution by stabbing p0.
    s2 = _run_finalize(s1, _P1_STAB)
    assert set(s2.pact_breaches) == {0}
    assert s2.pact_breaches[0][0].breacher == 1
    assert s2.pact_breaches[0][0].turn == 2


# --- the load-bearing invariant: a Pact never changes resolution -----------


def test_honored_pact_resolves_identically_to_no_pact() -> None:
    orders = {
        0: {3: Move(dest=2), 0: Hold()},
        1: {4: Support(target=3), 1: Hold()},
        2: {2: Hold()},
    }
    # With a ratified + honored pact.
    s_pact = _joint_move_state()
    s_pact = propose_pact(s_pact, 0, 1, _pact_terms_p0_p1())
    s_pact = accept_pact(s_pact, 0, 1)
    r_pact = _run_finalize(s_pact, orders)
    # Without any pact.
    s_none = _joint_move_state()
    r_none = _run_finalize(s_none, orders)

    assert r_pact.scores == r_none.scores
    assert r_pact.last_turn_score_delta == r_none.last_turn_score_delta
    assert r_pact.ownership == r_none.ownership
    assert r_pact.units == r_none.units
    assert r_pact.eliminated == r_none.eliminated
    # Reference values from test_score_delta's known-good scenario. The
    # alliance bonus (+3 mover / +3 supporter) now fires on this cross-player
    # supported capture — the aid-spend gate was deleted and the mover passes
    # the reciprocation gate (no ally support taken yet).
    assert r_none.scores == {0: 7.0, 1: 6.0, 2: 0.0}


# --- fog visibility ---------------------------------------------------------


def test_fog_exposes_pact_to_both_parties_only() -> None:
    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s = accept_pact(s, 0, 1)
    for party in (0, 1):
        view = visible_state_for(s, party)
        ids = [p.pact_id for p in view["your_pacts"]]
        assert ids == [0], f"party {party} should see the pact"
    # Third party sees nothing.
    assert visible_state_for(s, 2)["your_pacts"] == []


def test_fog_exposes_pact_breaches_to_observer_only() -> None:
    s = _pact_harm_state()
    s = propose_pact(s, 0, 1, _nonaggression_terms())
    s = accept_pact(s, 0, 1)
    s2 = _run_finalize(s, _P1_STAB)   # p1 breaches by stabbing p0
    assert len(visible_state_for(s2, 0)["your_pact_breaches"]) == 1
    assert visible_state_for(s2, 1)["your_pact_breaches"] == []
    assert visible_state_for(s2, 2)["your_pact_breaches"] == []


# --- play_game agent-hook integration (loop.py) -----------------------------


from foedus.agents.base import Agent  # noqa: E402
from foedus.core import GameConfig, PactProposal  # noqa: E402
from foedus.loop import play_game  # noqa: E402


class _NoHookAgent(Agent):
    """Agent with no pact hooks — must still play fine (backward compat)."""

    def choose_orders(self, state, player):
        return {u.id: Hold() for u in state.units_of(player)}


class _ScriptedPactAgent(Agent):
    """P0 proposes a Hold/Hold pact to P1 on turn 0; P1 accepts inbound
    proposals. Each player's `breach` flag decides whether it honors its
    own term or defects by moving.
    """

    def __init__(self, seat, *, propose_to=None, breach=False):
        self.seat = seat
        self.propose_to = propose_to
        self.breach = breach

    def choose_orders(self, state, player):
        orders = {}
        for u in state.units_of(player):
            if self.breach:
                # Defect: move toward the middle node 1 if adjacent.
                nbrs = sorted(state.map.neighbors(u.location))
                if 1 in nbrs:
                    orders[u.id] = Move(dest=1)
                    continue
            orders[u.id] = Hold()
        return orders

    def choose_pacts(self, state, player):
        if self.propose_to is None or state.turn != 0:
            return []
        my_units = state.units_of(player)
        their_units = state.units_of(self.propose_to)
        if not my_units or not their_units:
            return []
        terms = (
            PactTerm(player=player, unit_id=my_units[0].id,
                     declared_order=Hold()),
            PactTerm(player=self.propose_to, unit_id=their_units[0].id,
                     declared_order=Hold()),
        )
        return [PactProposal(counterparty=self.propose_to, terms=terms)]

    def accept_pacts(self, state, player):
        return [
            p.pact_id for p in state.pacts
            if p.counterparty == player and p.status == PactStatus.PROPOSED
        ]


def _one_turn_state():
    """Explicit line_map(3): 0(H,p0)-1$-2(H,p1), one turn, no détente."""
    m = line_map(3)
    return make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)],
                      num_players=2, max_turns=1)


def test_play_game_runs_without_pact_hooks() -> None:
    final = play_game({0: _NoHookAgent(), 1: _NoHookAgent()},
                      state=_one_turn_state())
    assert final.is_terminal()
    assert final.pact_breaches == {}


def test_play_game_honored_pact_records_no_breach() -> None:
    agents = {
        0: _ScriptedPactAgent(0, propose_to=1, breach=False),
        1: _ScriptedPactAgent(1, breach=False),
    }
    final = play_game(agents, state=_one_turn_state())
    assert final.pact_breaches == {}


class _NonAggressionProposer(Agent):
    """p0: proposes a uA-Hold / uC-Hold non-aggression pact to p1, then honors
    it (Holds everything)."""

    def choose_orders(self, state, player):
        return {u.id: Hold() for u in state.units_of(player)}

    def choose_pacts(self, state, player):
        if state.turn != 0:
            return []
        return [PactProposal(counterparty=1, terms=(
            PactTerm(player=0, unit_id=1, declared_order=Hold()),
            PactTerm(player=1, unit_id=4, declared_order=Hold()),
        ))]


class _StabbingAccepter(Agent):
    """p1: accepts inbound proposals, then breaches by stabbing p0's target
    unit @10 (uC moves in, uD backs it) — a harm-typed pact breach."""

    def choose_orders(self, state, player):
        return {3: Hold(), 4: Move(dest=10), 5: Support(target=4)}

    def accept_pacts(self, state, player):
        return [p.pact_id for p in state.pacts
                if p.counterparty == player and p.status == PactStatus.PROPOSED]


def test_play_game_breached_pact_records_breach_via_hooks() -> None:
    s = replace(_pact_harm_state(), config=replace(
        _pact_harm_state().config, max_turns=1))
    agents = {
        0: _NonAggressionProposer(),
        1: _StabbingAccepter(),      # accepts, then stabs p0 (harmful breach)
        2: _NoHookAgent(),
    }
    final = play_game(agents, state=s)
    # P0 (the harmed proposer) observes P1's harmful breach.
    assert set(final.pact_breaches) == {0}
    assert final.pact_breaches[0][0].breacher == 1


# --- wire protocol: pacts are deliberately press-layer (omitted) ------------


def test_wire_omits_pacts_and_round_trips_clean() -> None:
    """F5 pacts are press-layer, not needed for remote choose_orders, so the
    wire format omits them (like Press v0 fields). A state carrying pacts +
    breaches must still serialize and deserialize without error, coming back
    with the press-layer fields defaulted empty."""
    from foedus.remote.wire import deserialize_state, serialize_state

    s = _joint_move_state()
    s = propose_pact(s, 0, 1, _pact_terms_p0_p1())
    s = accept_pact(s, 0, 1)
    s.pact_breaches[0] = [
        # a plausible breach entry to prove serialization doesn't choke
    ]
    blob = serialize_state(s)
    assert "pacts" not in blob
    assert "pact_breaches" not in blob
    restored = deserialize_state(blob)
    assert restored.pacts == []
    assert restored.pact_breaches == {}
    assert restored.next_pact_id == 0
