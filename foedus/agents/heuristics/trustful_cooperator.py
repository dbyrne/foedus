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
    AidSpend,
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

    def choose_aid(self, state: GameState,
                   player: PlayerId) -> list[AidSpend]:
        """Spend tokens on mutual-ALLY partners' declared Move intents.

        Reciprocity heuristic: prefer aiding partners who have given us
        more aid than we've given them (reduces our owed leverage).
        """
        balance = state.aid_tokens.get(player, 0)
        if balance <= 0:
            return []
        # Need a previous-turn locked press for the mutual-ALLY gate.
        if not state.press_history:
            return []
        last = state.press_history[-1]
        my_prev = last.get(player)
        if my_prev is None:
            return []
        candidates: list[tuple[float, AidSpend]] = []
        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid in state.eliminated:
                continue
            # Mutual ALLY in last archived press?
            their_prev = last.get(other_pid)
            if their_prev is None:
                continue
            if my_prev.stance.get(other_pid, Stance.NEUTRAL) != Stance.ALLY:
                continue
            if their_prev.stance.get(player, Stance.NEUTRAL) != Stance.ALLY:
                continue
            # Prefer partners we owe (they aided us more than vice-versa).
            owed = state.leverage(other_pid, player)  # >0 if they aided us more
            for intent in press.intents:
                if not isinstance(intent.declared_order, Move):
                    continue
                # Higher owed score → higher priority for reciprocation.
                priority = float(owed)
                candidates.append((priority, AidSpend(
                    target_unit=intent.unit_id,
                )))
        # Sort by descending priority, take up to balance.
        candidates.sort(key=lambda c: -c[0])
        return [spend for _, spend in candidates[:balance]]

    def chat_drafts(self, state, player):
        return []
