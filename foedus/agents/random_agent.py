"""Reference random agent: picks a uniformly-random legal order per unit."""

from __future__ import annotations

import random

from foedus.core import GameState, Order, PlayerId, UnitId
from foedus.legal import legal_orders_for_unit


class RandomAgent:
    """Picks a uniformly-random legal order for each owned unit.

    Useful as a baseline opponent during NN training and as a smoke-test
    for engine correctness (a random agent should never crash the resolver).
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def choose_orders(
        self, state: GameState, player: PlayerId
    ) -> dict[UnitId, Order]:
        orders: dict[UnitId, Order] = {}
        for u in state.units.values():
            if u.owner != player:
                continue
            choices = legal_orders_for_unit(state, u.id)
            orders[u.id] = self._rng.choice(choices)
        return orders

    def choose_press(self, state, player):  # type: ignore[no-untyped-def]
        from foedus.core import Press
        return Press(stance={}, intents={})

    def chat_drafts(self, state, player):  # type: ignore[no-untyped-def]
        return []
