"""Tests for foedus.game_server — session logic + HTTP API."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from foedus.game_server.server import make_app  # noqa: E402
from foedus.game_server.session import (  # noqa: E402
    GameSession,
    SeatSpec,
    build_agent,
)


# --- SeatSpec / build_agent ---


def test_seat_spec_validates_type() -> None:
    with pytest.raises(ValueError):
        SeatSpec(type="alien")


def test_seat_spec_agent_requires_kind() -> None:
    with pytest.raises(ValueError):
        SeatSpec(type="agent")


def test_seat_spec_remote_requires_url() -> None:
    with pytest.raises(ValueError):
        SeatSpec(type="remote")


def test_build_agent_imports_known_class() -> None:
    seat = SeatSpec(type="agent", kind="foedus.HeuristicAgent")
    agent = build_agent(seat)
    assert agent is not None
    # Sanity: implements choose_orders.
    assert hasattr(agent, "choose_orders")


def test_build_agent_rejects_bad_path() -> None:
    seat = SeatSpec(type="agent", kind="not.a.real.module.Class")
    with pytest.raises(ValueError):
        build_agent(seat)


def test_build_agent_rejects_unqualified_path() -> None:
    seat = SeatSpec(type="agent", kind="HeuristicAgent")
    with pytest.raises(ValueError):
        build_agent(seat)


# --- HTTP API ---


@pytest.fixture
def client():
    return TestClient(make_app())


def _create_all_agent_game(client: TestClient, num_players: int = 4,
                           seed: int = 42, max_turns: int = 8) -> str:
    r = client.post("/games", json={
        "config": {
            "num_players": num_players,
            "seed": seed,
            "max_turns": max_turns,
            "peace_threshold": 99,
        },
        "seats": [
            {"type": "agent", "kind": "foedus.HeuristicAgent"}
            if i == 0 else
            {"type": "agent", "kind": "foedus.RandomAgent",
             "args": {"seed": i}}
            for i in range(num_players)
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()["game_id"]


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["sessions"] == 0


def test_create_game_rejects_seat_count_mismatch(client: TestClient) -> None:
    r = client.post("/games", json={
        "config": {"num_players": 4, "seed": 1},
        "seats": [{"type": "agent", "kind": "foedus.RandomAgent"}],  # only 1
    })
    assert r.status_code == 400


def test_create_game_returns_view(client: TestClient) -> None:
    r = client.post("/games", json={
        "config": {"num_players": 2, "seed": 1, "max_turns": 5},
        "seats": [
            {"type": "human", "name": "Alice"},
            {"type": "agent", "kind": "foedus.RandomAgent"},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert "game_id" in body
    view = body["view"]
    assert view["you"] == 0
    assert view["turn"] == 0
    assert view["seats"]["0"]["type"] == "human"
    assert view["seats"]["1"]["type"] == "agent"


def test_view_includes_legal_orders(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=4)
    r = client.get(f"/games/{gid}/view/0")
    assert r.status_code == 200
    view = r.json()
    assert view["legal_orders"]
    for orders in view["legal_orders"].values():
        # Hold should always be in the legal-orders list for any unit.
        assert any(o["type"] == "Hold" for o in orders)


def test_advance_runs_full_all_agent_game(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=4, max_turns=6)
    r = client.post(f"/games/{gid}/advance", json={"auto": True})
    assert r.status_code == 200
    body = r.json()
    assert body["advanced"] >= 1
    assert body["is_terminal"]


def test_advance_blocks_on_human(client: TestClient) -> None:
    """With a human seat that hasn't submitted, advance should not progress."""
    r = client.post("/games", json={
        "config": {"num_players": 2, "seed": 1, "max_turns": 5,
                   "peace_threshold": 99},
        "seats": [
            {"type": "human"},
            {"type": "agent", "kind": "foedus.RandomAgent"},
        ],
    })
    gid = r.json()["game_id"]
    r = client.post(f"/games/{gid}/advance", json={"auto": True})
    body = r.json()
    assert body["advanced"] == 0
    assert body["awaiting_humans"] == [0]
    assert body["turn"] == 0


