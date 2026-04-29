"""Bandwagon — ALLY everyone, play GreedyHold under the hood.

Strategy:
  Press: ALLY toward all active opponents (no enemies).
  Orders: delegate to GreedyHold — a reasonable proxy for "do what
    successful expanders do". The original design called for mirroring
    the leader's last-round order pattern, but that requires a per-turn
    order log not currently exposed via GameState; GreedyHold is the
    pragmatic stand-in.
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
