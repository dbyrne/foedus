"""Agent protocol — anything implementing `choose_orders` is an agent."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from foedus.core import (
    ChatDraft,
    GameState,
    Order,
    PlayerId,
    Press,
    UnitId,
)


@runtime_checkable
class Agent(Protocol):
    """An agent that plays the game.

    Agents receive the full `GameState` and should honor fog-of-war by
    querying `foedus.fog.visible_state_for(state, player)` when they want to
    play with only the information their player can see. This is a
    convention, not enforced.
    """

    def choose_orders(
        self, state: GameState, player: PlayerId
    ) -> dict[UnitId, Order]:
        """Return orders for all of `player`'s units."""
        ...

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        """Return this player's press for the current round.

        Default implementation returns an empty Press (NEUTRAL toward all,
        no intents shared). Override for press-aware agents.
        """
        return Press(stance={}, intents=[])

    def chat_drafts(self, state: GameState, player: PlayerId
                    ) -> list[ChatDraft]:
        """Return any chat messages this player wants to send this round.

        Default returns no messages. Driver may call this once per round
        (single-shot) or multiple times within a round (interactive).
        Engine fills in turn, sequence, and sender.
        """
        return []
