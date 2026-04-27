"""Determinism: same seed + same orders → same state.

Critical for self-play: when training breaks at episode 4,213,892, you need to
be able to replay it exactly. Any stray nondeterminism corrupts that.
"""

from __future__ import annotations

from foedus.core import GameConfig, Hold, Move
from foedus.mapgen import generate_map
from foedus.resolve import initial_state, resolve_turn


def test_same_seed_same_initial_state() -> None:
    cfg = GameConfig(num_players=4, seed=42, build_period=999)
    m1 = generate_map(4, seed=42)
    m2 = generate_map(4, seed=42)
    s1 = initial_state(cfg, m1)
    s2 = initial_state(cfg, m2)
    # Compare relevant fields. (GameState is mutable so direct == may fail.)
    assert {u.id: (u.owner, u.location) for u in s1.units.values()} == \
           {u.id: (u.owner, u.location) for u in s2.units.values()}
    assert s1.ownership == s2.ownership
    assert s1.scores == s2.scores


def test_same_orders_produce_same_state() -> None:
    """Run the same game twice; everything should match exactly."""
    cfg = GameConfig(num_players=4, seed=42, build_period=3, max_turns=10)
    m = generate_map(4, seed=42)
    s1 = initial_state(cfg, m)
    s2 = initial_state(cfg, m)

    # Drive both runs with identical order sequences (all Hold).
    for _ in range(5):
        orders = {p: {u.id: Hold() for u in s1.units.values() if u.owner == p}
                  for p in range(cfg.num_players)}
        s1 = resolve_turn(s1, orders)
        orders2 = {p: {u.id: Hold() for u in s2.units.values() if u.owner == p}
                   for p in range(cfg.num_players)}
        s2 = resolve_turn(s2, orders2)

    assert {u.id: (u.owner, u.location) for u in s1.units.values()} == \
           {u.id: (u.owner, u.location) for u in s2.units.values()}
    assert s1.ownership == s2.ownership
    assert s1.scores == s2.scores
    assert s1.eliminated == s2.eliminated


def test_resolve_does_not_mutate_input() -> None:
    """resolve_turn must return new state; original must be untouched."""
    cfg = GameConfig(num_players=2, seed=42, build_period=999, max_turns=10)
    m = generate_map(2, seed=42)
    s = initial_state(cfg, m)

    # Snapshot every mutable surface.
    snapshot_units = {u.id: (u.owner, u.location) for u in s.units.values()}
    snapshot_ownership = dict(s.ownership)
    snapshot_scores = dict(s.scores)
    snapshot_eliminated = set(s.eliminated)
    snapshot_log_len = len(s.log)
    snapshot_turn = s.turn

    # Run a turn with non-trivial orders.
    units = list(s.units.values())
    orders: dict = {}
    for u in units:
        nbrs = sorted(s.map.neighbors(u.location))
        if nbrs:
            orders.setdefault(u.owner, {})[u.id] = Move(dest=nbrs[0])
    resolve_turn(s, orders)

    # Verify the original state is unchanged.
    assert {u.id: (u.owner, u.location) for u in s.units.values()} == snapshot_units
    assert s.ownership == snapshot_ownership
    assert s.scores == snapshot_scores
    assert s.eliminated == snapshot_eliminated
    assert len(s.log) == snapshot_log_len
    assert s.turn == snapshot_turn
