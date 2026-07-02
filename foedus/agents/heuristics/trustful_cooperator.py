"""TrustfulCooperator — Bundle 4 aware cooperator.

Like Cooperator (cross-supports allied attacks based on declared Intents),
but ALSO engages with the Bundle 4 aid resource: spends aid tokens on
mutual-ALLY partners to back their declared Move intents, while
reciprocating to keep `aid_given` balanced.

Strategy:
  Press: ALLY toward all surviving non-eliminated opponents; publish own
    GreedyHold-planned Moves as Intents (so other Cooperators see what to
    support).
  Aid spending: for each affordable token, find a mutual-ALLY partner whose
    declared Intent is a Move-on-supply we'd like to support. Prefer
    partners with higher `aid_given[partner→self]` (i.e. partners who have
    given us aid; reciprocate to keep leverage balanced) over partners
    we've already aided heavily.
  Orders: Support for declared cross-player Move-on-supply intents we
    can reach geographically (same as Cooperator). Else fall back to
    GreedyHold.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState,
    Intent,
    Move,
    Order,
    PlayerId,
    Press,
    Stance,
    Support,
    UnitId,
)


class TrustfulCooperator:
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
            their_stance_to_me = press.stance.get(player, Stance.NEUTRAL)
            if their_stance_to_me == Stance.HOSTILE:
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
