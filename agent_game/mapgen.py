"""Procedural hex map generation.

Uses a hex disk of radius 3 (37 cells) with light per-game variation:
- 0-3 cells randomly removed to vary topology
- N home nodes placed evenly around the perimeter
- ~40% of non-home nodes become supply centers
"""

from __future__ import annotations

import math
import random

from agent_game.core import Map, NodeId, NodeType, PlayerId


def _hex_neighbors(q: int, r: int) -> list[tuple[int, int]]:
    return [
        (q + 1, r),
        (q - 1, r),
        (q, r + 1),
        (q, r - 1),
        (q + 1, r - 1),
        (q - 1, r + 1),
    ]


def _hex_disk(radius: int) -> list[tuple[int, int]]:
    out = []
    for q in range(-radius, radius + 1):
        r1 = max(-radius, -q - radius)
        r2 = min(radius, -q + radius)
        for r in range(r1, r2 + 1):
            out.append((q, r))
    return out


def _hex_to_xy(q: int, r: int) -> tuple[float, float]:
    x = q + r / 2.0
    y = r * (math.sqrt(3) / 2.0)
    return x, y


def _ring_distance(c: tuple[int, int]) -> int:
    q, r = c
    return max(abs(q), abs(r), abs(q + r))


def generate_map(num_players: int, seed: int | None = None) -> Map:
    if not 2 <= num_players <= 6:
        raise ValueError("num_players must be 2..6")

    rng = random.Random(seed)
    radius = 3
    coords = _hex_disk(radius)

    # Perimeter cells, sorted by angle around origin (for symmetric placement).
    perimeter = [c for c in coords if _ring_distance(c) == radius]

    def angle(c: tuple[int, int]) -> float:
        x, y = _hex_to_xy(*c)
        return math.atan2(y, x)

    perimeter.sort(key=angle)

    home_coords = [perimeter[(i * len(perimeter)) // num_players] for i in range(num_players)]

    # Random topology variation: drop 0-3 non-home, non-center cells.
    removable = [c for c in coords if c not in home_coords and c != (0, 0)]
    rng.shuffle(removable)
    removed = set(removable[: rng.randint(0, 3)])

    final_coords = sorted(c for c in coords if c not in removed)
    node_id_of = {c: i for i, c in enumerate(final_coords)}
    coord_of = {i: c for c, i in node_id_of.items()}

    # Adjacency.
    edges: dict[NodeId, set[NodeId]] = {i: set() for i in node_id_of.values()}
    for c, i in node_id_of.items():
        for nbr in _hex_neighbors(*c):
            if nbr in node_id_of:
                edges[i].add(node_id_of[nbr])
    edges_frozen = {n: frozenset(s) for n, s in edges.items()}

    # Home nodes by player.
    home_assignments: dict[NodeId, PlayerId] = {
        node_id_of[hc]: i for i, hc in enumerate(home_coords)
    }

    # Supply centers: all homes plus ~40% of remaining nodes.
    non_home_ids = [n for n in node_id_of.values() if n not in home_assignments]
    rng.shuffle(non_home_ids)
    num_supply = max(num_players, int(len(non_home_ids) * 0.4))
    supply_set = set(non_home_ids[:num_supply])

    node_types: dict[NodeId, NodeType] = {}
    for n in node_id_of.values():
        if n in home_assignments:
            node_types[n] = NodeType.HOME
        elif n in supply_set:
            node_types[n] = NodeType.SUPPLY
        else:
            node_types[n] = NodeType.PLAIN

    return Map(
        coords=coord_of,
        edges=edges_frozen,
        node_types=node_types,
        home_assignments=home_assignments,
    )
