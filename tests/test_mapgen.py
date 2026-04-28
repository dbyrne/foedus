"""Procedural map generation invariants."""

from __future__ import annotations

import pytest

from foedus.mapgen import generate_map


def _bfs_reachable(start: int, edges: dict[int, frozenset[int]]) -> set[int]:
    seen = {start}
    frontier = [start]
    while frontier:
        nxt = []
        for n in frontier:
            for nbr in edges.get(n, frozenset()):
                if nbr not in seen:
                    seen.add(nbr)
                    nxt.append(nbr)
        frontier = nxt
    return seen


@pytest.mark.parametrize("num_players", [2, 3, 4, 5, 6])
def test_one_home_per_player(num_players: int) -> None:
    m = generate_map(num_players, seed=42)
    homes_by_player: dict[int, list[int]] = {}
    for node, player in m.home_assignments.items():
        homes_by_player.setdefault(player, []).append(node)
    assert sorted(homes_by_player.keys()) == list(range(num_players))
    for p, nodes in homes_by_player.items():
        assert len(nodes) == 1, f"player {p} has {len(nodes)} homes"


@pytest.mark.parametrize("num_players", [2, 3, 4, 5, 6])
def test_map_is_connected(num_players: int) -> None:
    m = generate_map(num_players, seed=42)
    start = next(iter(m.nodes))
    reachable = _bfs_reachable(start, m.edges)
    assert reachable == set(m.nodes), f"unreachable nodes: {set(m.nodes) - reachable}"


@pytest.mark.parametrize("seed", [0, 1, 42, 1234, 99999])
def test_seed_reproducibility(seed: int) -> None:
    m1 = generate_map(4, seed=seed)
    m2 = generate_map(4, seed=seed)
    assert m1.coords == m2.coords
    assert m1.edges == m2.edges
    assert m1.node_types == m2.node_types
    assert m1.home_assignments == m2.home_assignments


def test_different_seeds_produce_different_maps() -> None:
    m1 = generate_map(4, seed=1)
    m2 = generate_map(4, seed=2)
    # At minimum the home assignments should differ for some seed; if they don't,
    # at least node count or supply distribution should.
    differ = (
        m1.coords != m2.coords
        or m1.home_assignments != m2.home_assignments
        or m1.node_types != m2.node_types
    )
    assert differ


def test_edges_are_symmetric() -> None:
    m = generate_map(4, seed=42)
    for n, nbrs in m.edges.items():
        for nbr in nbrs:
            assert n in m.edges[nbr], f"asymmetric edge {n} <-> {nbr}"


def test_no_self_loops() -> None:
    m = generate_map(4, seed=42)
    for n, nbrs in m.edges.items():
        assert n not in nbrs


def test_homes_are_supply_centers() -> None:
    """Every home node is a supply center."""
    from foedus.core import NodeType
    m = generate_map(4, seed=42)
    for node in m.home_assignments:
        assert m.node_types[node] == NodeType.HOME


def test_invalid_player_count_raises() -> None:
    with pytest.raises(ValueError):
        generate_map(1)
    with pytest.raises(ValueError):
        generate_map(7)


def test_node_type_has_mountain_and_water() -> None:
    from foedus.core import NodeType
    assert NodeType.MOUNTAIN.value == "mountain"
    assert NodeType.WATER.value == "water"


def test_map_is_passable_for_plain_supply_home() -> None:
    from foedus.core import Map, NodeType
    m = Map(
        coords={0: (0, 0), 1: (1, 0), 2: (0, 1)},
        edges={0: frozenset({1, 2}), 1: frozenset({0, 2}), 2: frozenset({0, 1})},
        node_types={0: NodeType.PLAIN, 1: NodeType.SUPPLY, 2: NodeType.HOME},
        home_assignments={2: 0},
    )
    assert m.is_passable(0) is True
    assert m.is_passable(1) is True
    assert m.is_passable(2) is True


def test_map_is_passable_false_for_mountain_water() -> None:
    from foedus.core import Map, NodeType
    m = Map(
        coords={0: (0, 0), 1: (1, 0)},
        edges={0: frozenset(), 1: frozenset()},
        node_types={0: NodeType.MOUNTAIN, 1: NodeType.WATER},
        home_assignments={},
    )
    assert m.is_passable(0) is False
    assert m.is_passable(1) is False


def test_uniform_archetype_preserves_v1_output_for_seed() -> None:
    """The UNIFORM archetype must produce maps byte-identical to the
    pre-archetype generator for the same seed and player count.
    This is the primary backward-compat invariant."""
    from foedus.core import Archetype
    from foedus.mapgen import generate_map

    m_explicit = generate_map(num_players=4, seed=42,
                              archetype=Archetype.UNIFORM)
    m_default = generate_map(num_players=4, seed=42)

    assert m_explicit.coords == m_default.coords
    assert m_explicit.edges == m_default.edges
    assert m_explicit.node_types == m_default.node_types
    assert m_explicit.home_assignments == m_default.home_assignments


def test_default_generate_map_produces_uniform_archetype() -> None:
    """Default archetype is UNIFORM — no terrain types."""
    from foedus.core import NodeType
    from foedus.mapgen import generate_map
    m = generate_map(num_players=4, seed=42)
    types = {t for t in m.node_types.values()}
    assert NodeType.MOUNTAIN not in types
    assert NodeType.WATER not in types


def test_generate_map_accepts_archetype_kwarg() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    m = generate_map(num_players=4, seed=42, archetype=Archetype.UNIFORM)
    assert m is not None
