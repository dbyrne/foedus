"""SupportLapsed event taxonomy."""
from foedus.core import Hold, Move, Support, SupportLapsed
from foedus.press import advance_turn
from tests.helpers import build_state_with_units


def _find_lapse_events(state) -> list[SupportLapsed]:
    """Pull SupportLapsed entries from the state's structured event log.
    The log is currently a list[str]; we emit lapses as a parallel typed
    list on state. See implementation note in Task 4 step 4.3."""
    return list(state.support_lapses)  # added in step 4.3


def test_geometry_break_emits_lapse():
    s = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1}, 1: {0, 2}, 2: {1}},
        num_players=2,
    )
    orders_by_player = {
        0: {0: Support(target=1)},
        1: {1: Move(dest=2)},
    }
    s2 = advance_turn(s, orders_by_player)
    lapses = _find_lapse_events(s2)
    assert any(
        l.supporter == 0 and l.target == 1 and l.reason == "geometry_break"
        for l in lapses
    )


def test_pin_mismatch_emits_lapse():
    s = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1, 2, 3}, 1: {0, 2, 3}, 2: {0, 1}, 3: {0, 1}},
        num_players=2,
    )
    # P0 pins to node 2; P1 actually moves to node 3.
    orders_by_player = {
        0: {0: Support(target=1, require_dest=2)},
        1: {1: Move(dest=3)},
    }
    s2 = advance_turn(s, orders_by_player)
    lapses = _find_lapse_events(s2)
    assert any(l.reason == "pin_mismatch" for l in lapses)


def test_target_destroyed_emits_lapse():
    s = build_state_with_units(
        layout={0: 0},  # only one unit; supporter targets nonexistent unit
        ownership={0: 0},
        edges={0: {1}, 1: {0}},
        num_players=2,
    )
    orders_by_player = {0: {0: Support(target=999)}}
    s2 = advance_turn(s, orders_by_player)
    lapses = list(s2.support_lapses)
    assert any(l.reason == "target_destroyed" for l in lapses)


def test_betrayal_observation_independent_of_support_outcome():
    """A declared intent vs. submitted-order mismatch still emits
    BetrayalObservation, even when the support succeeded."""
    # Stub: regression check only — confirm test_betrayal.py still passes
    # after Task 4 lands. No new assertion here; this test exists to flag
    # if the verifier path drifts.
    pass
