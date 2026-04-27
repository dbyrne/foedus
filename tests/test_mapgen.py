"""Procedural map generation invariants."""

from __future__ import annotations

import pytest

from agent_game.mapgen import generate_map


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
    from agent_game.core import NodeType
    m = generate_map(4, seed=42)
    for node in m.home_assignments:
        assert m.node_types[node] == NodeType.HOME


def test_invalid_player_count_raises() -> None:
    with pytest.raises(ValueError):
        generate_map(1)
    with pytest.raises(ValueError):
        generate_map(7)
