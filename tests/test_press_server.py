"""Bundle 6 — press server endpoint integration tests."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from foedus.game_server.server import make_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app())


def _create_press_game(client: TestClient, num_llm: int = 2,
                       num_agents: int = 2) -> str:
    """Create a game with `num_llm` human (LLM) seats and the rest
    HeuristicAgent. Returns the game_id."""
    n = num_llm + num_agents
    seats = []
    for p in range(num_llm):
        seats.append({"type": "human", "name": f"llm{p}"})
    for p in range(num_agents):
        seats.append({"type": "agent", "name": f"h{p}",
                      "kind": "foedus.agents.heuristic.HeuristicAgent"})
    r = client.post("/games", json={
        "config": {"num_players": n, "max_turns": 7, "seed": 42},
        "seats": seats,
    })
    assert r.status_code == 200, r.text
    return r.json()["game_id"]


def test_chat_endpoint_records_message(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.post(f"/games/{gid}/chat", json={
        "player": 0,
        "draft": {"recipients": None, "body": "hello"},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["chat_phase_complete"] is False  # p1 still pending


def test_chat_endpoint_skip_with_null_draft(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.post(f"/games/{gid}/chat",
                    json={"player": 0, "draft": None})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_chat_endpoint_double_signal_returns_409(client: TestClient) -> None:
    gid = _create_press_game(client)
    client.post(f"/games/{gid}/chat", json={"player": 0, "draft": None})
    r = client.post(f"/games/{gid}/chat",
                    json={"player": 0, "draft": None})
    assert r.status_code == 409


def test_commit_blocked_with_425_until_chat_phase_complete(client: TestClient) -> None:
    gid = _create_press_game(client)
    client.post(f"/games/{gid}/chat", json={"player": 0, "draft": None})
    # P1 hasn't signaled chat-done. Commit must 425.
    r = client.post(f"/games/{gid}/commit", json={
        "player": 0, "press": {}, "orders": {},
    })
    assert r.status_code == 425


def test_commit_advances_round_when_both_llm_committed(client: TestClient) -> None:
    gid = _create_press_game(client)
    for p in (0, 1):
        client.post(f"/games/{gid}/chat",
                    json={"player": p, "draft": None})
    client.post(f"/games/{gid}/commit", json={
        "player": 0, "press": {}, "orders": {},
    })
    r = client.post(f"/games/{gid}/commit", json={
        "player": 1, "press": {}, "orders": {},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["round_advanced"] is True
    assert body["new_turn"] == 1


def test_chat_prompt_endpoint_returns_text(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.get(f"/games/{gid}/chat-prompt/0")
    assert r.status_code == 200
    assert "TURN 1" in r.text
    assert "YOU ARE PLAYER 0" in r.text


def test_commit_prompt_returns_425_before_chat_done(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.get(f"/games/{gid}/commit-prompt/0")
    assert r.status_code == 425


def test_commit_prompt_returns_text_when_chat_complete(client: TestClient) -> None:
    gid = _create_press_game(client)
    for p in (0, 1):
        client.post(f"/games/{gid}/chat",
                    json={"player": p, "draft": None})
    r = client.get(f"/games/{gid}/commit-prompt/0")
    assert r.status_code == 200
    assert "PHASE: COMMIT" in r.text


def test_wait_returns_ready_immediately_when_chat_open(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.get(f"/games/{gid}/wait/0/chat")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["current_phase"] == "chat"


def test_wait_chat_returns_not_ready_when_player_already_done(monkeypatch: pytest.MonkeyPatch) -> None:
    """If P0 already chat_done, /wait/0/chat should NOT return ready —
    chat phase is closed for them. Use a short wait timeout to avoid
    blocking the test."""
    monkeypatch.setenv("FOEDUS_PRESS_WAIT_TIMEOUT", "1")
    client = TestClient(make_app())
    gid = _create_press_game(client)
    client.post(f"/games/{gid}/chat",
                json={"player": 0, "draft": None})
    r = client.get(f"/games/{gid}/wait/0/chat")
    assert r.status_code == 200
    assert r.json()["ready"] is False


def test_full_press_round_via_http(client: TestClient) -> None:
    """End-to-end: 2 LLM seats + 2 agent seats. Walk through one round
    via HTTP. Both LLMs send empty chat + empty commit. Round advances."""
    gid = _create_press_game(client)
    # Chat phase: skip for both LLMs.
    for p in (0, 1):
        r = client.post(f"/games/{gid}/chat",
                        json={"player": p, "draft": None})
        assert r.status_code == 200
    # Commit phase: empty press + empty orders for both LLMs.
    r0 = client.post(f"/games/{gid}/commit", json={
        "player": 0, "press": {}, "orders": {},
    })
    assert r0.status_code == 200
    r1 = client.post(f"/games/{gid}/commit", json={
        "player": 1, "press": {}, "orders": {},
    })
    assert r1.status_code == 200
    body = r1.json()
    assert body["round_advanced"] is True
    assert body["new_turn"] == 1
    # Verify state via existing /games/{gid}/view/0 endpoint.
    view = client.get(f"/games/{gid}/view/0").json()
    assert view["turn"] == 1
