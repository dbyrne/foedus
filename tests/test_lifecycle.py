"""Build phase, scoring, and elimination logic over multi-turn games."""

from __future__ import annotations

from agent_game.core import (
    GameConfig,
    Hold,
    Move,
    NodeType,
    Unit,
)
from agent_game.resolve import resolve_turn

from tests.helpers import line_map, make_state


def test_score_increments_per_turn() -> None:
    """Each turn, every active player gains score == their controlled supply count."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
    ], build_period=999)
    # Both have 1 supply each (their home).
    s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.scores[0] == 1.0
    assert s.scores[1] == 1.0
    s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.scores[0] == 2.0
    assert s.scores[1] == 2.0


def test_score_grows_when_supply_captured() -> None:
    """Capturing a supply center increases score next turn."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, build_period=999)
    # Move into adjacent supply node 1.
    s = resolve_turn(s, {0: {0: Move(dest=1)}})
    assert s.scores[0] == 2.0  # home (still owned) + new supply
    s = resolve_turn(s, {0: {0: Hold()}})
    assert s.scores[0] == 4.0  # 2 supply x 2 turns total


def test_eliminated_player_does_not_score() -> None:
    m = line_map(3)
    # Player 1 has no units and no supply at start — should be eliminated turn 1.
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, build_period=999)
    s.ownership[2] = None  # explicitly clear player 1's home ownership
    s = resolve_turn(s, {0: {0: Hold()}})
    assert 1 in s.eliminated
    assert s.scores[1] == 0.0
    s = resolve_turn(s, {0: {0: Hold()}})
    assert s.scores[1] == 0.0  # still 0


def test_build_phase_at_period() -> None:
    """Build occurs every config.build_period turns."""
    m = line_map(5)
    # Player 0 will own home (0) + supply (1) by turn 1.
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, build_period=2)
    # turn 1: move 0->1 (capture supply). No build yet (build_period=2, turn 1).
    s = resolve_turn(s, {0: {0: Move(dest=1)}})
    assert len(s.units) == 1, "no build at turn 1"
    # turn 2: hold. Build phase fires.
    # Player 0 now controls 2 supplies (home 0 + node 1) but home 0 is unoccupied.
    s = resolve_turn(s, {0: {0: Hold()}})
    # supply_count(0) = 2 (nodes 0 and 1), unit count was 1 → need 1 more.
    # Build at owned unoccupied node: node 0 is owned, unoccupied.
    assert len(s.units) == 2


def test_no_build_when_supply_equals_units() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, build_period=2)
    # Don't capture extra supply. Just hold.
    s = resolve_turn(s, {0: {0: Hold()}})  # turn 1
    s = resolve_turn(s, {0: {0: Hold()}})  # turn 2 (build)
    # Player 0 has 1 supply, 1 unit. No build needed.
    assert len(s.units) == 1


def test_eliminated_when_no_units_and_no_supply() -> None:
    """Player with 0 units and 0 supply centers is eliminated."""
    m = line_map(3)
    # Place player 1's unit at the wrong spot — player 1's home (node 2) is unowned.
    # If u1 dies and player 1 has no supply, eliminated.
    s = make_state(m, [
        Unit(0, 0, 1),  # p0 supporter
        Unit(1, 0, 0),  # p0 attacker
        Unit(2, 1, 1),  # wait — two units at node 1 — invalid.
    ], num_players=2)
    # Need a different setup. Let's use:
    s = make_state(m, [
        Unit(0, 0, 0),  # p0 home
        Unit(1, 1, 2),  # p1 home
    ], num_players=2)
    # Player 1's home (2) is owned by p1 because u1 is there. So p1 has supply.
    # To test elimination, we need p1 to lose home AND units. That's a multi-turn setup.
    # Simplest: p1 has no units and no supply at start of turn.
    s.ownership[2] = None
    # Remove unit 1 manually
    del s.units[1]
    # Now p1: 0 units, 0 supply.
    s = resolve_turn(s, {0: {0: Hold()}})
    assert 1 in s.eliminated


def test_not_eliminated_with_supply_alone() -> None:
    """A player with supply centers but no units is NOT eliminated immediately."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2)
    # Player 1 owns node 2 (supply, their home) but has no units.
    s.ownership[2] = 1
    s = resolve_turn(s, {0: {0: Hold()}})
    assert 1 not in s.eliminated  # still in (has supply)


def test_build_at_owned_unoccupied_node() -> None:
    """Builds occur only at nodes owned by the building player and currently unoccupied."""
    m = line_map(5)
    # Player 0 controls nodes 0, 1, 2 (home + 2 supply); has 1 unit at 2.
    # Should build 2 more units at unoccupied owned nodes (0, 1).
    s = make_state(m, [Unit(0, 0, 2)], num_players=2, build_period=1, max_turns=20)
    s.ownership[0] = 0
    s.ownership[1] = 0
    s = resolve_turn(s, {0: {0: Hold()}})
    # Build at turn 1 (build_period=1).
    # Supply for p0: home 0, supply 1, supply 2 = 3 supplies. Unit count = 1. Build 2.
    locations = sorted(u.location for u in s.units.values())
    assert len(s.units) == 3
    assert locations == [0, 1, 2]


def test_terminal_at_max_turns() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   build_period=999, max_turns=3)
    for _ in range(3):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.is_terminal()
