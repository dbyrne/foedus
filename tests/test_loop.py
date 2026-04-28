"""Tests for play_game()."""

from __future__ import annotations

import pytest

from foedus.agents.random_agent import RandomAgent
from foedus.core import GameConfig
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def test_play_game_runs_to_completion() -> None:
    cfg = GameConfig(num_players=4, seed=42, max_turns=10, build_period=3)
    agents = {p: RandomAgent(seed=p) for p in range(4)}
    final = play_game(agents, config=cfg)
    assert final.is_terminal()


def test_play_game_with_explicit_state() -> None:
    cfg = GameConfig(num_players=2, seed=7, max_turns=5, build_period=999)
    m = generate_map(2, seed=7)
    s = initial_state(cfg, m)
    agents = {0: RandomAgent(seed=0), 1: RandomAgent(seed=1)}
    final = play_game(agents, state=s)
    assert final.is_terminal()


def test_play_game_requires_state_or_config() -> None:
    with pytest.raises(ValueError):
        play_game({})


def test_play_game_reproducible_with_seeds() -> None:
    """Reproducibility check. stagnation_cost=0 preserves the v1 behavior the
    test was originally written for: random agents may produce identical
    move-less rounds, so disabling stagnation isolates the assertion to the
    deterministic-engine property the test cares about."""
    cfg = GameConfig(num_players=3, seed=999, max_turns=8, build_period=3,
                     stagnation_cost=0)
    a1 = play_game({p: RandomAgent(seed=p) for p in range(3)}, config=cfg)
    a2 = play_game({p: RandomAgent(seed=p) for p in range(3)}, config=cfg)
    assert {u.id: (u.owner, u.location) for u in a1.units.values()} == \
           {u.id: (u.owner, u.location) for u in a2.units.values()}
    assert a1.scores == a2.scores


def test_play_game_populates_press_and_chat_history() -> None:
    """After play_game, the GameState has press_history / chat_history fields
    that grew per turn (even if empty per round)."""
    cfg = GameConfig(num_players=2, seed=7, max_turns=3, build_period=999)
    agents = {0: RandomAgent(seed=0), 1: RandomAgent(seed=1)}
    final = play_game(agents, config=cfg)
    # 3 turns played, so 3 entries in each history.
    assert len(final.press_history) == 3
    assert len(final.chat_history) == 3


def test_play_game_propagates_archetype_to_mapgen() -> None:
    """Regression: play_game must pass config.archetype to generate_map.

    Without this, the loop silently produces a UNIFORM map regardless of
    the archetype configured. Verifies by running games on different
    archetypes and confirming the maps differ structurally.
    """
    from foedus.core import Archetype, NodeType

    archetypes_with_terrain = [
        (Archetype.HIGHLAND_PASS, NodeType.MOUNTAIN),
        (Archetype.ARCHIPELAGO, NodeType.WATER),
    ]
    for arch, expected_terrain in archetypes_with_terrain:
        cfg = GameConfig(num_players=4, seed=42, max_turns=2,
                         archetype=arch)
        agents = {p: RandomAgent(seed=p) for p in range(4)}
        final = play_game(agents, config=cfg)
        terrain_present = expected_terrain in final.map.node_types.values()
        assert terrain_present, (
            f"play_game(config.archetype={arch}) produced a map with no "
            f"{expected_terrain.value} cells — config not propagated to "
            f"generate_map."
        )


def test_play_game_propagates_map_radius() -> None:
    """Regression: play_game must pass config.map_radius to generate_map."""
    cfg_small = GameConfig(num_players=2, seed=42, max_turns=2, map_radius=2)
    cfg_default = GameConfig(num_players=2, seed=42, max_turns=2)
    agents = {p: RandomAgent(seed=p) for p in range(2)}
    final_small = play_game(agents, config=cfg_small)
    agents = {p: RandomAgent(seed=p) for p in range(2)}
    final_default = play_game(agents, config=cfg_default)
    # A radius=2 map has fewer cells than default radius=3.
    assert len(final_small.map.coords) < len(final_default.map.coords), (
        "play_game ignored config.map_radius — both maps have same size"
    )
