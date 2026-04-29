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
    NEUTRAL), emit SupportMove(target=their_unit, target_dest=that_supply).
    Remaining own units fall back to GreedyHold.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Move, Order, PlayerId, Press, Stance, SupportMove, UnitId,
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
            # Bundle 4 reciprocity gate: don't waste a unit-turn supporting
            # a partner we already lead by more than a small slack on the
            # trust ledger. They've been freeriding; stop subsidizing.
            if state.leverage(player, other_pid) > 1:
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
                    orders[u.id] = SupportMove(
                        target=intent.unit_id,
                        target_dest=order.dest,
                    )
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

    def choose_aid(self, state: GameState,
                   player: PlayerId):
        """Bundle 4: back cross-support intents from RECIPROCATING partners.

        Refuses to keep funding freeriders — only spends on partners where
        leverage(self, partner) <= 0 (partner has given us at least as much
        aid as we've given them, so we're not subsidizing). At turn 0 (no
        ledger yet) all partners are eligible.

        Within the eligible set, mirrors the SupportMove logic in
        choose_orders so the alliance bonus fires on captures we
        geographically contribute to.
        """
        from foedus.core import AidSpend
        balance = state.aid_tokens.get(player, 0)
        if balance <= 0:
            return []
        if not state.press_history:
            return []
        last = state.press_history[-1]
        my_prev = last.get(player)
        if my_prev is None:
            return []
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        spends: list = []
        used: set = set()
        # Sort partners by reciprocation: prefer partners who owe us
        # (negative leverage from our side) over partners we already owe.
        partner_priority = []
        for other_pid in range(state.config.num_players):
            if other_pid == player or other_pid in state.eliminated:
                continue
            their_prev = last.get(other_pid)
            if their_prev is None:
                continue
            if my_prev.stance.get(other_pid, Stance.NEUTRAL) != Stance.ALLY:
                continue
            if their_prev.stance.get(player, Stance.NEUTRAL) != Stance.ALLY:
                continue
            lev_against_us = state.leverage(other_pid, player)
            # Filter: only spend on partners where we don't already owe them
            # heavily (we lead by no more than a small slack).
            if state.leverage(player, other_pid) > 1:
                continue
            partner_priority.append((lev_against_us, other_pid))
        partner_priority.sort(key=lambda x: -x[0])
        for _, other_pid in partner_priority:
            press = state.round_press_pending.get(other_pid)
            if press is None:
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
                    spends.append(AidSpend(
                        target_unit=intent.unit_id,
                        target_order=order,
                    ))
                    used.add(u.id)
                    break
                if len(spends) >= balance:
                    break
            if len(spends) >= balance:
                break
        return spends[:balance]

    def chat_drafts(self, state, player):
        return []
