"""Fog-of-war filtering: per-player private observation of the game state."""

from __future__ import annotations

from typing import Any

from foedus.core import GameState, NodeId, PlayerId, Press, Stance


def visible_state_for(state: GameState, player: PlayerId) -> dict[str, Any]:
    """Return a dict snapshot of what `player` can see.

    Public: ownership of all nodes, scores, eliminations, map structure, turn.
    Private: enemy unit positions are visible only on/adjacent to your units.
    Press v0 fields: public_stance_matrix (everyone), your_inbound_intents
    (recipient-only), your_chat (filtered), your_betrayals (betrayed-only).
    """
    own_units = [u for u in state.units.values() if u.owner == player]
    visible: set[NodeId] = set()
    for u in own_units:
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
        {"id": u.id, "owner": u.owner, "location": u.location}
        for u in state.units.values()
        if u.owner == player or u.location in visible
    ]

    # Press v0 derivations from press_history[-1] (last completed round).
    last_press: dict[PlayerId, Press] = (
        state.press_history[-1] if state.press_history else {}
    )

    # Public stance matrix: stance[i][j] = stance of i toward j (string value).
    public_stance_matrix: dict[PlayerId, dict[PlayerId, str]] = {}
    for i in range(state.config.num_players):
        if i in state.eliminated:
            continue
        public_stance_matrix[i] = {}
        press_i = last_press.get(i, Press(stance={}, intents={}))
        for j in range(state.config.num_players):
            if i == j or j in state.eliminated:
                continue
            public_stance_matrix[i][j] = press_i.stance.get(
                j, Stance.NEUTRAL
            ).value

    # Inbound intents: only intents addressed to `player`.
    your_inbound_intents: dict[PlayerId, list] = {}
    for sender, press_s in last_press.items():
        if sender == player:
            continue
        if player in press_s.intents:
            your_inbound_intents[sender] = list(press_s.intents[player])

    # Outbound press history (this player's own press, all turns).
    your_outbound_press = [
        press_per_turn.get(player, Press(stance={}, intents={}))
        for press_per_turn in state.press_history
    ]

    # Chat filter: keep messages where the player is sender, named recipient,
    # or where recipients is None (public broadcast).
    last_chat = state.chat_history[-1] if state.chat_history else []
    your_chat = [
        m for m in last_chat
        if m.recipients is None
        or m.sender == player
        or player in m.recipients
    ]

    your_betrayals = list(state.betrayals.get(player, []))

    return {
        "turn": state.turn,
        "you": player,
        "ownership": dict(state.ownership),
        "scores": dict(state.scores),
        "eliminated": sorted(state.eliminated),
        "visible_units": visible_units,
        "visible_nodes": sorted(visible),
        "supply_count_you": state.supply_count(player),
        "public_stance_matrix": public_stance_matrix,
        "your_outbound_press": your_outbound_press,
        "your_inbound_intents": your_inbound_intents,
        "your_chat": your_chat,
        "your_betrayals": your_betrayals,
    }
