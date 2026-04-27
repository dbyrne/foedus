"""Tests for RemoteAgent — the HTTP client implementing the Agent protocol.

Uses fastapi's TestClient (an httpx.Client subclass) so we can exercise the
real wire protocol without a real network listener.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from foedus import GameConfig, RandomAgent, play_game  # noqa: E402
from foedus.agents.base import Agent  # noqa: E402
from foedus.core import Hold  # noqa: E402
from foedus.legal import legal_orders_for_unit  # noqa: E402
from foedus.mapgen import generate_map  # noqa: E402
from foedus.remote.client import RemoteAgent  # noqa: E402
from foedus.remote.server import make_app  # noqa: E402
from foedus.resolve import initial_state  # noqa: E402


def test_remote_agent_implements_protocol() -> None:
    app = make_app(RandomAgent(seed=0))
    test_client = TestClient(app)
    remote = RemoteAgent(client=test_client)
    assert isinstance(remote, Agent)


def test_remote_agent_choose_orders_round_trip() -> None:
    cfg = GameConfig(num_players=4, seed=42, max_turns=10)
    m = generate_map(4, seed=42)
    state = initial_state(cfg, m)

    app = make_app(RandomAgent(seed=42))
    test_client = TestClient(app)
    remote = RemoteAgent(client=test_client)

    orders = remote.choose_orders(state, player=0)
    assert orders, "expected at least one order for player 0"
    for uid, order in orders.items():
        assert order in legal_orders_for_unit(state, uid)


def test_remote_agent_info() -> None:
    app = make_app(RandomAgent(), name="random", version="2.0",
                   capabilities=["fast", "broken"])
    test_client = TestClient(app)
    remote = RemoteAgent(client=test_client)
    info = remote.info()
    assert info["name"] == "random"
    assert info["version"] == "2.0"
    assert "fast" in info["capabilities"]


def test_remote_agent_healthz() -> None:
    app = make_app(RandomAgent())
    test_client = TestClient(app)
    remote = RemoteAgent(client=test_client)
    assert remote.healthz() is True


def test_remote_agent_drives_full_game() -> None:
    """A RemoteAgent can stand in for an in-process agent in play_game."""
    app = make_app(RandomAgent(seed=42))
    test_client = TestClient(app)

    remote = RemoteAgent(client=test_client)
    cfg = GameConfig(num_players=4, seed=42, max_turns=8, peace_threshold=99)
    agents = {
        0: remote,
        1: RandomAgent(seed=1),
        2: RandomAgent(seed=2),
        3: RandomAgent(seed=3),
    }
    final = play_game(agents, config=cfg)
    assert final.is_terminal()
    # Sanity: scores accumulated, no crash.
    assert sum(final.scores.values()) > 0


class _SilentAgent:
    """An in-process agent that holds every unit — useful for deterministic tests."""

    def choose_orders(self, state, player):
        return {u.id: Hold() for u in state.units.values() if u.owner == player}


def test_remote_silent_agent_holds_every_unit() -> None:
    app = make_app(_SilentAgent())
    test_client = TestClient(app)
    remote = RemoteAgent(client=test_client)
    cfg = GameConfig(num_players=2, seed=1, max_turns=3, peace_threshold=99)
    m = generate_map(2, seed=1)
    state = initial_state(cfg, m)
    orders = remote.choose_orders(state, 0)
    for o in orders.values():
        assert isinstance(o, Hold)
