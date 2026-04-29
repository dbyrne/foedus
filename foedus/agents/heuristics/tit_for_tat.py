"""TitForTat — ALLY by default, HOSTILE-once-betrayed.

Maintains an in-process hostile_set (instance variable, not in
GameState — meaning each new game starts fresh). At the start of each
choose_press / choose_orders call, scans state.betrayals[player] for
NEW betrayers and adds them to hostile_set. Once HOSTILE, stays HOSTILE
for the rest of the game.

Press: ALLY toward not-hostile opponents; HOSTILE toward hostile_set.
Orders: prioritize attacking units owned by hostile players; else
GreedyHold fallback.
"""

from __future__ import annotations

from foedus.agents.heuristics._tiebreak import shuffled_neighbors
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Hold, Move, Order, PlayerId, Press, Stance, UnitId,
)


class TitForTat:
    def __init__(self) -> None:
        self.hostile_set: set[PlayerId] = set()
        self._inner = GreedyHold()

    def _update_hostile_set(self, state, player):
        for b in state.betrayals.get(player, []):
            self.hostile_set.add(b.betrayer)

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        self._update_hostile_set(state, player)
        # Compute GreedyHold fallback once (it covers every owned unit).
        fallback = self._inner.choose_orders(state, player)
        # Look for hostile player units adjacent to ours; attack.
        m = state.map
        orders: dict[UnitId, Order] = {}
        for u in state.units.values():
            if u.owner != player:
                continue
            attacked = False
            for nbr in shuffled_neighbors(state, player, u.location):
                target = state.unit_at(nbr)
                if (target is not None
                        and target.owner in self.hostile_set):
                    orders[u.id] = Move(dest=nbr)
                    attacked = True
                    break
            if not attacked:
                # GreedyHold guarantees an entry for every owned unit, but
                # default to Hold defensively in case that ever changes.
                orders[u.id] = fallback.get(u.id, Hold())
        return orders

    def choose_press(self, state, player):
        self._update_hostile_set(state, player)
        opponents = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        stance = {}
        for p in opponents:
            stance[p] = (Stance.HOSTILE if p in self.hostile_set
                         else Stance.ALLY)
        return Press(stance=stance, intents=[])

    def chat_drafts(self, state, player):
        return []
