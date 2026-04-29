"""OpportunisticBetrayer — declares Intent, breaks it when target is exposed.

Strategy:
  Compute Greedy's plan (greedy_orders).
  Press: ALLY toward all + declare a public Intent for each unit
    matching greedy_orders (commits publicly).
  Orders: by default match the declared intent. BUT if any opponent's
    supply is "exposed" (held by lone unit, no nearby allied defenders),
    pivot one of our units to attack instead — breaks our own Intent
    → triggers BetrayalObservation.

For the simple version: always declare Intent matching Greedy plan.
On orders: if there's an enemy unit on a supply adjacent to one of
our units (any opponent), break Intent and Move to attack.

Press: ALLY toward all + Intents.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy import Greedy
from foedus.core import (
    GameState, Intent, Move, Order, PlayerId, Press, Stance, UnitId,
)


class OpportunisticBetrayer:
    def __init__(self) -> None:
        self._inner = Greedy()

    def _planned_orders(self, state, player):
        return self._inner.choose_orders(state, player)

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        planned = self._planned_orders(state, player)
        # Look for an opponent unit on a supply, adjacent to one of our units.
        m = state.map
        for u in state.units.values():
            if u.owner != player:
                continue
            for nbr in sorted(m.neighbors(u.location)):
                target = state.unit_at(nbr)
                if (target is None
                        or target.owner == player
                        or not m.is_supply(nbr)):
                    continue
                # Found exposed enemy on supply. Break the planned Intent
                # for u and attack instead.
                planned[u.id] = Move(dest=nbr)
                return planned  # Just one betrayal per turn
        return planned

    def choose_press(self, state, player):
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        # Declare Intents matching the planned (pre-betrayal) orders.
        planned = self._planned_orders(state, player)
        intents = [
            Intent(unit_id=uid, declared_order=order, visible_to=None)
            for uid, order in planned.items()
        ]
        return Press(stance=opponents, intents=intents)

    def chat_drafts(self, state, player):
        return []
