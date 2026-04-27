"""Tests for the Agent protocol and RandomAgent."""

from __future__ import annotations

from foedus.agents.base import Agent
from foedus.agents.random_agent import RandomAgent
from foedus.core import GameConfig, Unit
from foedus.legal import legal_orders_for_unit
from foedus.mapgen import generate_map
from foedus.resolve import initial_state

from tests.helpers import line_map, make_state


def test_random_agent_implements_protocol() -> None:
    """isinstance check on the Protocol works due to @runtime_checkable."""
    agent = RandomAgent(seed=0)
    assert isinstance(agent, Agent)


def test_random_agent_orders_only_own_units() -> None:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
    ])
    agent = RandomAgent(seed=42)
    orders = agent.choose_orders(s, player=0)
    assert set(orders.keys()) == {0}


def test_random_agent_returns_legal_orders() -> None:
    """Every order produced should be in the legal set for that unit."""
    cfg = GameConfig(num_players=4, seed=42, max_turns=10, build_period=999)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    agent = RandomAgent(seed=0)
    for player in range(4):
        orders = agent.choose_orders(s, player)
        for u_id, order in orders.items():
            assert order in legal_orders_for_unit(s, u_id)


def test_random_agent_reproducible_with_seed() -> None:
    cfg = GameConfig(num_players=4, seed=42, max_turns=10, build_period=999)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    a = RandomAgent(seed=123)
    b = RandomAgent(seed=123)
    assert a.choose_orders(s, 0) == b.choose_orders(s, 0)


def test_random_agent_returns_empty_for_player_with_no_units() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2)
    agent = RandomAgent(seed=0)
    orders = agent.choose_orders(s, player=1)
    assert orders == {}
