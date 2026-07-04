"""Opt-in per-turn spectate emitter.

Wired as `play_game`'s `on_turn_resolved` callback (see foedus/loop.py). Each
call appends one JSON line to `spectate_game{game_id}.jsonl` describing the
turn that just resolved: declared stances + intents (from the new state's
press_history, the just-archived round), the orders that were submitted, and
the resulting scores/eliminations. Nothing here is engine state -- it is a
read-only projection for a spectator UI.

Default OFF: this module is only ever invoked when a caller explicitly builds
an emitter (harness scripts do so only when FOEDUS_SPECTATE_DIR is set), so
omitting it leaves game output untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

from foedus.core import GameState, Order, PlayerId, Press, UnitId
from foedus.remote.wire import serialize_intent, serialize_orders


def _serialize_press(press: Press) -> dict:
    return {
        "stance": {str(pid): s.value for pid, s in press.stance.items()},
        "intents": [serialize_intent(i) for i in press.intents],
    }


def spectate_turn_emitter(spectate_dir: str | Path, game_id: int):
    """Build an `on_turn_resolved(prev_state, orders_by_player, new_state)`
    callback that appends one JSON line per turn to
    `<spectate_dir>/spectate_game{game_id}.jsonl` (created if needed)."""
    out_dir = Path(spectate_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"spectate_game{game_id}.jsonl"

    def on_turn_resolved(
        prev_state: GameState,
        orders_by_player: dict[PlayerId, dict[UnitId, Order]],
        new_state: GameState,
    ) -> None:
        turn_press = new_state.press_history[-1] if new_state.press_history else {}
        record = {
            "game_id": game_id,
            "turn": new_state.turn,
            "stances": {
                str(pid): _serialize_press(press)["stance"]
                for pid, press in turn_press.items()
            },
            "intents": {
                str(pid): _serialize_press(press)["intents"]
                for pid, press in turn_press.items()
            },
            "orders": {
                str(pid): serialize_orders(orders)
                for pid, orders in orders_by_player.items()
            },
            "scores": {str(pid): score for pid, score in new_state.scores.items()},
            "eliminated": sorted(new_state.eliminated),
        }
        with out_path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    return on_turn_resolved
