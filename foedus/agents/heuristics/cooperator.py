"""Cooperator — opportunistically cross-supports allied attacks.

EXPERIMENTAL (Bundle-7-followup probe). Tests whether the alliance-bonus
mechanic (FOEDUS_ALLIANCE_BONUS) reshapes the dominant-strategy
landscape when at least one heuristic actually attempts to capture
the bonus.

Strategy:
  Press: ALLY toward all opponents (so other Cooperators reciprocate
    and so we declare ourselves a cross-supporter).
  Orders: for each owned unit u, if any other player's declared Intent
    (read from state.round_press_pending) is a Move-on-supply that u
    is adjacent to, AND that player's stance toward us is ALLY (or
    NEUTRAL), emit Support(target=their_unit).
    Remaining own units fall back to GreedyHold.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Move, Order, PlayerId, Press, Stance, Support, UnitId,
)


class Cooperator:
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
            their_stance_toward_me = press.stance.get(player, Stance.NEUTRAL)
            if their_stance_toward_me == Stance.HOSTILE:
                continue
            for intent in press.intents:
                order = intent.declared_order
                if not isinstance(order, Move):
                    continue
                if not m.is_supply(order.dest):
                    continue
                for u in my_units:
                    if u.id in used:
                        continue
                    if not m.is_adjacent(u.location, order.dest):
                        continue
                    if u.location == order.dest:
                        continue
                    target_unit = state.units.get(intent.unit_id)
                    if target_unit is None or target_unit.owner != other_pid:
                        continue
                    orders[u.id] = Support(target=intent.unit_id)
                    used.add(u.id)
                    break
        # Remaining own units: fall back to GreedyHold.
        fallback = self._inner.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)
        return orders

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        from foedus.core import Intent
        # Declare ALLY toward all + publish our own GreedyHold-planned
        # moves as Intents so other Cooperators can support us.
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
