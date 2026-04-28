"""Archetype-specific map generators and the random_archetype selector.

Each generator function receives (num_players, rng, map_radius) and returns
a Map. They share hex utilities from foedus.mapgen.
"""

from __future__ import annotations

import math
import random

from foedus.core import Archetype, Map, NodeId, NodeType, PlayerId
from foedus.mapgen import _hex_disk, _hex_neighbors, _hex_to_xy, _ring_distance


def _gen_uniform(num_players: int, rng: random.Random,
                 map_radius: int) -> Map:
    """V1-compatible generator: no terrain types, 0-3 cells removed."""
    coords = _hex_disk(map_radius)
    perimeter = [c for c in coords if _ring_distance(c) == map_radius]

    def angle(c: tuple[int, int]) -> float:
        x, y = _hex_to_xy(*c)
        return math.atan2(y, x)

    perimeter.sort(key=angle)
    home_coords = [perimeter[(i * len(perimeter)) // num_players]
                   for i in range(num_players)]

    removable = [c for c in coords if c not in home_coords and c != (0, 0)]
    rng.shuffle(removable)
    removed = set(removable[: rng.randint(0, 3)])

    final_coords = sorted(c for c in coords if c not in removed)
    node_id_of = {c: i for i, c in enumerate(final_coords)}
    coord_of = {i: c for c, i in node_id_of.items()}

    edges: dict[NodeId, set[NodeId]] = {i: set() for i in node_id_of.values()}
    for c, i in node_id_of.items():
        for nbr in _hex_neighbors(*c):
            if nbr in node_id_of:
                edges[i].add(node_id_of[nbr])
    edges_frozen = {n: frozenset(s) for n, s in edges.items()}

    home_assignments: dict[NodeId, PlayerId] = {
        node_id_of[hc]: i for i, hc in enumerate(home_coords)
    }

    non_home_ids = [n for n in node_id_of.values()
                    if n not in home_assignments]
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


def _gen_continental_sweep(num_players: int, rng: random.Random,
                           map_radius: int) -> Map:
    raise NotImplementedError("Implemented in Task 5")


def _gen_highland_pass(num_players: int, rng: random.Random,
                       map_radius: int) -> Map:
    raise NotImplementedError("Implemented in Task 6")


def _gen_archipelago(num_players: int, rng: random.Random,
                     map_radius: int) -> Map:
    raise NotImplementedError("Implemented in Task 7")
