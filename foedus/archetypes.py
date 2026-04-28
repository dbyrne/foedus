"""Archetype-specific map generators and the random_archetype selector.

Each generator function receives (num_players, rng, map_radius) and returns
a Map. They share hex utilities from foedus.mapgen.
"""

from __future__ import annotations

import logging
import math
import random

from foedus.core import Archetype, Map, NodeId, NodeType, PlayerId
from foedus.mapgen import _hex_disk, _hex_neighbors, _hex_to_xy, _ring_distance

_log = logging.getLogger(__name__)


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
    """Open plains, dense connectivity, resource-rich.

    Like UNIFORM but with 0-1 cells removed (denser connectivity) and
    ~50% supply density instead of ~40%. No MOUNTAIN/WATER terrain.
    """
    coords = _hex_disk(map_radius)
    perimeter = [c for c in coords if _ring_distance(c) == map_radius]

    def angle(c: tuple[int, int]) -> float:
        x, y = _hex_to_xy(*c)
        return math.atan2(y, x)

    perimeter.sort(key=angle)
    home_coords = [perimeter[(i * len(perimeter)) // num_players]
                   for i in range(num_players)]

    # Continental: remove only 0-1 cells (denser connectivity than UNIFORM).
    removable = [c for c in coords if c not in home_coords and c != (0, 0)]
    rng.shuffle(removable)
    removed = set(removable[: rng.randint(0, 1)])

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
    # Continental: 50% supply density (vs UNIFORM's 40%).
    num_supply = max(num_players, int(len(non_home_ids) * 0.5))
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


def _gen_highland_pass(num_players: int, rng: random.Random,
                       map_radius: int) -> Map:
    """Mountain ridge with passes; defensive flavor.

    1. Generate base hex disk with 0-1 cells removed (minimal variation).
    2. Pick two opposite perimeter cells; trace a ridge between them.
    3. Mark ridge cells as MOUNTAIN, leaving num_passes gaps as PLAIN.
    4. Place homes on alternating sides of the ridge near passes.
    5. Apply ~35% supply density to non-home, non-mountain cells.
    Re-rolls up to 5 times if homes end up unreachable from each other.
    Falls back to UNIFORM if all attempts fail.
    """
    num_passes = max(1, 1 + (num_players // 3))

    for attempt in range(5):
        coords = _hex_disk(map_radius)
        removable = [c for c in coords if c != (0, 0)]
        rng.shuffle(removable)
        removed = set(removable[: rng.randint(0, 1)])
        live_coords = [c for c in coords if c not in removed]

        perimeter = [c for c in live_coords if _ring_distance(c) == map_radius]
        if len(perimeter) < 2:
            continue

        def angle(c: tuple[int, int]) -> float:
            x, y = _hex_to_xy(*c)
            return math.atan2(y, x)

        perimeter.sort(key=angle)

        # Pick two roughly opposite perimeter cells as ridge endpoints.
        endpoint_a_idx = rng.randrange(len(perimeter))
        endpoint_b_idx = (endpoint_a_idx + len(perimeter) // 2) % len(perimeter)
        ep_a = perimeter[endpoint_a_idx]
        ep_b = perimeter[endpoint_b_idx]

        # Trace ridge: cells whose center lies near the line ep_a -> ep_b.
        ax, ay = _hex_to_xy(*ep_a)
        bx, by = _hex_to_xy(*ep_b)
        dx, dy = bx - ax, by - ay
        line_len_sq = dx * dx + dy * dy
        ridge_candidates: list[tuple[int, int]] = []
        for c in live_coords:
            cx, cy = _hex_to_xy(*c)
            if line_len_sq == 0:
                continue
            t = ((cx - ax) * dx + (cy - ay) * dy) / line_len_sq
            if not (0.0 <= t <= 1.0):
                continue
            proj_x = ax + t * dx
            proj_y = ay + t * dy
            d_sq = (cx - proj_x) ** 2 + (cy - proj_y) ** 2
            if d_sq <= 0.85:  # within ~1 hex of the line
                ridge_candidates.append(c)

        if len(ridge_candidates) < num_passes + 2:
            continue  # not enough cells to form a ridge with passes

        # Pick gap cells from ridge, evenly spaced along it.
        ridge_candidates.sort(key=lambda c: ((c[0] - ep_a[0]) ** 2
                                             + (c[1] - ep_a[1]) ** 2))
        pass_indices = [
            (i * len(ridge_candidates)) // num_passes
            for i in range(num_passes)
        ]
        pass_cells = {ridge_candidates[i] for i in pass_indices}
        mountain_cells = set(ridge_candidates) - pass_cells

        # Don't make endpoints mountains (need them for home placement).
        if ep_a in mountain_cells:
            mountain_cells.remove(ep_a)
            pass_cells.add(ep_a)
        if ep_b in mountain_cells:
            mountain_cells.remove(ep_b)
            pass_cells.add(ep_b)

        # Place homes evenly along perimeter, excluding mountains.
        passable_perimeter = [c for c in perimeter if c not in mountain_cells]
        if len(passable_perimeter) < num_players:
            continue
        home_coords = [
            passable_perimeter[(i * len(passable_perimeter)) // num_players]
            for i in range(num_players)
        ]
        if any(h in mountain_cells for h in home_coords):
            continue

        # Build node_id mapping.
        final_coords = sorted(live_coords)
        node_id_of = {c: i for i, c in enumerate(final_coords)}
        coord_of = {i: c for c, i in node_id_of.items()}

        mountain_ids = {node_id_of[c] for c in mountain_cells}
        edges: dict[NodeId, set[NodeId]] = {
            i: set() for i in node_id_of.values()
        }
        for c, i in node_id_of.items():
            if i in mountain_ids:
                continue
            for nbr in _hex_neighbors(*c):
                if nbr in node_id_of and node_id_of[nbr] not in mountain_ids:
                    edges[i].add(node_id_of[nbr])
        edges_frozen = {n: frozenset(s) for n, s in edges.items()}

        home_assignments: dict[NodeId, PlayerId] = {
            node_id_of[hc]: i for i, hc in enumerate(home_coords)
        }

        # Reachability: BFS from first home over passable cells.
        if home_assignments:
            start = next(iter(home_assignments))
            visited = {start}
            frontier = [start]
            while frontier:
                n = frontier.pop()
                for nbr in edges_frozen[n]:
                    if nbr not in visited:
                        visited.add(nbr)
                        frontier.append(nbr)
            if not all(h in visited for h in home_assignments):
                continue  # ridge isolated some homes; re-roll

        # Apply supply density (~35%).
        non_home_passable_ids = [
            n for n in node_id_of.values()
            if n not in home_assignments and n not in mountain_ids
        ]
        rng.shuffle(non_home_passable_ids)
        num_supply = max(num_players, int(len(non_home_passable_ids) * 0.35))
        supply_set = set(non_home_passable_ids[:num_supply])

        node_types: dict[NodeId, NodeType] = {}
        for n in node_id_of.values():
            if n in mountain_ids:
                node_types[n] = NodeType.MOUNTAIN
            elif n in home_assignments:
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

    # Fall back to UNIFORM if all attempts fail. Warn so callers who asked
    # specifically for HIGHLAND_PASS don't silently receive a terrain-free map.
    _log.warning(
        "_gen_highland_pass: all 5 ridge attempts failed for "
        "num_players=%d, map_radius=%d; falling back to UNIFORM map",
        num_players, map_radius,
    )
    return _gen_uniform(num_players, rng, map_radius)


def _gen_riverlands(num_players: int, rng: random.Random,
                    map_radius: int) -> Map:
    """Snaking river divides the map into two regions; two crossings
    connect them. Strategic flavor: control of crossings is decisive.

    1. Pick start/end perimeter points roughly opposite each other.
    2. Pick a waypoint near the midpoint, offset perpendicular to create
       the snake bend.
    3. Trace hex lines along start->waypoint and waypoint->end; gather
       cells within distance ~0.85 of either segment as river candidates.
    4. Pick 2 cells along the path as CROSSINGS (kept as PLAIN/SUPPLY).
    5. Mark remaining river cells as WATER.
    6. Endpoints are not allowed to be water (homes need them).
    7. Place homes evenly along passable perimeter.
    8. Verify all homes mutually reachable; re-roll up to 5 attempts.
    9. Apply ~40% supply density to non-home, non-water cells.
    Falls back to UNIFORM with a logging.warning if all attempts fail.
    """
    NUM_CROSSINGS = 2

    for attempt in range(5):
        coords = _hex_disk(map_radius)
        removable = [c for c in coords if c != (0, 0)]
        rng.shuffle(removable)
        removed = set(removable[: rng.randint(0, 1)])
        live_coords = [c for c in coords if c not in removed]

        perimeter = [c for c in live_coords if _ring_distance(c) == map_radius]
        if len(perimeter) < 2:
            continue

        def angle(c: tuple[int, int]) -> float:
            x, y = _hex_to_xy(*c)
            return math.atan2(y, x)

        perimeter.sort(key=angle)
        start_idx = rng.randrange(len(perimeter))
        end_idx = (start_idx + len(perimeter) // 2) % len(perimeter)
        ep_a = perimeter[start_idx]
        ep_b = perimeter[end_idx]

        # Compute snake waypoint: midpoint perpendicular-offset by random amount.
        ax, ay = _hex_to_xy(*ep_a)
        bx, by = _hex_to_xy(*ep_b)
        mx = (ax + bx) / 2.0
        my = (ay + by) / 2.0
        seg_dx, seg_dy = bx - ax, by - ay
        line_len = math.sqrt(seg_dx * seg_dx + seg_dy * seg_dy)
        if line_len == 0:
            continue
        px, py = -seg_dy / line_len, seg_dx / line_len
        offset = rng.uniform(-line_len * 0.3, line_len * 0.3)
        target_x = mx + px * offset
        target_y = my + py * offset
        # Closest live coord to that perpendicular offset point.
        waypoint = min(
            live_coords,
            key=lambda c: (
                (_hex_to_xy(*c)[0] - target_x) ** 2
                + (_hex_to_xy(*c)[1] - target_y) ** 2
            ),
        )

        def line_candidates(p_start: tuple[int, int],
                            p_end: tuple[int, int],
                            threshold_sq: float = 0.85
                            ) -> list[tuple[int, int]]:
            sx, sy = _hex_to_xy(*p_start)
            ex, ey = _hex_to_xy(*p_end)
            sdx, sdy = ex - sx, ey - sy
            seg_len_sq = sdx * sdx + sdy * sdy
            if seg_len_sq == 0:
                return []
            out: list[tuple[int, int]] = []
            for c in live_coords:
                cx, cy = _hex_to_xy(*c)
                t = ((cx - sx) * sdx + (cy - sy) * sdy) / seg_len_sq
                if not (0.0 <= t <= 1.0):
                    continue
                proj_x = sx + t * sdx
                proj_y = sy + t * sdy
                d_sq = (cx - proj_x) ** 2 + (cy - proj_y) ** 2
                if d_sq <= threshold_sq:
                    out.append(c)
            return out

        seg1 = line_candidates(ep_a, waypoint)
        seg2 = line_candidates(waypoint, ep_b)
        river_candidates = list(set(seg1) | set(seg2))

        if len(river_candidates) < NUM_CROSSINGS + 2:
            continue

        # Sort along the path (rough: by distance from ep_a).
        river_candidates.sort(
            key=lambda c: (
                (_hex_to_xy(*c)[0] - ax) ** 2
                + (_hex_to_xy(*c)[1] - ay) ** 2
            )
        )
        crossing_indices = [
            (i * len(river_candidates)) // NUM_CROSSINGS
            for i in range(NUM_CROSSINGS)
        ]
        # Use the second-ish element to avoid picking endpoints
        # if the path is very short.
        crossings = {river_candidates[i] for i in crossing_indices}
        # Endpoints must not be water.
        crossings.add(ep_a)
        crossings.add(ep_b)

        water_cells = set(river_candidates) - crossings

        # Place homes evenly along passable perimeter.
        passable_perimeter = [c for c in perimeter if c not in water_cells]
        if len(passable_perimeter) < num_players:
            continue
        home_coords = [
            passable_perimeter[(i * len(passable_perimeter)) // num_players]
            for i in range(num_players)
        ]
        if any(h in water_cells for h in home_coords):
            continue

        # Build node id mapping.
        final_coords = sorted(live_coords)
        node_id_of = {c: i for i, c in enumerate(final_coords)}
        coord_of = {i: c for c, i in node_id_of.items()}

        water_ids = {node_id_of[c] for c in water_cells}
        edges: dict[NodeId, set[NodeId]] = {
            i: set() for i in node_id_of.values()
        }
        for c, i in node_id_of.items():
            if i in water_ids:
                continue
            for nbr in _hex_neighbors(*c):
                if nbr in node_id_of and node_id_of[nbr] not in water_ids:
                    edges[i].add(node_id_of[nbr])
        edges_frozen = {n: frozenset(s) for n, s in edges.items()}

        home_assignments: dict[NodeId, PlayerId] = {
            node_id_of[hc]: i for i, hc in enumerate(home_coords)
        }

        # Reachability: BFS from first home over passable cells.
        if home_assignments:
            start = next(iter(home_assignments))
            visited = {start}
            frontier = [start]
            while frontier:
                n = frontier.pop()
                for nbr in edges_frozen[n]:
                    if nbr not in visited:
                        visited.add(nbr)
                        frontier.append(nbr)
            if not all(h in visited for h in home_assignments):
                continue

        # Apply ~40% supply density.
        non_home_passable = [
            n for n in node_id_of.values()
            if n not in home_assignments and n not in water_ids
        ]
        rng.shuffle(non_home_passable)
        num_supply = max(num_players, int(len(non_home_passable) * 0.4))
        supply_set = set(non_home_passable[:num_supply])

        node_types: dict[NodeId, NodeType] = {}
        for n in node_id_of.values():
            if n in water_ids:
                node_types[n] = NodeType.WATER
            elif n in home_assignments:
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

    _log.warning(
        "_gen_riverlands: all 5 river attempts failed for "
        "num_players=%d, map_radius=%d; falling back to UNIFORM map",
        num_players, map_radius,
    )
    return _gen_uniform(num_players, rng, map_radius)


def random_archetype(seed: int | None = None) -> Archetype:
    """Return a random Archetype from the non-UNIFORM set.

    Caller can pass a seed for reproducibility. Useful for picking a
    fresh archetype per game when running test pilots or human play.
    """
    rng = random.Random(seed)
    return rng.choice([
        Archetype.HIGHLAND_PASS,
        Archetype.RIVERLANDS,
        Archetype.CONTINENTAL_SWEEP,
    ])
