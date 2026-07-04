"""Tests for foedus/spectate/server.py's route handlers -- called directly
against a fixture run-dir, no real sockets (no network flakiness)."""

from __future__ import annotations

import json

from foedus.spectate.server import route

SWEEP_RECORD = {
    "game_id": 0, "game_index": 0, "seed": 1,
    "agents": ["LLMDiplomat"] * 3 + ["DishonestCooperator"],
    "llm_seats": [0, 1, 2], "freerider_seats": [3],
    "identity_by_seat": ["Delta", "Echo", "Foxtrot", "Golf"],
    "total_turns": 1, "final_scores": [2.0, 3.0, 1.0, 6.0],
    "eliminated": [], "winners": [3], "detente_reached": False,
}

TRANSCRIPT = """\
# Foedus LLM Diplomat transcript — LLM seats 0, 1, 2

Final scores: {0: 2.0, 1: 3.0, 2: 1.0, 3: 6.0}
Eliminated: []
Winners: [3]
Détente reached: False

## Turn 1
- p0 stance: p3=hostile
- p1 stance: (none)
- p2 stance: (none)
- p3 stance: (none)

## Betrayals observed
(none)

## Pact breaches observed
(none)

## Final reputation (public)
- p0: 0 intent / 0 pact / 0 total
"""


def _fixture_run_dir(tmp_path):
    (tmp_path / "campaign_plan.json").write_text(json.dumps({
        "match_id": "test-match", "num_games": 1,
        "entrant_identities": ["Delta", "Echo", "Foxtrot", "Golf"],
        "freerider_handles": ["Golf"],
        "board": {"max_turns": 12, "map_radius": 2, "detente_threshold": 8},
        "seatings": [{"game_index": 0, "identity_by_seat": SWEEP_RECORD["identity_by_seat"],
                      "llm_seats": [0, 1, 2], "freerider_seats": [3]}],
    }))
    (tmp_path / "sweep.jsonl").write_text(json.dumps(SWEEP_RECORD) + "\n")
    (tmp_path / "transcript_game0.md").write_text(TRANSCRIPT)
    return tmp_path


def test_route_dashboard_page_returns_html(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "GET", "/")
    assert status == 200
    assert "text/html" in content_type
    assert b"<title>" in body


def test_route_replay_page_returns_html(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "GET", "/replay")
    assert status == 200
    assert "text/html" in content_type


def test_route_api_dashboard_returns_valid_json(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "GET", "/api/dashboard")
    assert status == 200
    assert content_type == "application/json"
    data = json.loads(body)
    assert data["match_id"] == "test-match"
    assert data["games_complete"] == 1
    assert "inflight_claude_calls" in data


def test_route_api_games_lists_finished_games(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "GET", "/api/games")
    assert status == 200
    data = json.loads(body)
    assert data == [{"game_id": 0, "game_index": 0}]


def test_route_api_replay_returns_game_data(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "GET", "/api/replay/0")
    assert status == 200
    data = json.loads(body)
    assert data["identity_by_seat"] == ["Delta", "Echo", "Foxtrot", "Golf"]


def test_route_api_replay_missing_game_returns_404(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "GET", "/api/replay/999")
    assert status == 404


def test_route_api_replay_non_integer_id_returns_400(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "GET", "/api/replay/not-a-number")
    assert status == 400


def test_route_unknown_path_returns_404(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "GET", "/nope")
    assert status == 404


def test_route_non_get_method_returns_405(tmp_path) -> None:
    status, content_type, body = route(_fixture_run_dir(tmp_path), "POST", "/")
    assert status == 405


def test_route_dashboard_on_fresh_campaign_no_files(tmp_path) -> None:
    """An empty run dir (freshest possible campaign state) must not crash
    any route."""
    status, content_type, body = route(tmp_path, "GET", "/api/dashboard")
    assert status == 200
    data = json.loads(body)
    assert data["games_complete"] == 0

    status, _, body = route(tmp_path, "GET", "/api/games")
    assert status == 200
    assert json.loads(body) == []
