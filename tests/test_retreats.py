"""Retreats — a dislodged unit retreats to its home node (tempo cost) instead
of being eliminated, when GameConfig.retreats_enabled is True.

Spec (2026-07-02 lethality-softening pass):
  - Primary: a dislodged unit is placed on its HOME node (teleport home; the
    tempo cost is losing its forward position).
  - Fallback A — home captured by an enemy (new_owner[home] != owner): eliminate.
  - Fallback C — home owned but occupied (by any unit): retreat to the nearest
    empty owned passable node (BFS from home, tie-break lowest node id); if none,
    eliminate.
  - retreats_enabled defaults OFF, so v1 behavior (dislodged -> eliminated) is
    unchanged.

Retreats must compose with combat rewards, the build phase, ownership updates,
and eliminations — those interactions are tested here too.
"""

from __future__ import annotations

from foedus.core import (
    GameConfig,
    Hold,
    Map,
    Move,
    NodeType,
    Support,
    Unit,
)
from foedus.resolve import resolve_turn

from tests.helpers import make_state


def retreat_map() -> Map:
    """Purpose-built topology for retreat scenarios.

        n6(PLAIN)   n7(PLAIN)      <- p0 reserve nodes, hang off home n0
             \\      /
             n0(HOME p0) - n1(SUPPLY) - n2(SUPPLY) - n3(HOME p1)
                            /     \\
                        n4(PLAIN) n5(PLAIN)          <- attacker staging

    n1's neighbors are n0, n2, n4, n5 — so p0's home (n0) and reserves (n6, n7)
    are NOT adjacent to the frontier n1, letting a test dislodge a unit on n1
    (via attackers staged on n4/n5) while keeping n6/n7 free as retreat targets.
    """
    coords = {
        0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (3, 0),
        4: (1, 1), 5: (1, -1), 6: (-1, 1), 7: (-1, -1),
    }
    edges = {
        0: frozenset({1, 6, 7}),
        1: frozenset({0, 2, 4, 5}),
        2: frozenset({1, 3}),
        3: frozenset({2}),
        4: frozenset({1}),
        5: frozenset({1}),
        6: frozenset({0}),
        7: frozenset({0}),
    }
    node_types = {
        0: NodeType.HOME,
        1: NodeType.SUPPLY,
        2: NodeType.SUPPLY,
        3: NodeType.HOME,
        4: NodeType.PLAIN,
        5: NodeType.PLAIN,
        6: NodeType.PLAIN,
        7: NodeType.PLAIN,
    }
    home_assignments = {0: 0, 3: 1}
    return Map(coords=coords, edges=edges, node_types=node_types,
               home_assignments=home_assignments)


# --- Config surface -------------------------------------------------------


def test_retreats_disabled_by_default() -> None:
    assert GameConfig().retreats_enabled is False


# --- Core: retreat to home ------------------------------------------------


def test_dislodged_unit_retreats_to_home() -> None:
    """A unit dislodged off the frontier survives on its (empty, owned) home."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(1, 0, 1),                 # p0 victim on frontier n1
         Unit(10, 1, 4), Unit(11, 1, 5)],  # p1 attackers on n4, n5
        retreats_enabled=True,
    )
    out = resolve_turn(s, {
        0: {1: Hold()},  # holds and is dislodged in place (does not vacate)
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    })
    assert 1 in out.units, "dislodged unit should survive via retreat"
    assert out.units[1].location == 0, "should retreat to home node n0"
    assert 0 not in out.eliminated, "p0 keeps a unit, so not eliminated"


def test_retreats_off_dislodged_unit_is_eliminated() -> None:
    """Control: same setup with retreats OFF eliminates the dislodged unit."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(1, 0, 1), Unit(10, 1, 4), Unit(11, 1, 5)],
        retreats_enabled=False,
    )
    out = resolve_turn(s, {
        0: {1: Hold()},  # holds and is dislodged in place (does not vacate)
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    })
    assert 1 not in out.units, "with retreats off, dislodged unit is eliminated"


# --- Fallback A: home captured by an enemy -> eliminate -------------------


