"""Enumerate geometrically-valid orders for a unit.

"Geometrically valid" = the order will not be normalized to Hold purely on
the basis of map structure, unit existence, or self-dislodge prevention.
Whether the order achieves its *intended effect* depends on what other units
do (e.g., a Support only counts if resolution can apply it meaningfully).

This is what an agent uses to enumerate its action space:
- RandomAgent picks uniformly from this list
- A heuristic agent ranks options from this list
- NN training uses it for action masking
"""

from __future__ import annotations

from foedus.core import (
    GameState,
    Hold,
    Move,
    Order,
    Support,
    UnitId,
)


def legal_orders_for_unit(state: GameState, unit_id: UnitId) -> list[Order]:
    """All geometrically-valid orders for `unit_id`.

    Always includes Hold(). Output is sorted deterministically:
    Hold first, then Moves by destination, then Support entries by target id.

    Reactive Support enumeration: one Support(target=other) per other unit
    that is geometrically reachable as a support target — i.e., the supporter
    is currently adjacent to `other.location` (so support of a Hold is
    trivially possible) OR adjacent to at least one neighbor of `other.location`
    (so support of a Move from `other` is possible). Pin variants
    (require_dest=...) are NOT enumerated; pinning is an opt-in expressive
    behavior, not part of the default candidate set.
    """
    unit = state.units[unit_id]
    m = state.map
    out: list[Order] = [Hold()]

    for nbr in sorted(m.neighbors(unit.location)):
        out.append(Move(dest=nbr))

    others = sorted(state.units.values(), key=lambda u: u.id)
    my_neighbors = m.neighbors(unit.location)
    for other in others:
        if other.id == unit_id:
            continue
        # Reactive Support is geometrically valid if the supporter is
        # adjacent to the target (supports a Hold/Support) OR adjacent
        # to any of the target's neighbors (could support a Move from
        # the target into that neighbor).
        if other.location in my_neighbors:
            out.append(Support(target=other.id))
            continue
        if any(n in my_neighbors for n in m.neighbors(other.location)):
            out.append(Support(target=other.id))

    return out
