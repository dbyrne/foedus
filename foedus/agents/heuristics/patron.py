"""Patron — allies broadly, then turns on its strongest partner late.

Strategy:
  Press: ALLY toward all surviving non-eliminated opponents.
  Orders:
    Early/mid game: GreedyHold expansion.
    Late game (after turn = max_turns * late_game_threshold): switch to
    raiding the highest-supply mutual-ALLY partner — the strong neighbour the
    Patron rode alongside, now the most valuable target. Where no unit is
    adjacent to that partner's territory, fall back to GreedyHold.

The aid/leverage economy that used to drive this heuristic's buildup-then-
betray arc was deleted in the 2026-07-02 reciprocity model; target selection
is now by supply count (the strongest ally), preserving the "generous ally,
late defector" character without the removed mechanic.

Defaults `late_game_threshold = 0.6` so a 25-turn game switches at turn 15.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState,
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

    def _richest_ally(self, state: GameState,
                      player: PlayerId) -> PlayerId | None:
        """Highest-supply mutual-ALLY partner (by last locked press), or None.

        Mutual ALLY is read from the previous turn's archived press; at turn 0
        (no history) every surviving opponent is eligible so an early switch
        still has a target. Tiebreak: lowest pid."""
        last = state.press_history[-1] if state.press_history else {}
        my_prev = last.get(player)
        partners: list[PlayerId] = []
        for other in range(state.config.num_players):
            if other == player or other in state.eliminated:
                continue
            their_prev = last.get(other)
            if my_prev is None or their_prev is None:
                partners.append(other)  # no prior stance -> eligible
                continue
            if (my_prev.stance.get(other, Stance.NEUTRAL) == Stance.ALLY
                    and their_prev.stance.get(player, Stance.NEUTRAL) == Stance.ALLY):
                partners.append(other)
        if not partners:
            return None
        partners.sort(key=lambda p: (-state.supply_count(p), p))
        return partners[0]

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        if not self._is_late_game(state):
            return self._inner.choose_orders(state, player)
        target = self._richest_ally(state, player)
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

    def chat_drafts(self, state, player):
        return []
