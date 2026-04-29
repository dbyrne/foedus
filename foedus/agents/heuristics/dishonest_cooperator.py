"""DishonestCooperator — declares cross-support intents, never reciprocates.

EXPERIMENTAL probe (paired with Cooperator). Tests whether the alliance
bonus is exploitable by a freerider that publishes Move-on-supply intents
(so genuine Cooperators support its attacks) but never issues
cross-supports for anyone else's intents — just plays GreedyHold orders.

Strategy:
  Press: ALLY toward all + publish own GreedyHold-planned Move intents
    (identical to Cooperator's press — allies can't tell us apart from
    declared signals alone).
  Orders: pure GreedyHold. Never issues cross-player SupportMove.

Predicted: at any positive FOEDUS_ALLIANCE_BONUS, DishonestCooperator
outscores Cooperator because it receives the alliance bonus on its
supported attacks but never spends an action supporting someone else.
This validates the design call that Bundle 4 must ship paired with
Intent-break / cooperation-consistency consequences.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Intent, Move, Order, PlayerId, Press, Stance, UnitId,
)


class DishonestCooperator:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        # Pure GreedyHold — no cross-support, no reciprocation.
        return self._inner.choose_orders(state, player)

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        # Publish our own planned Moves as Intents so allies will
        # cross-support our attacks. Identical signal to Cooperator's.
        planned = self._inner.choose_orders(state, player)
        intents = [
            Intent(unit_id=uid, declared_order=order, visible_to=None)
            for uid, order in planned.items()
            if isinstance(order, Move)
        ]
        return Press(stance=opponents, intents=intents)

    def chat_drafts(self, state, player):
        return []
