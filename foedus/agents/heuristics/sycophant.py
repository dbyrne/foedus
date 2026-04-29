"""Sycophant — declares ALLY in stance + chat, plays Greedy.

Pure deception. No Intent declaration (so no BetrayalObservation fires
since they never committed to anything specific). Tests whether stance
+ chat alone create real strategic constraint.

Press: ALLY toward all opponents in stance.
Chat: public broadcast saying "let's cooperate".
Orders: identical to Greedy (no holds, walks forward).
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy import Greedy
from foedus.core import (
    ChatDraft, GameState, Order, PlayerId, Press, Stance, UnitId,
)


class Sycophant:
    def __init__(self) -> None:
        self._inner = Greedy()

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
        return [ChatDraft(
            recipients=None,
            body="Let's all cooperate. I'm declaring ALLY toward everyone.",
        )]
