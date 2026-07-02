"""Reciprocator — supports allies every turn it can, to stay in good standing.

Probe for the reciprocity model (Primitive B). Unlike DishonestCooperator (takes
support, never gives) this heuristic reliably GIVES ally-Support, so its
reciprocation standing stays high and it keeps earning the mover-side alliance
bonus. It should thrive under the gate — the positive control against which the
free-riders (DishonestCooperator, MinimalReciprocator) are measured.

Strategy:
  Press: ALLY toward all + publish truthful GreedyHold-planned Move intents.
  Orders: for each owned unit, if a mutual-non-hostile ally declared a Move
    this unit can reach, Support it (broader than Cooperator, which only backs
    Move-on-supply). Remaining units fall back to GreedyHold.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Intent, Move, Order, PlayerId, Press, Stance, Support, UnitId,
)


class Reciprocator:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        my_unit_ids = {u.id for u in my_units}
        orders: dict[UnitId, Order] = {}
        used: set[UnitId] = set()
        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid in state.eliminated:
                continue
            if press.stance.get(player, Stance.NEUTRAL) == Stance.HOSTILE:
                continue
            for intent in press.intents:
                order = intent.declared_order
                if not isinstance(order, Move):
                    continue
                target_unit = state.units.get(intent.unit_id)
                if target_unit is None or target_unit.owner != other_pid:
                    continue
                for u in my_units:
                    if u.id in used:
                        continue
                    # Supporter must be adjacent to the ally's destination
                    # (and not be the destination itself).
                    if not m.is_adjacent(u.location, order.dest):
                        continue
                    if u.location == order.dest:
                        continue
                    orders[u.id] = Support(target=intent.unit_id)
                    used.add(u.id)
                    break
        fallback = self._inner.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)
        return orders

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        planned = self._inner.choose_orders(state, player)
        intents = [
            Intent(unit_id=uid, declared_order=order, visible_to=None)
            for uid, order in planned.items()
            if isinstance(order, Move)
        ]
        return Press(stance=opponents, intents=intents)

    def chat_drafts(self, state, player):
        return []
