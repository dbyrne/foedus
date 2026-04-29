"""Patron — aggressive aid giver with late-game betrayal switch.

Strategy:
  Press: ALLY toward all surviving non-eliminated opponents.
  Aid spending: spend ALL available tokens each turn on the highest-supply
    mutual-ALLY partner. Builds up `aid_given[self→partner]` rapidly,
    accumulating leverage (and thus combat advantage) over them.
  Orders:
    Early/mid game: GreedyHold.
    Late game (after turn = max_turns * late_game_threshold): switch to
    attacking the partner against whom we have the most leverage. Their
    units are mechanically vulnerable to our attacks via leverage_bonus.

Defaults `late_game_threshold = 0.6` so a 25-turn game switches at turn 15.
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
    UnitId,
)


class Patron:
    def __init__(self, late_game_threshold: float = 0.6) -> None:
        self._inner = GreedyHold()
        self._late_threshold = late_game_threshold

    def _is_late_game(self, state: GameState) -> bool:
        return state.turn >= state.config.max_turns * self._late_threshold

    def _most_leveraged_target(self, state: GameState,
                               player: PlayerId) -> PlayerId | None:
        """Player against whom we have the most positive leverage."""
        candidates = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        if not candidates:
            return None
        scored = [(state.leverage(player, p), p) for p in candidates]
        scored.sort(key=lambda x: -x[0])
        if scored[0][0] <= 0:
            return None
        return scored[0][1]

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        if not self._is_late_game(state):
            return self._inner.choose_orders(state, player)
        target = self._most_leveraged_target(state, player)
        if target is None:
            return self._inner.choose_orders(state, player)
        # Late-game raid: each of our units tries to Move into a target-owned
        # adjacent hex. Where no such adjacency, fall back to GreedyHold.
        m = state.map
        fallback = self._inner.choose_orders(state, player)
        orders: dict[UnitId, Order] = {}
        for unit in state.units.values():
            if unit.owner != player:
                continue
            attack_dest = None
            for nbr in m.neighbors(unit.location):
                if state.ownership.get(nbr) == target and m.is_passable(nbr):
                    attack_dest = nbr
                    break
            if attack_dest is not None:
                orders[unit.id] = Move(dest=attack_dest)
            else:
                orders[unit.id] = fallback.get(unit.id)
        return orders

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        return Press(stance=opponents, intents=[])

    def choose_aid(self, state: GameState,
                   player: PlayerId) -> list[AidSpend]:
        balance = state.aid_tokens.get(player, 0)
        if balance <= 0:
            return []
        if not state.press_history:
            return []
        last = state.press_history[-1]
        my_prev = last.get(player)
        if my_prev is None:
            return []
        # Find all mutual-ALLY partners.
        partners: list[PlayerId] = []
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
            partners.append(other_pid)
        if not partners:
            return []
        # Pick the highest-supply partner.
        partners.sort(key=lambda p: -state.supply_count(p))
        recipient = partners[0]
        # Find one of their declared Move intents to back. If none, no spends.
        their_pending = state.round_aid_pending  # not useful — different field
        # Use round_press_pending for declared intents.
        pending = state.round_press_pending.get(recipient)
        if pending is None:
            return []
        target_intents = [
            i for i in pending.intents
            if isinstance(i.declared_order, Move)
        ]
        if not target_intents:
            return []
        # Spend up to balance, cycling through their intents.
        spends: list[AidSpend] = []
        for i in range(balance):
            intent = target_intents[i % len(target_intents)]
            spends.append(AidSpend(
                target_unit=intent.unit_id,
                target_order=intent.declared_order,
            ))
        return spends

    def chat_drafts(self, state, player):
        return []
