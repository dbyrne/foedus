"""ConservativeBuilder — captures only supplies adjacent to owned territory.

Strategy:
  for each owned unit u:
    if u is at a supply NOT owned by player AND that supply is adjacent
       to at least one OTHER node owned by player:
      Hold (will flip via rule (b))
    elif u is at an owned supply AND has an adjacent unowned supply
         that's also adjacent to OTHER owned territory:
      Move to that adjacent unowned supply
    elif u is at an owned supply:
      Hold (defend)
    else:
      Move one step back toward an owned supply (retreat)

Press: NEUTRAL toward all.
"""

from __future__ import annotations

from collections import deque

from foedus.core import ChatDraft, GameState, Hold, Move, Order, PlayerId, Press, UnitId


class ConservativeBuilder:
    def __init__(self) -> None:
        pass

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        orders: dict[UnitId, Order] = {}
        # Build a set of all nodes adjacent to player's owned territory
        # (territory = any owned supply or plain).
        owned_nodes = {n for n, o in state.ownership.items() if o == player}
        adj_to_owned = set()
        for n in owned_nodes:
            for nbr in state.map.neighbors(n):
                adj_to_owned.add(nbr)
        for unit in state.units.values():
            if unit.owner != player:
                continue
            orders[unit.id] = self._choose_for_unit(
                state, player, unit, owned_nodes, adj_to_owned
            )
        return orders

    def _choose_for_unit(self, state, player, unit, owned_nodes, adj_to_owned):
        m = state.map
        loc = unit.location
        # If at unowned supply that touches owned territory: Hold to flip.
        if m.is_supply(loc) and state.ownership.get(loc) != player \
                and any(nbr in owned_nodes for nbr in m.neighbors(loc)):
            return Hold()
        # If at owned supply: look for an adjacent unowned supply that
        # ALSO touches owned territory; move there to start a flip.
        if m.is_supply(loc) and state.ownership.get(loc) == player:
            for nbr in sorted(m.neighbors(loc)):
                if (m.is_supply(nbr)
                        and state.ownership.get(nbr) != player
                        and any(n in owned_nodes - {loc}
                                for n in m.neighbors(nbr))):
                    occupant = state.unit_at(nbr)
                    if occupant is None or occupant.owner != player:
                        return Move(dest=nbr)
            return Hold()
        # Otherwise retreat toward owned territory.
        if owned_nodes:
            for nbr in sorted(m.neighbors(loc)):
                if nbr in owned_nodes:
                    return Move(dest=nbr)
        return Hold()

    def choose_press(self, state, player):
        return Press(stance={}, intents=[])

    def chat_drafts(self, state, player):
        return []
