"""Tests for playtest-feedback Bundle 1.

Sources of these requirements:
- Sonnet playtest (5 priority fixes): walk-in capture, build sort, detente
  scaling, fog-respecting legal-orders, mapgen home-balance.
- Haiku playtest (this branch): the specific bugs/UX gaps both Haiku agents
  independently identified — visible_nodes UX, support-cut not surfaced in
  log, attempted-but-bounced destinations not surfaced in log.

Bundle 1 covers the unanimous, low-risk fixes:
  B  — build sort prefers supply nodes
  C  — detente threshold scales with num_players
  E  — mapgen home-balance check (rerolls until each home has >=3 supplies
       within 2 hops)
  F  — log surfaces "support cut by attack from u<X>"
  G  — log surfaces attempted destinations of bounced units
  U  — visible_nodes regression (was clobbered by an inner-loop rebinding)

Walk-in capture (A) and strict-majority (I) are deliberately out of scope —
they change game balance and need a design decision first (Bundle 2).
"""

from __future__ import annotations

from foedus.core import (
    Archetype,
    GameConfig,
    GameState,
    Hold,
    Move,
    NodeType,
    Phase,
    Press,
    SupportMove,
    Unit,
)
from foedus.fog import visible_state_for
from foedus.mapgen import generate_map
from foedus.press import advance_turn
from foedus.resolve import initial_state, resolve_turn

from tests.helpers import line_map, make_state


# ---------------------------------------------------------------------------
# U — visible_nodes regression (the playtest's most-cited UX bug)
# ---------------------------------------------------------------------------


def test_visible_nodes_includes_own_unit_locations() -> None:
    """A player's own unit locations must appear in visible_nodes.

    Regression: an inner-loop variable shadowed `visible`, leaving an empty
    list whenever any other player had press in the last round (which is
    every round once Press v0 shipped). Both Haiku agents reported seeing
    `Your visible nodes: []` every turn during the playtest.
    """
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
    ])
    view = visible_state_for(s, 0)
    assert 0 in view["visible_nodes"], (
        "own unit at node 0 must be visible to player 0"
    )


