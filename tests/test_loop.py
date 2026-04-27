"""Tests for play_game()."""

from __future__ import annotations

import pytest

from agent_game.agents.random_agent import RandomAgent
from agent_game.core import GameConfig
from agent_game.loop import play_game
from agent_game.mapgen import generate_map
from agent_game.resolve import initial_state


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
    cfg = GameConfig(num_players=3, seed=999, max_turns=8, build_period=3)
    a1 = play_game({p: RandomAgent(seed=p) for p in range(3)}, config=cfg)
    a2 = play_game({p: RandomAgent(seed=p) for p in range(3)}, config=cfg)
    assert {u.id: (u.owner, u.location) for u in a1.units.values()} == \
           {u.id: (u.owner, u.location) for u in a2.units.values()}
    assert a1.scores == a2.scores
