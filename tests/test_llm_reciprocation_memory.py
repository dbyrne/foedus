"""Tests for foedus.agents.llm.memory.ReciprocationMemory — the agent-side,
fog-legal reciprocation record an LLMDiplomat accumulates across the turns
it has observed (declared stance it received vs. Support it has given).

The memory is fog-safe by construction: it ingests only a seat's own fogged
view (public_stance_matrix, your_outbound_press) and its own submitted orders.
These tests pin the counting semantics against scripted histories so a future
change can't silently drift them, and assert the directedness (nothing about
stances between OTHER players ever enters a seat's record).
"""

from __future__ import annotations

from foedus.core import Hold, Move, Press, Stance, Support

from foedus.agents.llm.memory import ReciprocationMemory


def _view(matrix: dict, outbound: list[Press]) -> dict:
    """A minimal fogged view carrying just what the memory reads."""
    return {"public_stance_matrix": matrix, "your_outbound_press": outbound}


def _press(stance: dict[int, Stance]) -> Press:
    return Press(stance=stance, intents=[])


# --- declared-stance-toward-me counting --------------------------------------


def test_freerider_ally_declaration_counts_over_turns() -> None:
    """An opponent who declares ALLY toward me every turn: the record shows
    ally-toward-me == turns-observed, with no support I ever gave them."""
    mem = ReciprocationMemory()
    for turn in (1, 2, 3):
        # outbound non-empty => there is real prior press to observe.
        outbound = [_press({}) for _ in range(turn)]
        mem.observe_view(_view({1: {0: "ally"}}, outbound), me=0, turn=turn)
    rec = mem.record(1)
    assert rec.turns_observed == 3
    assert rec.ally_toward_me == 3
    assert rec.hostile_toward_me == 0
    assert rec.turns_i_supported_them == 0


def test_neutral_and_hostile_declarations_bucketed() -> None:
    mem = ReciprocationMemory()
    seq = {1: "hostile", 2: "neutral", 3: "ally"}
    for turn, st in seq.items():
        outbound = [_press({}) for _ in range(turn)]
        mem.observe_view(_view({1: {0: st}}, outbound), me=0, turn=turn)
    rec = mem.record(1)
    assert rec.turns_observed == 3
    assert rec.ally_toward_me == 1
    assert rec.neutral_toward_me == 1
    assert rec.hostile_toward_me == 1


def test_observe_view_skips_when_no_prior_press() -> None:
    """Turn 0's matrix is all-default (press_history empty) — an empty
    your_outbound_press signals 'no real declaration yet', so nothing is
    counted (the denominator stays clean)."""
    mem = ReciprocationMemory()
    mem.observe_view(_view({1: {0: "ally"}}, []), me=0, turn=0)
    assert mem.opponents() == [] or mem.record(1).turns_observed == 0


def test_observe_view_idempotent_per_turn() -> None:
    mem = ReciprocationMemory()
    v = _view({1: {0: "ally"}}, [_press({})])
    mem.observe_view(v, me=0, turn=1)
    mem.observe_view(v, me=0, turn=1)
    assert mem.record(1).turns_observed == 1
    assert mem.record(1).ally_toward_me == 1


# --- fog-legality: only stances directed AT me, never between others ----------


def test_records_only_stances_directed_at_me() -> None:
    """p1 declares ALLY toward p2 but HOSTILE toward me. My record for p1 must
    reflect only the stance toward me — the p1->p2 relationship never leaks."""
    mem = ReciprocationMemory()
    matrix = {1: {0: "hostile", 2: "ally"}, 2: {0: "neutral", 1: "ally"}}
    mem.observe_view(_view(matrix, [_press({})]), me=0, turn=1)
    assert mem.record(1).hostile_toward_me == 1
    assert mem.record(1).ally_toward_me == 0
    assert mem.record(2).neutral_toward_me == 1


# --- my-own-support-to-them counting -----------------------------------------


def test_my_support_of_their_unit_counts() -> None:
    mem = ReciprocationMemory()
    # unit 5 is owned by opponent p1; I (p0) support it on turns 1 and 3.
    unit_owner = {5: 1, 9: 0}
    mem.observe_orders({9: Support(target=5)}, unit_owner, me=0, turn=1)
    mem.observe_orders({9: Hold()}, unit_owner, me=0, turn=2)
    mem.observe_orders({9: Support(target=5)}, unit_owner, me=0, turn=3)
    assert mem.record(1).turns_i_supported_them == 2


def test_support_counts_turns_not_orders() -> None:
    """Two supports of the same opponent's units in one turn is one turn."""
    mem = ReciprocationMemory()
    unit_owner = {5: 1, 6: 1, 9: 0, 10: 0}
    mem.observe_orders(
        {9: Support(target=5), 10: Support(target=6)}, unit_owner, me=0, turn=1
    )
    assert mem.record(1).turns_i_supported_them == 1


def test_support_of_my_own_unit_not_counted() -> None:
    mem = ReciprocationMemory()
    unit_owner = {9: 0, 10: 0}  # both mine
    mem.observe_orders({9: Support(target=10)}, unit_owner, me=0, turn=1)
    # Supporting my own unit records no opponent at all (and never me).
    assert mem.opponents() == []


def test_observe_orders_idempotent_per_turn() -> None:
    mem = ReciprocationMemory()
    unit_owner = {5: 1, 9: 0}
    orders = {9: Support(target=5)}
    mem.observe_orders(orders, unit_owner, me=0, turn=1)
    mem.observe_orders(orders, unit_owner, me=0, turn=1)
    assert mem.record(1).turns_i_supported_them == 1


# --- my own prior declared stances (counters the "forgets its turn-1 read") --


def test_my_prior_stances_recorded_from_outbound() -> None:
    mem = ReciprocationMemory()
    outbound = [_press({1: Stance.HOSTILE}), _press({1: Stance.NEUTRAL})]
    mem.observe_view(_view({1: {0: "ally"}}, outbound), me=0, turn=2)
    assert mem.record(1).my_prior_stances == ["hostile", "neutral"]


def test_my_prior_stances_default_neutral_for_undeclared_turns() -> None:
    """A turn where I declared nothing toward them reads as neutral (the game
    default), so the sequence has one entry per prior turn."""
    mem = ReciprocationMemory()
    outbound = [_press({}), _press({1: Stance.ALLY})]
    mem.observe_view(_view({1: {0: "ally"}}, outbound), me=0, turn=2)
    assert mem.record(1).my_prior_stances == ["neutral", "ally"]


def test_asymmetry_freerider_vs_honest_ally() -> None:
    """End-to-end asymmetry over a scripted 3-turn history: a freerider (p1)
    declares ALLY every turn and I keep backing it; an honest ally (p2) I also
    back. The record separates their declarations from my own sunk support."""
    mem = ReciprocationMemory()
    unit_owner = {11: 1, 22: 2, 90: 0, 91: 0}
    for turn in (1, 2, 3):
        outbound = [_press({1: Stance.ALLY, 2: Stance.ALLY}) for _ in range(turn)]
        matrix = {1: {0: "ally"}, 2: {0: "ally"}}
        mem.observe_view(_view(matrix, outbound), me=0, turn=turn)
        # I support p1 every turn; p2 only on turn 2.
        orders = {90: Support(target=11)}
        if turn == 2:
            orders[91] = Support(target=22)
        mem.observe_orders(orders, unit_owner, me=0, turn=turn)
    assert mem.record(1).ally_toward_me == 3
    assert mem.record(1).turns_i_supported_them == 3
    assert mem.record(2).ally_toward_me == 3
    assert mem.record(2).turns_i_supported_them == 1
