"""Enumerate geometrically-valid orders for a unit.

"Geometrically valid" = the order will not be normalized to Hold purely on
the basis of map structure, unit existence, or self-dislodge prevention.
Whether the order achieves its *intended effect* depends on what other units
do (e.g., a SupportMove only counts if the target unit actually makes the
supported move).

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
    SupportHold,
    SupportMove,
    UnitId,
)


def legal_orders_for_unit(state: GameState, unit_id: UnitId) -> list[Order]:
    """All geometrically-valid orders for `unit_id`.

    Always includes Hold(). Output is sorted in a deterministic order
    (Hold first, then Moves by destination, then SupportHold by target,
    then SupportMove by (target, target_dest)) so callers can rely on it
    for reproducible random sampling.
    """
    unit = state.units[unit_id]
    m = state.map
    out: list[Order] = [Hold()]

    for nbr in sorted(m.neighbors(unit.location)):
        out.append(Move(dest=nbr))

    others = sorted(state.units.values(), key=lambda u: u.id)
    for other in others:
        if other.id == unit_id:
            continue
        if m.is_adjacent(unit.location, other.location):
            out.append(SupportHold(target=other.id))

    for other in others:
        if other.id == unit_id:
            continue
        for target_dest in sorted(m.neighbors(unit.location)):
            if not m.is_adjacent(other.location, target_dest):
                continue
            defender = state.unit_at(target_dest)
            if defender is not None and defender.owner == unit.owner:
                continue
            out.append(SupportMove(target=other.id, target_dest=target_dest))

    return out