def test_dislodged_on_home_is_eliminated_home_captured() -> None:
    """A unit dislodged ON its home loses the home to the attacker (rule a),
    so there is nowhere to retreat -> eliminate."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(0, 0, 0),                 # p0 victim sitting on its home n0
         Unit(10, 1, 1), Unit(11, 1, 6)],  # p1 attackers on n1, n6 (both adj n0)
        retreats_enabled=True,
    )
    out = resolve_turn(s, {
        0: {0: Hold()},  # holds its home and is dislodged in place
        1: {10: Move(dest=0), 11: Support(target=10, require_dest=0)},
    })
    assert 0 not in out.units, "home captured by enemy -> unit eliminated"
    assert out.ownership[0] == 1, "home flipped to the attacker"


def test_home_pre_captured_elsewhere_dislodge_eliminates_even_with_spare() -> None:
    """Fallback A is terminal: even when the player owns another empty node,
    a unit whose home is enemy-owned is eliminated (not routed to the spare)."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(1, 0, 1),                 # p0 victim on frontier n1
         Unit(10, 1, 4), Unit(11, 1, 5)],  # p1 attackers
        retreats_enabled=True,
    )
    s.ownership[0] = 1   # p0's home already held by the enemy
    s.ownership[6] = 0   # p0 owns an empty spare node n6 (a valid Case-C target)
    out = resolve_turn(s, {
        0: {1: Hold()},  # holds and is dislodged in place (does not vacate)
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    })
    assert 1 not in out.units, (
        "home captured -> eliminate, terminal even though p0 owns empty n6"
    )


# --- Fallback C: home occupied -> nearest empty owned node ----------------


def test_home_occupied_by_own_unit_retreats_to_nearest_owned() -> None:
    """When home is occupied by a surviving own unit, retreat to the nearest
    empty owned passable node."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(0, 0, 0),                 # p0 holds its home n0 (occupies it)
         Unit(1, 0, 1),                 # p0 victim on frontier n1
         Unit(10, 1, 4), Unit(11, 1, 5)],  # p1 attackers
        retreats_enabled=True,
    )
    s.ownership[6] = 0   # nearest empty owned node (dist 1 from home n0)
    out = resolve_turn(s, {
        0: {0: Hold()},  # occupies its home n0; u1 (unordered) holds n1
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    })
    assert 1 in out.units
    assert out.units[1].location == 6, "retreated to nearest empty owned node"
    assert out.units[0].location == 0, "home occupant unchanged"


def test_home_occupied_nearest_owned_tiebreaks_lowest_node_id() -> None:
    """Two equidistant empty owned nodes -> pick the lowest node id."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(0, 0, 0), Unit(1, 0, 1), Unit(10, 1, 4), Unit(11, 1, 5)],
        retreats_enabled=True,
    )
    s.ownership[6] = 0   # both n6 and n7 are dist 1 from home n0, empty, owned
    s.ownership[7] = 0
    out = resolve_turn(s, {
        0: {0: Hold()},
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    })
    assert out.units[1].location == 6, "tie-break picks lowest node id (n6<n7)"


def test_home_occupied_no_owned_node_eliminates() -> None:
    """Home occupied by own unit AND no empty owned node -> eliminate."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(0, 0, 0), Unit(1, 0, 1), Unit(10, 1, 4), Unit(11, 1, 5)],
        retreats_enabled=True,
    )
    # n6/n7 left unowned (None) -> no Case-C target available.
    out = resolve_turn(s, {
        0: {0: Hold()},
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    })
    assert 1 not in out.units, "no retreat target -> dislodged unit eliminated"
    assert out.units[0].location == 0, "the home occupant survives"
    assert 0 not in out.eliminated, "p0 still has a unit + its home supply"


# --- Composition: combat reward, builds, elimination ----------------------


def test_retreat_still_awards_attacker_combat_reward() -> None:
    """A dislodgement that ends in a retreat still counts as a dislodgement:
    the attacker earns its combat reward."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(1, 0, 1), Unit(10, 1, 4), Unit(11, 1, 5)],
        retreats_enabled=True,
    )
    out = resolve_turn(s, {
        0: {1: Hold()},  # holds and is dislodged in place (does not vacate)
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    })
    assert out.units[1].location == 0            # retreated
    assert any("combat reward" in line for line in out.log), (
        "attacker still rewarded for the dislodgement"
    )


def test_retreated_unit_counts_for_build_phase() -> None:
    """A retreated unit is a live unit: it must be counted in the build phase
    (so the player does not get an extra build for the 'lost' unit)."""
    m = retreat_map()
    s = make_state(
        m,
        [Unit(1, 0, 1), Unit(10, 1, 4), Unit(11, 1, 5)],
        build_period=1,   # build fires every turn
        retreats_enabled=True,
    )
    out = resolve_turn(s, {
        0: {1: Hold()},  # holds and is dislodged in place (does not vacate)
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    })
    p0_units = [u for u in out.units.values() if u.owner == 0]
    # p0 owns exactly 1 supply (its home n0) and now has its 1 retreated unit
    # there -> need = 1 - 1 = 0 builds. If the retreat weren't counted, p0
    # would build a second unit.
    assert len(p0_units) == 1, "retreat counted -> no spurious build"
    assert p0_units[0].location == 0