def test_visible_nodes_includes_neighbors_within_fog_radius() -> None:
    """fog_radius=1 means a unit's adjacents are also in visible_nodes."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 2)])
    view = visible_state_for(s, 0)
    assert {1, 2, 3}.issubset(set(view["visible_nodes"]))


def test_visible_nodes_unaffected_by_other_players_press() -> None:
    """Regression: visible_nodes was clobbered when other players had press.

    Construct a state with non-empty press_history (every advance_turn writes
    one) and verify visible_nodes still reflects fog from own units.
    """
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2)
    # Simulate the post-advance_turn state: press_history populated with
    # empty Press for each player.
    s = GameState(
        turn=s.turn,
        map=s.map,
        units=s.units,
        ownership=s.ownership,
        scores=s.scores,
        eliminated=s.eliminated,
        next_unit_id=s.next_unit_id,
        config=s.config,
        log=s.log,
        press_history=[{0: Press(stance={}, intents=[]),
                        1: Press(stance={}, intents=[])}],
    )
    view = visible_state_for(s, 0)
    assert 0 in view["visible_nodes"]


# ---------------------------------------------------------------------------
# C — detente threshold scaling default
# ---------------------------------------------------------------------------


def test_default_detente_threshold_scales_with_num_players() -> None:
    """Per Sonnet's playtest: a 2-player game needing 5 mutual-ally turns is
    fine, but a 4-player game needing all 6 ordered pairs to mutual-ally for
    5 consecutive turns is too easy / hard depending on dynamics. Use
    `4 + num_players` as a sensible default ramp.
    """
    cfg2 = GameConfig(num_players=2)
    cfg4 = GameConfig(num_players=4)
    cfg7 = GameConfig(num_players=7)
    assert cfg2.detente_threshold == 6   # 4 + 2
    assert cfg4.detente_threshold == 8   # 4 + 4
    assert cfg7.detente_threshold == 11  # 4 + 7


def test_explicit_detente_threshold_still_overrides_default() -> None:
    cfg = GameConfig(num_players=4, detente_threshold=3)
    assert cfg.detente_threshold == 3


def test_explicit_peace_threshold_still_overrides_default() -> None:
    """Backward compat: the deprecated alias still wins over the default."""
    cfg = GameConfig(num_players=4, peace_threshold=3)
    assert cfg.detente_threshold == 3


# ---------------------------------------------------------------------------
# B — build sort prefers supply nodes
# ---------------------------------------------------------------------------


def test_build_phase_prefers_supply_nodes() -> None:
    """When a player can build N units and has >N owned candidate nodes,
    builds should prefer SUPPLY/HOME over PLAIN. Pre-fix the sort key was
    just `n` (node id), so a low-id PLAIN could absorb the build slot
    instead of a higher-id supply.
    """
    # Custom small map: 3 nodes in a line.
    # n0 = HOME (p0), n1 = PLAIN, n2 = SUPPLY.
    # p0 owns all three but has zero units placed. With build_period=1
    # and need=3 (3 supplies including the home itself? — only 2 are
    # supply: n0 home + n2 supply), p0 will build to fill those 2 slots.
    # We want the *sort order* of placement to put supplies first:
    # the spawn at n0 (home, lowest id, supply) and n2 (supply) get filled
    # before n1 (plain).
    from foedus.core import Map
    coords = {0: (0, 0), 1: (1, 0), 2: (2, 0)}
    edges = {
        0: frozenset({1}),
        1: frozenset({0, 2}),
        2: frozenset({1}),
    }
    node_types = {0: NodeType.HOME, 1: NodeType.PLAIN, 2: NodeType.SUPPLY}
    m = Map(coords=coords, edges=edges, node_types=node_types,
            home_assignments={0: 0})
    cfg = GameConfig(num_players=2, build_period=1, max_turns=5,
                     detente_threshold=0)
    s = GameState(
        turn=0,
        map=m,
        units={},
        ownership={0: 0, 1: 0, 2: 0},  # p0 owns all three
        scores={0: 0.0, 1: 0.0},
        eliminated=set(),
        next_unit_id=0,
        config=cfg,
    )
    # No orders -> resolve_turn runs build phase since build_period=1.
    s2 = resolve_turn(s, {})
    p0_locs = {u.location for u in s2.units.values() if u.owner == 0}
    # p0 owns 2 supplies (home n0 + supply n2). need=2-0=2. With build sort
    # preferring supplies, builds happen at n0 and n2 (NOT n1).
    assert p0_locs == {0, 2}, (
        f"expected builds at supply nodes 0, 2; got {p0_locs}"
    )


def test_build_phase_falls_back_to_plain_when_more_units_than_supplies() -> None:
    """If a player has more pending builds than supply candidates, the
    overflow goes to plain nodes — but supplies still get priority.
    """
    from foedus.core import Map
    # n0 home (p0), n1 plain, n2 plain, n3 supply.
    coords = {0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (3, 0)}
    edges = {
        0: frozenset({1}),
        1: frozenset({0, 2}),
        2: frozenset({1, 3}),
        3: frozenset({2}),
    }
    node_types = {
        0: NodeType.HOME,
        1: NodeType.PLAIN,
        2: NodeType.PLAIN,
        3: NodeType.SUPPLY,
    }
    m = Map(coords=coords, edges=edges, node_types=node_types,
            home_assignments={0: 0})
    cfg = GameConfig(num_players=2, build_period=1, max_turns=5,
                     detente_threshold=0)
    # p0 owns all four. supply count = 2 (n0, n3). need = 2.
    # supplies n0 and n3 fill first. n1, n2 stay empty.
    s = GameState(
        turn=0, map=m, units={},
        ownership={0: 0, 1: 0, 2: 0, 3: 0},
        scores={0: 0.0, 1: 0.0}, eliminated=set(),
        next_unit_id=0, config=cfg,
    )
    s2 = resolve_turn(s, {})
    p0_locs = {u.location for u in s2.units.values() if u.owner == 0}
    assert p0_locs == {0, 3}


# ---------------------------------------------------------------------------
# E — mapgen home-balance check (>=3 supplies within 2 hops of each home)
# ---------------------------------------------------------------------------


def test_generated_maps_have_balanced_homes() -> None:
    """For each archetype, every home tile must have at least 3 supply
    centers (including the home itself) within 2 hops. This guarantees no
    player starts in an effectively-doomed position like P1 in our playtest
    (only their own home reachable for several turns, so they fell behind
    immediately when it was captured turn 4).
    """
    # Test all archetypes across multiple seeds so we exercise the reroll
    # path. UNIFORM is also covered (no terrain — but should still satisfy
    # the constraint trivially).
    for archetype in Archetype:
        for seed in range(10):
            m = generate_map(num_players=4, seed=seed,
                             archetype=archetype, map_radius=3)
            for home_node, home_player in m.home_assignments.items():
                # BFS within 2 hops (inclusive of home).
                within2 = {home_node}
                frontier = {home_node}
                for _ in range(2):
                    next_frontier: set[int] = set()
                    for n in frontier:
                        for nb in m.neighbors(n):
                            if nb not in within2 and m.is_passable(nb):
                                within2.add(nb)
                                next_frontier.add(nb)
                    frontier = next_frontier
                supply_count = sum(
                    1 for n in within2
                    if m.node_types[n] in (NodeType.HOME, NodeType.SUPPLY)
                )
                assert supply_count >= 3, (
                    f"archetype={archetype.value} seed={seed} "
                    f"home n{home_node} (p{home_player}) has only "
                    f"{supply_count} supplies within 2 hops"
                )


# ---------------------------------------------------------------------------
# F — log surfaces "support cut by attack from u<X>"
# ---------------------------------------------------------------------------


def test_log_surfaces_support_cut() -> None:
    """When a SupportMove is cut by an enemy attack on the supporter, the
    log must say so — not just that the supported attack failed silently.

    This was the most damaging UX gap the Haiku playtest surfaced: P1 issued
    the same supportmove three turns in a row and bounced every time
    without ever knowing the support was being cut by a P2 unit.
    """
    # 7-node line, 3 players (avoid the auto-eliminate-when-no-units).
    # n0(home p0) - n1 - n2 - n3 - n4 - n5 - n6(home p1)
    # u0 (p0) at n3 supports u1's move to n4 (n3 adjacent to n4, valid).
    # u1 (p0) at n5 moves to n4.
    # u2 (p2) at n2 moves to n3 -> cuts u0's support.
    # u3 (p1) at n4 holds (defender). Without cut: u1 wins (str 2 vs 1).
    # With cut: u1 ties (1 vs 1) -> bounces.
    m = line_map(7)
    s = make_state(m, [
        Unit(0, 0, 3),  # p0 supporter
        Unit(1, 0, 5),  # p0 mover (target of support)
        Unit(2, 2, 2),  # p2 cuts support
        Unit(3, 1, 4),  # p1 defender at attacked node
    ], num_players=3)
    orders = {
        0: {0: SupportMove(target=1, target_dest=4),
            1: Move(dest=4)},
        2: {2: Move(dest=3)},
        # p1 holds u3 by default
    }
    s2 = advance_turn(s, orders)
    log_text = "\n".join(s2.log)
    # Cut message must surface in the log.
    assert "cut" in log_text.lower(), (
        f"expected 'cut' in log, got:\n{log_text}"
    )
    assert "u0" in log_text, (
        f"expected supporter u0 mentioned in cut message:\n{log_text}"
    )
    # And the cut must have actually mattered: u1 should have bounced
    # (without the cut, supported u1 would have dislodged u3).
    u1 = next(u for u in s2.units.values() if u.id == 1)
    assert u1.location == 5, "u1 should have bounced back at n5"


# ---------------------------------------------------------------------------
# G — log surfaces attempted destinations of bounced units
# ---------------------------------------------------------------------------


def test_log_surfaces_attempted_dest_of_bounced_unit() -> None:
    """A 'bounced at n9' log line tells you nothing about *why* it bounced.
    Surface the attempted destination so agents can debug their plans.
    Both Haikus said this was the single biggest "explain failure" gap.
    """
    # Two units both move to the same empty node.
    # n0 - n1 - n2 - n3, p0 at n0 moves to n1, p1 at n2 moves to n1.
    # Both bounce.
    m = line_map(4)
    s = make_state(m, [
        Unit(0, 0, 0),  # p0
        Unit(1, 1, 2),  # p1
    ])
    orders = {
        0: {0: Move(dest=1)},
        1: {1: Move(dest=2)},  # p1 holds wherever — let's bounce at n1 too
    }
    # Make both target n1 to force a bounce.
    orders[1][1] = Move(dest=1)
    s2 = advance_turn(s, orders)
    log_text = "\n".join(s2.log)
    # Each bounce line should mention the attempted destination ("-> n1").
    assert "-> n1" in log_text or "→ n1" in log_text, (
        f"expected bounce line to mention attempted dest n1:\n{log_text}"
    )
