"""Global engine invariants that must hold after every resolution, checked
across real games (not just hand-built unit scenarios).

Regression guard for the resolver cycle-detection bug (pre-leaderboard
correctness bundle): `_resolve_moves` could, on certain cycle+dislodge
interleavings, land two units on the same node. `test_resolve.py` has a
minimal, hand-built repro of the exact mechanism; this file sweeps real
games (procedural maps, full heuristic roster, random pairings) so any
future regression -- from this mechanism or a new one -- gets caught even
without knowing the failure shape in advance.
"""

from __future__ import annotations

import random
from collections import Counter

from foedus.agents.heuristics import ROSTER
from foedus.core import Archetype, GameConfig
from foedus.mapgen import generate_map
from foedus.press import finalize_round, signal_done, submit_press_tokens
from foedus.resolve import initial_state

# The exact seeds that reproduced the cycle-detection two-units-one-node bug
# on unpatched main, found by sweeping continental_sweep/radius-2 4-player
# games with random heuristic pairings (matching the retreats evidence
# packet's sweep parameters). Kept explicit so this test anchors on the real
# failure even if the broader random scan below is ever narrowed.
_KNOWN_BAD_SEEDS = (38, 284, 351, 542, 622)

_ROSTER_NAMES = [n for n in ROSTER if n != "Random"]


def _assert_one_unit_per_node(state, seed: int, turn: int) -> None:
    locations = Counter(u.location for u in state.units.values())
    dupes = {node: count for node, count in locations.items() if count > 1}
    assert not dupes, (
        f"one-unit-per-node invariant violated at seed={seed} turn={turn}: "
        f"node(s) with >1 unit: {dupes}"
    )


def _run_and_check(seed: int, num_players: int = 4, max_turns: int = 15,
                    map_radius: int = 2) -> None:
    rng = random.Random(seed)
    agent_names = [rng.choice(_ROSTER_NAMES) for _ in range(num_players)]
    cfg = GameConfig(num_players=num_players, max_turns=max_turns, seed=seed,
                      archetype=Archetype.CONTINENTAL_SWEEP,
                      map_radius=map_radius, peace_threshold=99)
    m = generate_map(num_players, seed=seed, archetype=cfg.archetype,
                     map_radius=cfg.map_radius)
    state = initial_state(cfg, m)
    agents = [ROSTER[name]() for name in agent_names]

    turn = 0
    while not state.is_terminal():
        for pid in range(num_players):
            if pid in state.eliminated:
                continue
            state = submit_press_tokens(state, pid, agents[pid].choose_press(state, pid))
        for pid in range(num_players):
            if pid in state.eliminated:
                continue
            state = signal_done(state, pid)
        orders_by_player = {
            pid: agents[pid].choose_orders(state, pid)
            for pid in range(num_players) if pid not in state.eliminated
        }
        state = finalize_round(state, orders_by_player)
        turn += 1
        _assert_one_unit_per_node(state, seed, turn)


def test_one_unit_per_node_known_bad_seeds() -> None:
    """Seeds that reproduced the cycle-detection overwrite bug on main."""
    for seed in _KNOWN_BAD_SEEDS:
        _run_and_check(seed)


def test_one_unit_per_node_random_sweep() -> None:
    """Broader sweep with random heuristic pairings, for general coverage
    against future regressions of any shape (not just this bug's mechanism).
    """
    for seed in range(150):
        _run_and_check(seed)
