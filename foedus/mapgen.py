"""Procedural hex map generation.

The generator dispatches on `archetype`:
- UNIFORM produces v1-compatible maps (no terrain types).
- HIGHLAND_PASS / ARCHIPELAGO / CONTINENTAL_SWEEP produce maps with
  archetype-specific terrain and structural variation.
"""

from __future__ import annotations

import math
import random

from foedus.core import Archetype, Map


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


def generate_map(
    num_players: int,
    seed: int | None = None,
    archetype: Archetype = Archetype.UNIFORM,
    map_radius: int = 3,
) -> Map:
    """Generate a procedural hex map.

    Dispatches on archetype to a specialized generator. UNIFORM preserves
    pre-archetype behavior exactly for backward compatibility.
    """
    if not 2 <= num_players <= 6:
        raise ValueError("num_players must be 2..6")

    rng = random.Random(seed)

    # Lazy import avoids any future circular dependency.
    from foedus.archetypes import (
        _gen_archipelago,
        _gen_continental_sweep,
        _gen_highland_pass,
        _gen_uniform,
    )

    if archetype == Archetype.UNIFORM:
        return _gen_uniform(num_players, rng, map_radius)
    if archetype == Archetype.CONTINENTAL_SWEEP:
        return _gen_continental_sweep(num_players, rng, map_radius)
    if archetype == Archetype.HIGHLAND_PASS:
        return _gen_highland_pass(num_players, rng, map_radius)
    if archetype == Archetype.ARCHIPELAGO:
        return _gen_archipelago(num_players, rng, map_radius)
    raise ValueError(f"Unknown archetype: {archetype}")
