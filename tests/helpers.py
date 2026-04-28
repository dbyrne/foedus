"""Test helpers: tiny synthetic maps and state builders."""

from __future__ import annotations

from foedus.core import (
    GameConfig,
    GameState,
    Map,
    NodeId,
    NodeType,
    PlayerId,
    Unit,
)


def line_map(n_nodes: int) -> Map:
    """Linear chain: 0 - 1 - 2 - ... - (n-1).
    Endpoints are HOMEs (player 0 at node 0, player 1 at node n-1),
    interior nodes are SUPPLY.
    """
    coords = {i: (i, 0) for i in range(n_nodes)}
    edges: dict[NodeId, frozenset[NodeId]] = {}
    for i in range(n_nodes):
        nb: set[int] = set()
        if i > 0:
            nb.add(i - 1)
        if i < n_nodes - 1:
            nb.add(i + 1)
        edges[i] = frozenset(nb)
    node_types = {i: NodeType.SUPPLY for i in range(n_nodes)}
    node_types[0] = NodeType.HOME
    node_types[n_nodes - 1] = NodeType.HOME
    home_assignments = {0: 0, n_nodes - 1: 1}
    return Map(coords=coords, edges=edges, node_types=node_types,
               home_assignments=home_assignments)


def triangle_map() -> Map:
    """3-node fully-connected triangle. Each node a HOME for one player."""
    coords = {0: (0, 0), 1: (1, 0), 2: (0, 1)}
    edges = {
        0: frozenset({1, 2}),
        1: frozenset({0, 2}),
        2: frozenset({0, 1}),
    }
    node_types = {0: NodeType.HOME, 1: NodeType.HOME, 2: NodeType.HOME}
    home_assignments = {0: 0, 1: 1, 2: 2}
    return Map(coords=coords, edges=edges, node_types=node_types,
               home_assignments=home_assignments)


def make_state(m: Map, units: list[Unit], *, num_players: int = 2,
               build_period: int = 999, max_turns: int = 20,
               turn: int = 0, fog_radius: int = 1,
               detente_threshold: int | None = None,
               peace_threshold: int | None = None) -> GameState:
    """Build a GameState with units placed and ownership inferred from unit
    positions.

    Ownership seeding (precedence, low to high):
      1. All nodes start as None (unowned).
      2. Home nodes are seeded from `m.home_assignments` so each player's
         home is owned by them at start. Tests that need a home to start
         unowned must explicitly override `state.ownership[node] = None`
         after construction.
      3. Any node with a unit at construction time is owned by that unit's
         owner (overrides home-seeding for non-home occupied nodes).

    `detente_threshold` (or its deprecated alias `peace_threshold`) defaults
    to 0 (détente disabled) so single-purpose tests aren't accidentally
    terminated by the détente condition.
    """
    if detente_threshold is None and peace_threshold is None:
        detente_threshold = 0
    elif detente_threshold is None:
        detente_threshold = peace_threshold

    ownership: dict[NodeId, PlayerId | None] = {n: None for n in m.nodes}
    # Seed home node ownership from map's home_assignments.
    for node, player in m.home_assignments.items():
        ownership[node] = player
    for u in units:
        ownership[u.location] = u.owner

    return GameState(
        turn=turn,
        map=m,
        units={u.id: u for u in units},
        ownership=ownership,
        scores={p: 0.0 for p in range(num_players)},
        eliminated=set(),
        next_unit_id=max((u.id for u in units), default=-1) + 1,
        config=GameConfig(num_players=num_players, max_turns=max_turns,
                          build_period=build_period, fog_radius=fog_radius,
                          detente_threshold=detente_threshold),
    )
