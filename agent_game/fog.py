"""Fog-of-war filtering: per-player private observation of the game state."""

from __future__ import annotations

from typing import Any

from agent_game.core import GameState, NodeId, PlayerId


def visible_state_for(state: GameState, player: PlayerId) -> dict[str, Any]:
    """Return a dict snapshot of what `player` can see.

    Public: ownership of all nodes, scores, eliminations, map structure, turn.
    Private: enemy unit positions are visible only on/adjacent to your units.
    """
    own_units = [u for u in state.units.values() if u.owner == player]
    visible: set[NodeId] = set()
    for u in own_units:
        # BFS from unit's location up to fog_radius hops.
        visible.add(u.location)
        frontier = {u.location}
        for _ in range(state.config.fog_radius):
            next_frontier: set[NodeId] = set()
            for n in frontier:
                for nbr in state.map.neighbors(n):
                    if nbr not in visible:
                        visible.add(nbr)
                        next_frontier.add(nbr)
            frontier = next_frontier

    visible_units = [
        {
            "id": u.id,
            "owner": u.owner,
            "location": u.location,
        }
        for u in state.units.values()
        if u.owner == player or u.location in visible
    ]

    return {
        "turn": state.turn,
        "you": player,
        "ownership": dict(state.ownership),
        "scores": dict(state.scores),
        "eliminated": sorted(state.eliminated),
        "visible_units": visible_units,
        "visible_nodes": sorted(visible),
        "supply_count_you": state.supply_count(player),
    }
