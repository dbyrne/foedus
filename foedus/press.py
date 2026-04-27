"""Round-lifecycle engine functions for Press v0.

The engine never holds a timer or async event loop. These are pure
state-transition functions; drivers (CLI, web UI, training harness) call
them as events arrive.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    GameState,
    Intent,
    Phase,
    PlayerId,
    Press,
)


def submit_press_tokens(state: GameState, player: PlayerId,
                        press: Press) -> GameState:
    """Set/replace player's pending press tokens for the current round.

    Multiple calls overwrite (revisability until done). Intents about units
    not owned by `player` are silently dropped.

    Returns state unchanged if:
    - phase is not NEGOTIATION
    - player is eliminated
    - player has already signaled done this round
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if player in state.eliminated:
        return state
    if player in state.round_done:
        return state

    # Drop intents about units the player doesn't own.
    cleaned_intents: dict[PlayerId, list[Intent]] = {}
    for recipient, intents in press.intents.items():
        kept = [
            i for i in intents
            if i.unit_id in state.units
            and state.units[i.unit_id].owner == player
        ]
        cleaned_intents[recipient] = kept

    cleaned = Press(stance=dict(press.stance), intents=cleaned_intents)

    new_pending = dict(state.round_press_pending)
    new_pending[player] = cleaned

    return replace(state, round_press_pending=new_pending)
