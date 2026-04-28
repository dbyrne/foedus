"""End-to-end smoke for the Press v0 round-lifecycle path.

Runs a full 4-player heuristic-only game through the same engine API
the orchestrator uses (submit_press_tokens, signal_done, finalize_round)
and asserts the press lifecycle actually exercised — non-empty
press_history with non-empty stance entries.

This catches breakage between the heuristic press behavior (Task 1)
and the engine round-lifecycle (already shipped). The orchestrator
(Tasks 3-6) is then a thin user-facing layer on top.
"""

from __future__ import annotations

from foedus.agents.heuristic import HeuristicAgent
from foedus.core import Archetype, GameConfig, Stance
from foedus.mapgen import generate_map
from foedus.press import (
    finalize_round,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import initial_state


def test_heuristic_only_game_exercises_press_lifecycle() -> None:
    cfg = GameConfig(
        num_players=4, max_turns=5, seed=42,
        archetype=Archetype.CONTINENTAL_SWEEP,
    )
    m = generate_map(cfg.num_players, seed=cfg.seed,
                     archetype=cfg.archetype, map_radius=cfg.map_radius)
    state = initial_state(cfg, m)

    agent = HeuristicAgent()
    while not state.is_terminal():
        survivors = [
            p for p in range(cfg.num_players) if p not in state.eliminated
        ]
        # Phase 1+2 (no chat for heuristics; press only):
        for p in survivors:
            press = agent.choose_press(state, p)
            state = submit_press_tokens(state, p, press)
            state = signal_done(state, p)
        # Finalize with each player's orders.
        orders = {p: agent.choose_orders(state, p) for p in survivors}
        state = finalize_round(state, orders)

    # press_history should have one entry per turn played.
    assert len(state.press_history) == state.turn, (
        f"expected press_history length == turn ({state.turn}), "
        f"got {len(state.press_history)}"
    )
    # At least one turn must have had a non-empty stance entry from at
    # least one player (heuristic press is non-trivial in a multiplayer
    # game).
    saw_nonempty_stance = any(
        any(p.stance for p in turn_press.values())
        for turn_press in state.press_history
    )
    assert saw_nonempty_stance, (
        "expected at least one non-empty stance across press_history; "
        "got all-empty (heuristic press regressed?)"
    )
    # Spot-check: all non-empty stances should map to ALLY (the heuristic
    # never declares HOSTILE or explicit NEUTRAL).
    for turn_press in state.press_history:
        for p, press in turn_press.items():
            for target, stance in press.stance.items():
                assert stance == Stance.ALLY, (
                    f"unexpected stance {stance} from p{p} toward "
                    f"p{target} — heuristic should only declare ALLY"
                )
