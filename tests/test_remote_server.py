"""Tests for the AgentServer FastAPI app, exercised via TestClient."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from foedus import GameConfig, RandomAgent  # noqa: E402
from foedus.core import Hold, Move  # noqa: E402
from foedus.legal import legal_orders_for_unit  # noqa: E402
from foedus.mapgen import generate_map  # noqa: E402
from foedus.remote.server import make_app  # noqa: E402
from foedus.remote.wire import serialize_state  # noqa: E402
from foedus.resolve import initial_state  # noqa: E402


@pytest.fixture
def client():
    agent = RandomAgent(seed=42)
    app = make_app(agent, name="random", version="1.0.0",
                   capabilities=["fog-aware"])
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_info(client: TestClient) -> None:
    r = client.get("/info")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "random"
    assert body["version"] == "1.0.0"
    assert body["capabilities"] == ["fog-aware"]


def test_act_returns_legal_orders(client: TestClient) -> None:
    cfg = GameConfig(num_players=4, seed=42, max_turns=10)
    m = generate_map(4, seed=42)
    state = initial_state(cfg, m)

    r = client.post("/act", json={
        "state": serialize_state(state),
        "player": 0,
    })
    assert r.status_code == 200
    orders = r.json()["orders"]
    # Player 0 has at least one unit; verify each returned order is legal.
    p0_units = [u for u in state.units.values() if u.owner == 0]
    assert p0_units
    for u in p0_units:
        uid_key = str(u.id)
        assert uid_key in orders
        legal = legal_orders_for_unit(state, u.id)
        # Reconstruct the returned Order and check it's in the legal set.
        from foedus.remote.wire import deserialize_order
        chosen = deserialize_order(orders[uid_key])
        assert chosen in legal


def test_act_only_returns_own_units(client: TestClient) -> None:
    cfg = GameConfig(num_players=4, seed=42, max_turns=10)
    m = generate_map(4, seed=42)
    state = initial_state(cfg, m)

    r = client.post("/act", json={
        "state": serialize_state(state),
        "player": 0,
    })
    p0_unit_ids = {str(u.id) for u in state.units.values() if u.owner == 0}
    assert set(r.json()["orders"].keys()) == p0_unit_ids


def test_act_bad_payload_returns_422(client: TestClient) -> None:
    r = client.post("/act", json={"player": 0})  # missing state
    assert r.status_code == 422
