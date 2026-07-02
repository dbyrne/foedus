"""Tests for F6 (Phase 0b): betrayal teeth.

Playtest finding: betrayal was "untested theater" because breaking a
declared Intent or an accepted Pact cost nothing mechanically. F6 attaches
two costs to the two existing breach signals (BetrayalObservation from
press.py::_verify_intents, PactBreach from press.py::_verify_pacts):

  1. A configurable score penalty deducted from the BREACHER at finalize
     (GameConfig.intent_breach_penalty / pact_breach_penalty).
  2. A PUBLIC cumulative reputation tally (GameState.reputation), visible to
     every player via fog -- not just the observer/victim like
     betrayals/pact_breaches -- so the social cost compounds.

Mirrors the rigor of tests/test_score_delta.py and tests/test_pacts.py:
hand-derived scenarios, exact score/delta assertions, no re-derivation of
engine math.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    GameConfig,
    Hold,
    Intent,
    Move,
    PactTerm,
    Press,
    ReputationTally,
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


def _home_income_state(num_players: int = 2) -> "GameState":
    """line_map(3): 0(H,p0)-1$-2(H,p1). Each player Holds at home ->
    baseline +1.0/turn each (matches test_score_delta's home-income case)."""
    m = line_map(3)
    return make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=num_players)


def _three_player_public_state() -> "GameState":
    """line_map(5): 0(H,p0)-1$-2$-3$-4(H,p1), plus a p2 unit at n2.
    Three survivors, so a public (visible_to=None) broken intent fans out
    BetrayalObservation to two observers -- the scenario that would
    over-count a naive "one penalty per observation" implementation."""
    m = line_map(5)
    return make_state(
        m,
        [Unit(0, 0, 0), Unit(1, 1, 4), Unit(2, 2, 2)],
        num_players=3,
    )


def _pact_hold_state():
    """line_map(3): 0(H,p0)-1$-2(H,p1). A trivial mutual-Hold pact so a
    breach (p0 moving instead) doesn't entangle combat resolution -- keeps
    the penalty assertion isolated from resolve.py's combat math."""
    return _home_income_state()


def _pact_hold_terms():
    return (
        PactTerm(player=0, unit_id=0, declared_order=Hold()),
        PactTerm(player=1, unit_id=1, declared_order=Hold()),
    )


def _finalize_with_press(state, press_by_player, orders):
    """Submit `press_by_player[p]` (or empty Press) for every survivor,
    signal done, then finalize. Mirrors test_pacts.py::_run_finalize but
    allows per-player press payloads (needed to declare intents)."""
    for p in range(state.config.num_players):
        if p in state.eliminated:
            continue
        press = press_by_player.get(p, Press(stance={}, intents=[]))
        state = submit_press_tokens(state, p, press)
        state = signal_done(state, p)
    return finalize_round(state, orders)


# --- GameConfig defaults -----------------------------------------------------


def test_default_penalties_are_nonzero_and_pact_exceeds_intent() -> None:
    cfg = GameConfig()
    assert cfg.intent_breach_penalty > 0
    assert cfg.pact_breach_penalty > cfg.intent_breach_penalty


# --- honored commitments: no penalty ----------------------------------------


def test_honored_intent_no_penalty() -> None:
    s = _home_income_state()
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    assert s2.scores == {0: 1.0, 1: 1.0}
    assert s2.last_turn_score_delta == {0: 1.0, 1: 1.0}
    assert s2.reputation == {}


def test_honored_pact_no_penalty() -> None:
    s = _pact_hold_state()
    s = propose_pact(s, 0, 1, _pact_hold_terms())
    s = accept_pact(s, 0, 1)
    s2 = _finalize_with_press(s, {}, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s2.scores == {0: 1.0, 1: 1.0}
    assert s2.reputation == {}


# --- intent breach: penalty hits the breacher, not the victim --------------


def test_intent_breach_deducts_penalty_from_breacher() -> None:
    s = _home_income_state()
    # p0 declares it will Move but actually Holds.
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    penalty = s.config.intent_breach_penalty
    assert s2.scores == {0: 1.0 - penalty, 1: 1.0}
    assert s2.last_turn_score_delta == {0: 1.0 - penalty, 1: 1.0}


def test_intent_breach_penalty_hits_breacher_not_observer() -> None:
    """p0 breaches an intent visible to p1 -- p1 is the victim/observer,
    p0 is the breacher. The penalty must land on p0."""
    s = _home_income_state()
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    assert set(s2.betrayals) == {1}  # p1 is the observer
    assert s2.betrayals[1][0].betrayer == 0
    assert s2.scores[1] == 1.0  # victim untouched
    assert s2.scores[0] < 1.0  # breacher penalized


def test_intent_breach_penalty_disabled_at_zero() -> None:
    s = _home_income_state()
    s = replace(s, config=replace(s.config, intent_breach_penalty=0.0))
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    assert s2.scores == {0: 1.0, 1: 1.0}  # unchanged vs pre-F6 behavior


def test_n_intent_breaches_in_one_turn_sum_penalties() -> None:
    """p0 owns two units, each with a broken intent -- exactly 2 penalties."""
    m = line_map(5)
    s = make_state(
        m,
        [Unit(0, 0, 0), Unit(1, 1, 4), Unit(2, 0, 1)],  # u2: p0's 2nd unit
        num_players=2,
    )
    intents = [
        Intent(unit_id=0, declared_order=Move(dest=1), visible_to=frozenset({1})),
        Intent(unit_id=2, declared_order=Move(dest=0), visible_to=frozenset({1})),
    ]
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=intents)},
        {0: {0: Hold(), 2: Hold()}, 1: {1: Hold()}},
    )
    base = 2.0  # p0 owns n0 (home) + n1 (pre-owned supply) = 2 income
    penalty = 2 * s.config.intent_breach_penalty
    assert s2.scores[0] == base - penalty


