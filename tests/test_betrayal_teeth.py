"""Betrayal teeth, harm-typed (2026-07-02 reciprocity model).

A broken declared Intent or accepted Pact term now costs the breacher a score
penalty + a public reputation increment ONLY when the divergence harmed a
committed party (Primitive A — see tests/test_harm_typed_breaches.py for the
harm/no-harm boundary). This file exercises the *teeth* on confirmed-harmful
breaches: penalty amounts, once-per-breach counting, observer-eliminated
accounting, reputation ledger, and wire/fog exposure.

The pre-redesign version of this file fined *any* per-unit order deviation,
which conflated pro-social redirects (Cooperator's Move->Support) with stabs;
those flat-fine scenarios are gone — the fine is now reserved for harm.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Intent,
    Move,
    Pact,
    PactStatus,
    PactTerm,
    Press,
    ReputationTally,
    Stance,
    Support,
    Unit,
)
from foedus.fog import visible_state_for
from foedus.press import finalize_round, signal_done, submit_press_tokens

from tests.helpers import harm_map, line_map, make_state


# --- fixtures ---------------------------------------------------------------


def _harm_state(num_players: int = 2) -> GameState:
    """harm_map with p0's two attackers (u0@n0, u2@n2), p1's victim u1@n1.

    p0 can dislodge p1's n1 unit via Move(u0->n1)+Support(u2->u0); p1 keeps
    home n3 so it survives. Scores after a clean p0 capture of n1 are easy to
    reason about: p0 owns n0(home)+n1(captured supply), p1 owns n3(home)."""
    m = harm_map()
    ownership = {n: None for n in m.nodes}
    for node, player in m.home_assignments.items():
        ownership[node] = player
    ownership[1] = 1  # p1 owns the contested supply at start
    units = [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)]
    for u in units:
        ownership[u.location] = u.owner
    cfg = GameConfig(num_players=num_players, max_turns=50, build_period=999,
                     detente_threshold=0, high_value_supply_fraction=0.0)
    return GameState(
        turn=0, map=m, units={u.id: u for u in units}, ownership=ownership,
        scores={p: 0.0 for p in range(num_players)}, eliminated=set(),
        next_unit_id=3, config=cfg,
    )


def _ally(*players):
    return {p: Stance.ALLY for p in players}


def _finalize(state, press_by_player, orders):
    for p in range(state.config.num_players):
        if p in state.eliminated:
            continue
        press = press_by_player.get(p, Press(stance={}, intents=[]))
        state = submit_press_tokens(state, p, press)
        state = signal_done(state, p)
    return finalize_round(state, orders)


# p0 declares Hold on u0, then stabs p1 (Move u0->n1 dislodging u1, u2 backs).
_STAB_ORDERS = {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()}}
_STAB_INTENT = Intent(unit_id=0, declared_order=Hold(), visible_to=None)


# --- GameConfig defaults -----------------------------------------------------


def test_default_penalties_are_nonzero() -> None:
    cfg = GameConfig()
    assert cfg.intent_breach_penalty > 0
    assert cfg.pact_breach_penalty > 0


# --- honored / non-harmful commitments: no penalty --------------------------


def test_honored_intent_no_penalty() -> None:
    s = _harm_state()
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    s2 = _finalize(s, {0: Press(stance=_ally(1), intents=[intent])},
                   {0: {0: Hold(), 2: Hold()}, 1: {1: Hold()}})
    assert s2.reputation == {}


def test_nonharmful_deviation_no_penalty() -> None:
    """p0 declares Hold, redirects u0 to SUPPORT p1 (helps the ally). Deviation
    but no harm -> no penalty, no reputation."""
    s = _harm_state()
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    s2 = _finalize(
        s, {0: Press(stance=_ally(1), intents=[intent])},
        {0: {0: Support(target=1), 2: Hold()}, 1: {1: Move(dest=3)}},
    )
    assert s2.reputation == {}
    # p0 keeps only its home income (no penalty deducted).
    assert s2.scores[0] == 1.0


# --- harmful intent breach: penalty hits the breacher, not the victim -------


def test_harmful_intent_breach_deducts_penalty_from_breacher() -> None:
    s = _harm_state()
    penalty = s.config.intent_breach_penalty
    s_on = _finalize(s, {0: Press(stance=_ally(1), intents=[_STAB_INTENT])},
                     _STAB_ORDERS)
    s_off = _finalize(
        replace(s, config=replace(s.config, intent_breach_penalty=0.0)),
        {0: Press(stance=_ally(1), intents=[_STAB_INTENT])}, _STAB_ORDERS,
    )
    # Isolate the fine: on-vs-off differs by exactly one intent penalty.
    assert s_off.scores[0] - s_on.scores[0] == penalty
    assert s_on.reputation[0].intent_breaches == 1
    assert s_on.scores[1] == s_off.scores[1]  # victim's score unaffected by fine


def test_harmful_breach_penalty_hits_breacher_not_observer() -> None:
    s = _harm_state()
    s2 = _finalize(s, {0: Press(stance=_ally(1), intents=[_STAB_INTENT])},
                   _STAB_ORDERS)
    assert set(s2.betrayals) == {1}      # p1 observes the (harmful) betrayal
    assert s2.betrayals[1][0].betrayer == 0
    assert s2.reputation[0].intent_breaches == 1  # breacher tracked


def test_public_harmful_breach_counted_once_not_per_observer() -> None:
    """A public harmful breach fans BetrayalObservation to every survivor but
    counts as ONE broken commitment for penalty/reputation."""
    s = _harm_state(num_players=3)  # p2 is a third observer (phantom seat)
    s2 = _finalize(
        s, {0: Press(stance=_ally(1, 2), intents=[_STAB_INTENT])},
        {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()}, 2: {}},
    )
    assert 1 in s2.betrayals  # observers see it
    assert s2.reputation[0].intent_breaches == 1  # counted once


def test_harmful_breach_recorded_even_when_it_eliminates_the_victim() -> None:
    """Penalty/reputation track true behavior: a harmful breach that WIPES OUT
    the committed ally this turn is still recorded against the breacher. The
    victim is a pre-resolution survivor (so it is a committed party) whose only
    holding is n1, so the stab eliminates it."""
    s = _harm_state()
    s.ownership[3] = None  # strip p1's fallback home -> n1 is its only holding
    s2 = _finalize(s, {0: Press(stance=_ally(1), intents=[_STAB_INTENT])},
                   _STAB_ORDERS)
    assert 1 in s2.eliminated               # victim wiped out by the stab
    assert s2.reputation[0].intent_breaches == 1  # still recorded


def test_n_harmful_breaches_in_one_turn_sum_penalties() -> None:
    """Two of p0's units each break a harmful intent -> two penalties.
    Both u0 and u2 declare Hold, then together dislodge p1 (both diverge)."""
    s = _harm_state()
    penalty = s.config.intent_breach_penalty
    intents = [
        Intent(unit_id=0, declared_order=Hold(), visible_to=None),
        Intent(unit_id=2, declared_order=Hold(), visible_to=None),
    ]
    s_on = _finalize(s, {0: Press(stance=_ally(1), intents=intents)},
                     _STAB_ORDERS)
    s_off = _finalize(
        replace(s, config=replace(s.config, intent_breach_penalty=0.0)),
        {0: Press(stance=_ally(1), intents=intents)}, _STAB_ORDERS,
    )
    # Both u0 (moved) and u2 (supported the kill) diverged harmfully -> 2 fines.
    assert s_off.scores[0] - s_on.scores[0] == 2 * penalty
    assert s_on.reputation[0].intent_breaches == 2


# --- harmful pact breach -----------------------------------------------------


def _accepted_hold_pact(s: GameState) -> GameState:
    pact = Pact(
        pact_id=0, proposer=0, counterparty=1,
        terms=(PactTerm(player=0, unit_id=0, declared_order=Hold()),
               PactTerm(player=1, unit_id=1, declared_order=Hold())),
        status=PactStatus.ACCEPTED, proposed_turn=0,
    )
    return replace(s, pacts=[pact])


def test_harmful_pact_breach_deducts_penalty_and_records() -> None:
    penalty = GameConfig().pact_breach_penalty
    s_on = _finalize(_accepted_hold_pact(_harm_state()), {}, _STAB_ORDERS)
    s0 = _harm_state()
    s0 = replace(s0, config=replace(s0.config, pact_breach_penalty=0.0))
    s_off = _finalize(_accepted_hold_pact(s0), {}, _STAB_ORDERS)
    assert s_off.scores[0] - s_on.scores[0] == penalty
    assert set(s_on.pact_breaches) == {1}
    assert s_on.pact_breaches[1][0].breacher == 0
    assert s_on.reputation[0].pact_breaches == 1


def test_nonharmful_pact_divergence_not_penalized() -> None:
    """p0 diverges from a pact Hold term by redirecting to Support p1 -- helps
    the co-signer, harms nobody -> not a breach."""
    s = _accepted_hold_pact(_harm_state())
    s2 = _finalize(
        s, {},
        {0: {0: Support(target=1), 2: Hold()}, 1: {1: Move(dest=3)}},
    )
    assert s2.reputation == {}
    assert s2.pact_breaches == {}


def test_score_can_go_negative_from_penalty() -> None:
    s = _accepted_hold_pact(_harm_state())
    s = replace(s, config=replace(s.config, pact_breach_penalty=20.0))
    s2 = _finalize(s, {}, _STAB_ORDERS)
    assert s2.scores[0] < 0  # raw score unclamped; scoring.py clamps at payout


# --- public reputation tally -------------------------------------------------


def test_reputation_empty_before_any_breach() -> None:
    assert _harm_state().reputation == {}


def test_reputation_updates_even_when_penalty_disabled() -> None:
    s = _harm_state()
    s = replace(s, config=replace(s.config, intent_breach_penalty=0.0))
    s2 = _finalize(s, {0: Press(stance=_ally(1), intents=[_STAB_INTENT])},
                   _STAB_ORDERS)
    assert s2.reputation[0].intent_breaches == 1


def test_reputation_is_cumulative() -> None:
    """finalize_round adds to the existing tally, never overwrites it."""
    s = _harm_state()
    s = replace(s, reputation={0: ReputationTally(intent_breaches=5)})
    s2 = _finalize(s, {0: Press(stance=_ally(1), intents=[_STAB_INTENT])},
                   _STAB_ORDERS)
    assert s2.reputation[0].intent_breaches == 6


def test_reputation_visible_to_all_players_via_fog() -> None:
    s = _harm_state(num_players=3)
    s2 = _finalize(
        s, {0: Press(stance=_ally(1, 2), intents=[_STAB_INTENT])},
        {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()}, 2: {}},
    )
    view_victim = visible_state_for(s2, 1)
    view_third = visible_state_for(s2, 2)
    assert view_victim["public_reputation"][0].intent_breaches == 1
    assert view_third["public_reputation"] == view_victim["public_reputation"]


def test_wire_omits_reputation_and_round_trips_clean() -> None:
    from foedus.remote.wire import deserialize_state, serialize_state

    s = _finalize(_harm_state(),
                  {0: Press(stance=_ally(1), intents=[_STAB_INTENT])},
                  _STAB_ORDERS)
    assert s.reputation  # sanity: non-empty before round-tripping
    blob = serialize_state(s)
    assert "reputation" not in blob
    restored = deserialize_state(blob)
    assert restored.reputation == {}
