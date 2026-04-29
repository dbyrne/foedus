"""Sycophant — declares ALLY in stance + Hold intents, plays Greedy.

Pure deception. Declares peaceful intent (ALLY to all + every unit
publishes a Hold Intent), then plays Greedy under the hood (walks
forward, captures supplies). The mismatch between declared Hold and
submitted Move fires BetrayalObservations every turn — which is what
Bundle 4's détente reset (B5) needs to trigger on lying tables.

Pre-Bundle-4 Sycophant declared no intents, so no betrayals fired.
Updated to lie *about specific orders* so the engine's intent-verification
machinery can observe the dishonesty.

Press: ALLY toward all opponents; public Hold intent for each owned unit.
Chat: public broadcast saying "let's cooperate".
Orders: identical to Greedy (walks forward; mismatches the declared Holds).
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy import Greedy
from foedus.core import (
    ChatDraft, GameState, Hold, Intent, Order, PlayerId,
    Press, Stance, UnitId,
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
        # Lie: declare Hold for every owned unit. We'll actually play Greedy.
        intents = [
            Intent(unit_id=u.id, declared_order=Hold(), visible_to=None)
            for u in state.units.values()
            if u.owner == player
        ]
        return Press(stance=opponents, intents=intents)

    def chat_drafts(self, state, player):
        return [ChatDraft(
            recipients=None,
            body="Let's all cooperate. I'm declaring ALLY toward everyone.",
        )]
