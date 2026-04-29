"""Bandwagon — ALLY everyone, mirror the leader's behavior.

Strategy:
  Identify leader = opponent with most supplies.
  Press: ALLY toward all active opponents.
  Orders: fall back to GreedyHold (mirror "expansion" since most leaders
    expand). The "mirror leader's last-round order pattern" idea is hard
    to implement without engine-side per-turn order log; GreedyHold is
    a reasonable proxy for "do what successful expanders do".
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import GameState, Order, PlayerId, Press, Stance, UnitId


class Bandwagon:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        return self._inner.choose_orders(state, player)

    def choose_press(self, state, player):
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        return Press(stance=opponents, intents=[])

    def chat_drafts(self, state, player):
        return []
