"""Bundle 5b (C3) — variable supply values tests.

A small fraction of non-HOME SUPPLY nodes yield +2 score per turn instead of
+1, distributed deterministically from `config.seed`. HOME nodes always
yield +1 (heterogeneity is for contested frontier supplies, not homes).
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import GameConfig, Hold, Map, NodeType, Unit
from foedus.mapgen import generate_map
from foedus.press import advance_turn
from foedus.resolve import _assign_high_value_supplies, initial_state

from tests.helpers import line_map, make_state


def _supply_count(m: Map, type_: NodeType) -> int:
    return sum(1 for n, t in m.node_types.items() if t == type_)


def test_default_supply_value_is_one() -> None:
    """A map with no supply_values overrides scores supplies at +1 (v1 behavior)."""
    m = line_map(5)
    for n in m.nodes:
        assert m.supply_value(n) == 1


def test_supply_value_override_returned() -> None:
    m = replace(line_map(5), supply_values={1: 2, 2: 3})
    assert m.supply_value(0) == 1   # not overridden
    assert m.supply_value(1) == 2
    assert m.supply_value(2) == 3
    assert m.supply_value(99) == 1  # non-existent node defaults to 1


def test_disabled_when_fraction_zero() -> None:
    """high_value_supply_fraction=0 reverts to v1 (no high-value supplies)."""
    cfg = GameConfig(num_players=4, seed=42, high_value_supply_fraction=0.0)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    assert s.map.supply_values == {}


def test_assigns_some_high_value_at_default_fraction() -> None:
    """At fraction=0.05 on a r=3 map (~37 nodes), at least one supply
    is marked high-value across multiple seeds."""
    found_at_least_one = False
    for seed in range(10):
        cfg = GameConfig(num_players=4, seed=seed)
        m = generate_map(4, seed=seed)
        s = initial_state(cfg, m)
        if s.map.supply_values:
            found_at_least_one = True
            break
    assert found_at_least_one


def test_high_value_skips_homes() -> None:
    """HOME nodes never appear in supply_values; only non-HOME SUPPLY does."""
    cfg = GameConfig(num_players=4, seed=42, high_value_supply_fraction=1.0)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    for n in s.map.supply_values.keys():
        assert s.map.node_types[n] == NodeType.SUPPLY
        assert n not in s.map.home_assignments


def test_assignment_deterministic_from_seed() -> None:
    """Same seed -> same value assignment (replay-safe)."""
    cfg_a = GameConfig(num_players=4, seed=99)
    m_a = generate_map(4, seed=99)
    s_a = initial_state(cfg_a, m_a)
    cfg_b = GameConfig(num_players=4, seed=99)
    m_b = generate_map(4, seed=99)
    s_b = initial_state(cfg_b, m_b)
    assert s_a.map.supply_values == s_b.map.supply_values


def test_high_value_supply_scores_double() -> None:
    """A high-value supply controlled by a player yields +2 instead of +1."""
    m = line_map(5)
    # Mark node 1 (a SUPPLY in line_map) as value=2.
    m = replace(m, supply_values={1: 2})
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)],
                   num_players=2, max_turns=99)
    # Force p0 to own node 1 (so this turn's scoring picks it up).
    s = replace(s, ownership={0: 0, 1: 0, 2: None, 3: None, 4: 1})
    pre = s.scores[0]
    s_after = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # P0 owns home (0, value 1) + node 1 (high-value, +2) = 3 score this turn.
    assert s_after.scores[0] - pre == 3.0


def test_initial_state_skips_assignment_if_already_set() -> None:
    """If the input map already has supply_values, initial_state doesn't
    overwrite (e.g., wire-loaded states preserve their assignment).
    """
    m = line_map(5)
    pre_set = replace(m, supply_values={1: 2, 2: 2})
    cfg = GameConfig(num_players=2, seed=42, high_value_supply_fraction=1.0)
    s = initial_state(cfg, pre_set)
    assert s.map.supply_values == {1: 2, 2: 2}


def test_assign_helper_handles_no_eligible_nodes() -> None:
    """No-op if no SUPPLY nodes (e.g., a degenerate all-HOME map)."""
    cfg = GameConfig(num_players=2, seed=1, high_value_supply_fraction=0.5)
    coords = {0: (0, 0), 1: (1, 0)}
    edges = {0: frozenset({1}), 1: frozenset({0})}
    types = {0: NodeType.HOME, 1: NodeType.HOME}
    homes = {0: 0, 1: 1}
    m = Map(coords=coords, edges=edges, node_types=types, home_assignments=homes)
    out = _assign_high_value_supplies(m, cfg)
    assert out.supply_values == {}