def test_retreat_saves_player_from_elimination() -> None:
    """A player whose sole unit is dislodged survives when that unit retreats,
    where with retreats off it would lose the unit."""
    m = retreat_map()
    # Give the attacker ownership of p0's home-adjacent nodes is irrelevant;
    # p0's only unit is on the frontier and its home is empty+owned.
    units = [Unit(1, 0, 1), Unit(10, 1, 4), Unit(11, 1, 5)]
    orders = {
        0: {1: Hold()},  # holds and is dislodged in place (does not vacate)
        1: {10: Move(dest=1), 11: Support(target=10, require_dest=1)},
    }
    on = resolve_turn(
        make_state(m, list(units), retreats_enabled=True), orders)
    off = resolve_turn(
        make_state(m, list(units), retreats_enabled=False), orders)
    assert 1 in on.units and on.units[1].location == 0
    assert 1 not in off.units


# --- Determinism: two units retreating at once ----------------------------


def _double_frontier_map() -> Map:
    """Two p0 frontier supplies (n1, n2) sharing home n0, each flanked by two
    p1 attacker nodes; n7 is a spare p0-owned node off the home."""
    coords = {i: (i, 0) for i in range(9)}
    edges = {
        0: frozenset({1, 2, 7}),
        1: frozenset({0, 3, 4}),
        2: frozenset({0, 5, 6}),
        3: frozenset({1}),
        4: frozenset({1}),
        5: frozenset({2}),
        6: frozenset({2, 8}),
        7: frozenset({0}),
        8: frozenset({6}),
    }
    node_types = {
        0: NodeType.HOME, 1: NodeType.SUPPLY, 2: NodeType.SUPPLY,
        3: NodeType.PLAIN, 4: NodeType.PLAIN, 5: NodeType.PLAIN,
        6: NodeType.PLAIN, 7: NodeType.PLAIN, 8: NodeType.HOME,
    }
    return Map(coords=coords, edges=edges, node_types=node_types,
               home_assignments={0: 0, 8: 1})


def test_two_units_dislodged_retreat_deterministically() -> None:
    """Two of a player's units dislodged the same turn both want home n0.
    The lower-id unit takes the home; the other sees it occupied and falls
    back to the nearest empty owned node — proving each placement is visible
    to the next (no double-booking)."""
    m = _double_frontier_map()
    s = make_state(
        m,
        [Unit(1, 0, 1), Unit(2, 0, 2),          # p0 victims on n1, n2
         Unit(10, 1, 3), Unit(11, 1, 4),         # attackers on n1
         Unit(12, 1, 5), Unit(13, 1, 6)],        # attackers on n2
        retreats_enabled=True,
    )
    s.ownership[7] = 0   # p0's spare owned node (Case-C target for the runner-up)
    out = resolve_turn(s, {
        0: {1: Hold(), 2: Hold()},
        1: {
            10: Move(dest=1), 11: Support(target=10, require_dest=1),
            12: Move(dest=2), 13: Support(target=12, require_dest=2),
        },
    })
    assert out.units[1].location == 0, "lowest-id unit takes the home"
    assert out.units[2].location == 7, "runner-up falls back to nearest owned"


# --- Wire round-trip ------------------------------------------------------


def test_retreats_enabled_survives_wire_roundtrip() -> None:
    from foedus.remote.wire import deserialize_config, serialize_config

    cfg = GameConfig(num_players=4, retreats_enabled=True)
    back = deserialize_config(serialize_config(cfg))
    assert back.retreats_enabled is True

    cfg_off = GameConfig(num_players=4, retreats_enabled=False)
    back_off = deserialize_config(serialize_config(cfg_off))
    assert back_off.retreats_enabled is False


def test_leader_upkeep_survives_wire_roundtrip() -> None:
    """The leader-counterweight knobs must round-trip too — the web session
    store serializes+deserializes config on every save/load."""
    from foedus.remote.wire import deserialize_config, serialize_config

    cfg = GameConfig(num_players=4, supply_upkeep=0.5, supply_upkeep_free=2)
    back = deserialize_config(serialize_config(cfg))
    assert back.supply_upkeep == 0.5
    assert back.supply_upkeep_free == 2
