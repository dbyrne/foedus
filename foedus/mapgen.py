"""Procedural hex map generation.

The generator dispatches on `archetype`:
- UNIFORM produces v1-compatible maps (no terrain types).
- HIGHLAND_PASS / RIVERLANDS / CONTINENTAL_SWEEP produce maps with
  archetype-specific terrain and structural variation.
"""

from __future__ import annotations

import math
import random
import warnings

from foedus.core import Archetype, Map, NodeId, NodeType

# Minimum supplies (HOME or SUPPLY) reachable within 2 hops of every home,
# traversing only passable nodes. Sonnet-playtest constraint: a player whose
# home is corner-isolated (only their own home reachable for several turns)
# falls behind irrecoverably the first time it's threatened.
_HOME_BALANCE_MIN_SUPPLIES = 3
_HOME_BALANCE_RADIUS = 2
_HOME_BALANCE_MAX_REROLLS = 32


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


def _supplies_within_radius(m: Map, start: NodeId, radius: int) -> int:
    """Count HOME/SUPPLY nodes reachable from `start` within `radius` hops,
    traversing only passable nodes. Includes `start` itself if it's a supply.
    """
    seen = {start}
    frontier = {start}
    for _ in range(radius):
        nxt: set[NodeId] = set()
        for n in frontier:
            for nb in m.neighbors(n):
                if nb in seen or not m.is_passable(nb):
                    continue
                seen.add(nb)
                nxt.add(nb)
        frontier = nxt
    return sum(
        1 for n in seen
        if m.node_types[n] in (NodeType.HOME, NodeType.SUPPLY)
    )


def _is_home_balanced(m: Map) -> bool:
    """Each home tile must have at least _HOME_BALANCE_MIN_SUPPLIES
    HOME/SUPPLY nodes reachable within _HOME_BALANCE_RADIUS hops via passable
    edges. Prevents the doomed-corner-spawn pathology surfaced by both
    Sonnet's playtest and the Haiku P1 turn-4 home loss.
    """
    for home_node in m.home_assignments:
        if _supplies_within_radius(
            m, home_node, _HOME_BALANCE_RADIUS
        ) < _HOME_BALANCE_MIN_SUPPLIES:
            return False
    return True


def generate_map(
    num_players: int,
    seed: int | None = None,
    archetype: Archetype = Archetype.UNIFORM,
    map_radius: int = 3,
) -> Map:
    """Generate a procedural hex map.

    Dispatches on archetype to a specialized generator. UNIFORM preserves
    pre-archetype behavior exactly for backward compatibility.

    Each generated map is checked against the home-balance constraint
    (`_is_home_balanced`); if a generated map fails, we reseed deterministically
    and retry up to `_HOME_BALANCE_MAX_REROLLS` times. The first attempt
    uses the user-supplied seed verbatim, so previously-balanced seeds remain
    bit-identical (only seeds that produced corner-isolated homes will shift).
    """
    if not 2 <= num_players <= 6:
        raise ValueError("num_players must be 2..6")

    # Lazy import avoids any future circular dependency.
    from foedus.archetypes import (
        _gen_continental_sweep,
        _gen_highland_pass,
        _gen_riverlands,
        _gen_uniform,
    )

    def _attempt(rng: random.Random) -> Map:
        if archetype == Archetype.UNIFORM:
            return _gen_uniform(num_players, rng, map_radius)
        if archetype == Archetype.CONTINENTAL_SWEEP:
            return _gen_continental_sweep(num_players, rng, map_radius)
        if archetype == Archetype.HIGHLAND_PASS:
            return _gen_highland_pass(num_players, rng, map_radius)
        if archetype == Archetype.RIVERLANDS:
            return _gen_riverlands(num_players, rng, map_radius)
        raise ValueError(f"Unknown archetype: {archetype}")

    # Reroll seed namespace: keep the unseeded (`seed=None`) reroll path
    # disjoint from the explicit `seed=0` path so collisions across the two
    # call patterns don't reproduce the same imbalanced sequence.
    base = -1 if seed is None else seed
    last_map: Map | None = None
    for attempt in range(_HOME_BALANCE_MAX_REROLLS):
        cur_seed: int | None = seed if attempt == 0 else base * 1000003 + attempt
        m = _attempt(random.Random(cur_seed))
        if _is_home_balanced(m):
            return m
        last_map = m
    # All rerolls failed. Return the most recent attempt rather than raising
    # so callers see a usable (if imperfect) map. In practice no
    # archetype/radius combo we've measured exhausts the budget — but if it
    # does, surface it loudly: a silent imbalanced map would mask deeper
    # mapgen breakage.
    warnings.warn(
        f"generate_map exhausted {_HOME_BALANCE_MAX_REROLLS} rerolls for "
        f"archetype={archetype.value} num_players={num_players} "
        f"map_radius={map_radius} seed={seed}; "
        f"returning last (imbalanced) attempt. This indicates a mapgen bug "
        f"or pathological constraints — please report.",
        RuntimeWarning,
        stacklevel=2,
    )
    assert last_map is not None
    return last_map
