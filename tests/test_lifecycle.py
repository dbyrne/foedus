"""Build phase, scoring, and elimination logic over multi-turn games."""

from __future__ import annotations

from foedus.core import (
    GameConfig,
    Hold,
    Move,
    NodeType,
    Unit,
)
from foedus.resolve import resolve_turn

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
    """Capturing a supply center increases score after holding through a full turn."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, build_period=999)
    # Move into adjacent supply node 1.
    s = resolve_turn(s, {0: {0: Move(dest=1)}})
    # Bundle 2 cadence: walk-in does not flip ownership — only home (node 0)
    # is still owned; score = 1.
    assert s.scores[0] == 1.0
    s = resolve_turn(s, {0: {0: Hold()}})
    # After holding node 1 for a full turn (start AND end), ownership flips.
    # p0 now owns nodes 0 and 1 → score per turn = 2, accumulated = 1+2 = 3.
    assert s.scores[0] == 3.0  # 1 (turn 1) + 2 (turn 2)


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
    # Player 0 will own home (0) + supply (1) by turn 2 (hold-through flip).
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, build_period=2)
    # turn 1: move 0->1 (capture supply). No build yet (build_period=2, turn 1).
    s = resolve_turn(s, {0: {0: Move(dest=1)}})
    assert len(s.units) == 1, "no build at turn 1"
    # turn 2: hold. Build phase fires.
    # Bundle 2 cadence: node 1 owned at end of turn 2 (held start+end).
    # p0 controls 2 supplies (home 0 + node 1); p1 controls home 4.
    # make_state seeds home ownership for p1, so p1 also builds at n4.
    s = resolve_turn(s, {0: {0: Hold()}})
    # p0: 2 supplies, 1 unit → builds 1 (at node 0). p1: 1 supply, 0 units → builds 1 (at node 4).
    p0_units = [u for u in s.units.values() if u.owner == 0]
    assert len(p0_units) == 2  # p0 built 1 new unit
    assert any(u.location == 0 for u in p0_units)  # built at unoccupied home


def test_no_build_when_supply_equals_units() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, build_period=2)
    # Don't capture extra supply. Just hold.
    s = resolve_turn(s, {0: {0: Hold()}})  # turn 1
    s = resolve_turn(s, {0: {0: Hold()}})  # turn 2 (build)
    # p0 has 1 supply, 1 unit — no build needed for p0.
    # Bundle 2: make_state seeds home ownership for p1 (node 4); p1 has 0 units
    # → p1 builds 1 unit at n4 at turn 2 (build_period=2).
    p0_units = [u for u in s.units.values() if u.owner == 0]
    assert len(p0_units) == 1  # no build for p0


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
    # Bundle 2: make_state seeds home ownership for p1 (node 4); p1 has 0 units → builds 1.
    p0_units = [u for u in s.units.values() if u.owner == 0]
    p0_locations = sorted(u.location for u in p0_units)
    assert len(p0_units) == 3  # p0 built 2 new units
    assert p0_locations == [0, 1, 2]  # at unoccupied owned nodes 0 and 1


def test_terminal_at_max_turns() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   build_period=999, max_turns=3)
    for _ in range(3):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.is_terminal()
