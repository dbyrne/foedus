"""TrustfulCooperator — reciprocation-aware cooperator.

Like Cooperator (cross-supports allied Move-on-supply intents), but chooses
*which* ally to back by the public reciprocation ledger (Primitive B): it
prioritises supporting allies in good reciprocation standing over free-riders,
using its scarce unit-actions on partners who actually reciprocate. This is the
reciprocity-model reincarnation of the old (deleted) aid-ledger reciprocity
gate — same "reward the reciprocators" intent, expressed through real Support
orders and the new `reciprocation_standing` signal instead of aid tokens.

Strategy:
  Press: ALLY toward all surviving non-eliminated opponents; publish own
    GreedyHold-planned Moves as Intents (so other cooperators see what to back).
  Orders: among reachable cross-player Move-on-supply intents, back the ones
    whose owner has the highest reciprocation standing first (freeriders last);
    remaining units fall back to GreedyHold.
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

        # Gather reachable cross-player Move-on-supply support opportunities as
        # (-standing, ally_uid, dest), then serve them
        # highest-reciprocation-standing-first: back genuine reciprocators
        # before free-riders. Tiebreak: lower unit id (stable).
        candidates: list[tuple[float, int, int]] = []
        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid in state.eliminated:
                continue
            if press.stance.get(player, Stance.NEUTRAL) == Stance.HOSTILE:
                continue
            standing = state.reciprocation_standing(other_pid)
            for intent in press.intents:
                order = intent.declared_order
                if not isinstance(order, Move) or not m.is_supply(order.dest):
                    continue
                target_unit = state.units.get(intent.unit_id)
                if target_unit is None or target_unit.owner != other_pid:
                    continue
                candidates.append((-standing, intent.unit_id, order.dest))
        candidates.sort(key=lambda c: (c[0], c[1]))

        for _, ally_uid, ally_dest in candidates:
            for u in my_units:
                if u.id in used:
                    continue
                if not m.is_adjacent(u.location, ally_dest):
                    continue
                if u.location == ally_dest:
                    continue
                orders[u.id] = Support(target=ally_uid)
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