def test_human_orders_unblock_advance(client: TestClient) -> None:
    r = client.post("/games", json={
        "config": {"num_players": 2, "seed": 1, "max_turns": 3,
                   "peace_threshold": 99},
        "seats": [
            {"type": "human"},
            {"type": "agent", "kind": "foedus.RandomAgent"},
        ],
    })
    gid = r.json()["game_id"]
    # Submit hold-everything for player 0.
    view = client.get(f"/games/{gid}/view/0").json()
    holds = {uid: {"type": "Hold"} for uid in view["legal_orders"].keys()}
    r = client.post(f"/games/{gid}/orders",
                    json={"player": 0, "orders": holds})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["ready_to_resolve"] is True
    # Now advance one turn.
    r = client.post(f"/games/{gid}/advance", json={"auto": False})
    body = r.json()
    assert body["advanced"] == 1
    assert body["turn"] == 1


def test_submit_orders_rejects_agent_seat(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=2)
    r = client.post(f"/games/{gid}/orders",
                    json={"player": 0, "orders": {}})
    assert r.status_code == 400


def test_unknown_game_returns_404(client: TestClient) -> None:
    r = client.get("/games/ghost")
    assert r.status_code == 404
    r = client.get("/games/ghost/view/0")
    assert r.status_code == 404
    r = client.post("/games/ghost/advance", json={})
    assert r.status_code == 404


def test_delete_game(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=2)
    r = client.delete(f"/games/{gid}")
    assert r.status_code == 200
    r = client.get(f"/games/{gid}")
    assert r.status_code == 404


def test_list_games(client: TestClient) -> None:
    g1 = _create_all_agent_game(client, num_players=2, seed=1)
    g2 = _create_all_agent_game(client, num_players=2, seed=2)
    r = client.get("/games")
    body = r.json()
    ids = {g["game_id"] for g in body["games"]}
    assert {g1, g2}.issubset(ids)


def test_view_terminal_after_full_game(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=4, max_turns=4)
    client.post(f"/games/{gid}/advance", json={"auto": True})
    view = client.get(f"/games/{gid}/view/0").json()
    assert view["is_terminal"] is True
    # Bundle 2 cadence: with the hold-or-dislodge flip rule, short games on
    # symmetric maps often end in a full score-tie (everyone held home only).
    # A terminal game is valid whether it has a solo winner, a winners list,
    # or a full tie. Just verify the game ended.
    assert "winner" in view and "winners" in view


# --- replay history ---


def test_history_summary_includes_initial_snapshot(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=2, max_turns=5)
    r = client.get(f"/games/{gid}/history")
    assert r.status_code == 200
    body = r.json()
    assert body["current_turn"] == 0
    assert body["snapshots"] == [0]


def test_history_grows_after_each_advance(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=2, max_turns=10)
    # Advance 3 turns one at a time.
    for _ in range(3):
        r = client.post(f"/games/{gid}/advance", json={"auto": False})
        assert r.status_code == 200
    body = client.get(f"/games/{gid}/history").json()
    assert body["current_turn"] == 3
    assert body["snapshots"] == [0, 1, 2, 3]


def test_historical_view_reads_past_state(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=2, max_turns=5)
    client.post(f"/games/{gid}/advance", json={"auto": False})
    client.post(f"/games/{gid}/advance", json={"auto": False})
    # Past view at turn 1 should report turn=1 in the payload.
    r = client.get(f"/games/{gid}/history/1/view/0")
    assert r.status_code == 200
    body = r.json()
    assert body["turn"] == 1
    assert body["is_replay"] is True
    # Replay views never carry legal_orders or awaiting_humans data.
    assert body["legal_orders"] == {}
    assert body["awaiting_humans"] == []
    # Current turn is exposed alongside so clients can detect "live vs past."
    assert body["current_turn"] == 2
    assert body["snapshot_count"] == 3


def test_historical_view_at_zero_returns_initial_state(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=2, max_turns=5)
    client.post(f"/games/{gid}/advance", json={"auto": False})
    r = client.get(f"/games/{gid}/history/0/view/0")
    assert r.status_code == 200
    assert r.json()["turn"] == 0


def test_historical_view_out_of_range_returns_404(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=2, max_turns=5)
    r = client.get(f"/games/{gid}/history/99/view/0")
    assert r.status_code == 404


def test_historical_view_unknown_player_returns_400(client: TestClient) -> None:
    gid = _create_all_agent_game(client, num_players=2, max_turns=5)
    r = client.get(f"/games/{gid}/history/0/view/9")
    assert r.status_code == 400
