"""Agent protocol — anything implementing `choose_orders` is an agent."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from foedus.core import GameState, Order, PlayerId, UnitId


@runtime_checkable
class Agent(Protocol):
    """An agent that plays the game.

    Agents receive the full `GameState` and should honor fog-of-war by querying
    `foedus.fog.visible_state_for(state, player)` when they want to play
    with only the information their player can see. This is a convention, not
    enforced — self-play training relies on agents not peeking.
    """

    def choose_orders(
        self, state: GameState, player: PlayerId
    ) -> dict[UnitId, Order]:
        """Return orders for all of `player`'s units.

        Missing units default to Hold; invalid orders are silently normalized
        to Hold during resolution.
        """
        ...
