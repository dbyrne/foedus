"""Tests for the Archetype enum and archetype selection (Press v0.2)."""

from __future__ import annotations

from foedus.core import Archetype


def test_archetype_enum_has_four_values() -> None:
    values = {a.value for a in Archetype}
    assert values == {"uniform", "highland_pass", "archipelago", "continental_sweep"}


def test_archetype_uniform_present() -> None:
    assert Archetype.UNIFORM.value == "uniform"


def test_archetype_highland_pass_present() -> None:
    assert Archetype.HIGHLAND_PASS.value == "highland_pass"


def test_archetype_archipelago_present() -> None:
    assert Archetype.ARCHIPELAGO.value == "archipelago"


def test_archetype_continental_sweep_present() -> None:
    assert Archetype.CONTINENTAL_SWEEP.value == "continental_sweep"


def test_continental_sweep_no_terrain() -> None:
    """Continental Sweep should have no MOUNTAIN or WATER."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.CONTINENTAL_SWEEP)
        types = set(m.node_types.values())
        assert NodeType.MOUNTAIN not in types
        assert NodeType.WATER not in types


def test_continental_sweep_higher_supply_density() -> None:
    """Continental Sweep targets ~50% supply density (vs UNIFORM's 40%)."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    densities = []
    for seed in range(20):
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.CONTINENTAL_SWEEP)
        non_home = [n for n in m.nodes if m.node_types[n] != NodeType.HOME]
        supply = [n for n in non_home if m.node_types[n] == NodeType.SUPPLY]
        densities.append(len(supply) / len(non_home))
    avg = sum(densities) / len(densities)
    assert 0.40 <= avg <= 0.60, f"avg supply density {avg:.2%}"


def test_continental_sweep_is_deterministic() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    m1 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.CONTINENTAL_SWEEP)
    m2 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.CONTINENTAL_SWEEP)
    assert m1.coords == m2.coords
    assert m1.edges == m2.edges
    assert m1.node_types == m2.node_types


def test_continental_sweep_homes_match_player_count() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for n in [2, 3, 4, 5, 6]:
        m = generate_map(num_players=n, seed=42,
                         archetype=Archetype.CONTINENTAL_SWEEP)
        assert len(m.home_assignments) == n


def test_highland_pass_has_mountains() -> None:
    """Highland Pass produces at least one MOUNTAIN cell per map."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.HIGHLAND_PASS)
        types = list(m.node_types.values())
        assert NodeType.MOUNTAIN in types, f"seed {seed}: no mountains"


def test_highland_pass_no_water() -> None:
    """Highland Pass uses MOUNTAIN, never WATER."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.HIGHLAND_PASS)
        assert NodeType.WATER not in m.node_types.values()


def test_highland_pass_homes_reachable() -> None:
    """Every home is reachable from every other home via passable cells.

    Passes through the ridge must exist; otherwise homes get isolated.
    """
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.HIGHLAND_PASS)
        homes = sorted(m.home_assignments.keys())
        start = homes[0]
        visited = {start}
        frontier = [start]
        while frontier:
            n = frontier.pop()
            for nbr in m.edges[n]:
                if nbr not in visited and m.is_passable(nbr):
                    visited.add(nbr)
                    frontier.append(nbr)
        for h in homes:
            assert h in visited, \
                f"seed {seed}: home {h} unreachable from home {start}"


def test_highland_pass_mountain_cells_have_no_edges() -> None:
    """MOUNTAIN cells should have empty edge sets and no neighbors."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    m = generate_map(num_players=4, seed=42,
                     archetype=Archetype.HIGHLAND_PASS)
    for n, t in m.node_types.items():
        if t == NodeType.MOUNTAIN:
            assert m.edges[n] == frozenset(), f"mountain node {n} has edges"
        else:
            for nbr in m.edges[n]:
                assert m.node_types[nbr] != NodeType.MOUNTAIN


def test_highland_pass_is_deterministic() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    m1 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.HIGHLAND_PASS)
    m2 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.HIGHLAND_PASS)
    assert m1.coords == m2.coords
    assert m1.edges == m2.edges
    assert m1.node_types == m2.node_types