def test_public_intent_breach_counted_once_not_per_observer() -> None:
    """A public intent (visible_to=None) fans BetrayalObservation out to
    every surviving non-sender. That must still be exactly ONE broken
    commitment for penalty purposes, not one penalty per observer."""
    s = _three_player_public_state()
    intent = Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}, 2: {2: Hold()}},
    )
    # Two observers (p1, p2) both see the betrayal...
    assert set(s2.betrayals) == {1, 2}
    # ...but only one penalty was charged against the breacher p0.
    penalty = s.config.intent_breach_penalty
    assert s2.scores[0] == 1.0 - penalty  # p0 home income (1.0) minus ONE penalty
    assert s2.reputation[0].intent_breaches == 1  # not 2


# --- pact breach: larger penalty, hits the breacher -------------------------


def test_pact_breach_deducts_larger_penalty_from_breacher() -> None:
    s = _pact_hold_state()
    s = propose_pact(s, 0, 1, _pact_hold_terms())
    s = accept_pact(s, 0, 1)
    # p0 breaches: moves instead of holding. Walk-in capture needs a
    # subsequent Hold, so this turn p0's score is still just home income.
    s2 = _finalize_with_press(s, {}, {0: {0: Move(dest=1)}, 1: {1: Hold()}})
    penalty = s.config.pact_breach_penalty
    assert s2.scores == {0: 1.0 - penalty, 1: 1.0}
    assert set(s2.pact_breaches) == {1}
    assert s2.pact_breaches[1][0].breacher == 0


def test_pact_breach_penalty_disabled_at_zero() -> None:
    s = _pact_hold_state()
    s = replace(s, config=replace(s.config, pact_breach_penalty=0.0))
    s = propose_pact(s, 0, 1, _pact_hold_terms())
    s = accept_pact(s, 0, 1)
    s2 = _finalize_with_press(s, {}, {0: {0: Move(dest=1)}, 1: {1: Hold()}})
    assert s2.scores == {0: 1.0, 1: 1.0}


def test_score_can_go_negative_from_penalty() -> None:
    """Clamping decision: raw scores.py are allowed to go negative from a
    breach penalty (like stagnation_cost); scoring.py's payout functions
    already clamp with max(0, ...) at consumption time, so the raw score
    stays the true record of what happened this game."""
    s = _pact_hold_state()
    s = replace(s, config=replace(s.config, pact_breach_penalty=5.0))
    s = propose_pact(s, 0, 1, _pact_hold_terms())
    s = accept_pact(s, 0, 1)
    s2 = _finalize_with_press(s, {}, {0: {0: Move(dest=1)}, 1: {1: Hold()}})
    assert s2.scores[0] == 1.0 - 5.0
    assert s2.scores[0] < 0


# --- public reputation tally -------------------------------------------------


def test_reputation_empty_before_any_breach() -> None:
    s = _home_income_state()
    assert s.reputation == {}


def test_reputation_increments_for_intent_breach() -> None:
    s = _home_income_state()
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    assert s2.reputation[0] == ReputationTally(intent_breaches=1, pact_breaches=0)
    assert s2.reputation[0].total == 1
    assert 1 not in s2.reputation  # p1 never breached


def test_reputation_increments_for_pact_breach() -> None:
    s = _pact_hold_state()
    s = propose_pact(s, 0, 1, _pact_hold_terms())
    s = accept_pact(s, 0, 1)
    s2 = _finalize_with_press(s, {}, {0: {0: Move(dest=1)}, 1: {1: Hold()}})
    assert s2.reputation[0] == ReputationTally(intent_breaches=0, pact_breaches=1)
    assert s2.reputation[0].total == 1


def test_reputation_updates_even_when_penalty_disabled() -> None:
    """Reputation tracks true behavior, independent of whether the
    mechanical penalty is configured on."""
    s = _home_income_state()
    s = replace(s, config=replace(s.config, intent_breach_penalty=0.0))
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    assert s2.reputation[0].intent_breaches == 1


def test_reputation_is_cumulative_across_turns() -> None:
    s = _home_income_state()
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    assert s.reputation[0].intent_breaches == 1
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    assert s2.reputation[0].intent_breaches == 2


def test_reputation_visible_to_all_players_via_fog() -> None:
    """Unlike betrayals/pact_breaches (observer-only), reputation is fully
    public -- every fog view sees the same tally, like scores."""
    s = _three_player_public_state()
    intent = Intent(unit_id=0, declared_order=Move(dest=1), visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}, 2: {2: Hold()}},
    )
    view_victim = visible_state_for(s2, 1)
    view_third_party = visible_state_for(s2, 2)
    assert view_victim["public_reputation"] == {0: ReputationTally(intent_breaches=1)}
    assert view_third_party["public_reputation"] == view_victim["public_reputation"]
    # Contrast: the betrayal ledger itself IS observer-gated.
    assert visible_state_for(s2, 2)["your_betrayals"] == []


# --- wire protocol: reputation is press-layer (omitted), like pacts --------


def test_wire_omits_reputation_and_round_trips_clean() -> None:
    from foedus.remote.wire import deserialize_state, serialize_state

    s = _home_income_state()
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    assert s.reputation  # sanity: non-empty before round-tripping
    blob = serialize_state(s)
    assert "reputation" not in blob
    restored = deserialize_state(blob)
    assert restored.reputation == {}
