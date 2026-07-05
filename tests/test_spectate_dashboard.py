"""Tests for foedus/spectate/dashboard.py -- the View 1 campaign dashboard
data model, built entirely from run-dir files (no network, no LLM calls)."""

from __future__ import annotations

import json

from foedus.spectate.dashboard import build_dashboard

PLAN = {
    "match_id": "canonical-v1-2026-07-04",
    "num_games": 2,
    "num_seats": 4,
    "entrant_identities": ["Delta", "Echo", "Foxtrot", "Golf"],
    "freerider_entrants": [3],
    "freerider_handles": ["Golf"],
    "freerider_class": "DishonestCooperator",
    "board": {"num_players": 4, "max_turns": 12, "map_radius": 2,
              "archetype": "continental_sweep", "detente_threshold": 8},
    "seatings": [
        {
            "game_index": 0,
            "identity_by_seat": ["Delta", "Echo", "Foxtrot", "Golf"],
            "llm_seats": [0, 1, 2],
            "freerider_seats": [3],
        },
        {
            "game_index": 1,
            "identity_by_seat": ["Golf", "Delta", "Echo", "Foxtrot"],
            "llm_seats": [1, 2, 3],
            "freerider_seats": [0],
        },
    ],
}

MANIFEST = {"match_id": "canonical-v1-2026-07-04", "commit": "abc123", "seeds": None}


def _write_campaign_fixture(tmp_path, *, n_games_finished=2):
    (tmp_path / "campaign_plan.json").write_text(json.dumps(PLAN))
    (tmp_path / "seed_manifest.sealed.json").write_text(json.dumps(MANIFEST))
    (tmp_path / "timing.log").write_text(
        "CAMPAIGN START: 2026-07-04T10:06:10-04:00\n"
    )
    sweep_records = [
        {"game_id": 0, "game_index": 0, "seed": 1, "agents": ["LLMDiplomat"] * 3 + ["DishonestCooperator"],
         "llm_seats": [0, 1, 2], "freerider_seats": [3],
         "identity_by_seat": ["Delta", "Echo", "Foxtrot", "Golf"],
         "total_turns": 12, "final_scores": [2.0, 3.0, 1.0, 6.0],
         "eliminated": [], "winners": [3], "detente_reached": False},
        {"game_id": 1, "game_index": 1, "seed": 2, "agents": ["DishonestCooperator"] + ["LLMDiplomat"] * 3,
         "llm_seats": [1, 2, 3], "freerider_seats": [0],
         "identity_by_seat": ["Golf", "Delta", "Echo", "Foxtrot"],
         "total_turns": 12, "final_scores": [1.0, 4.0, 4.0, 3.0],
         "eliminated": [], "winners": [1, 2], "detente_reached": False},
    ][:n_games_finished]
    (tmp_path / "sweep.jsonl").write_text(
        "\n".join(json.dumps(r) for r in sweep_records) + ("\n" if sweep_records else "")
    )
    telemetry_records = [
        {"game_id": r["game_id"], "llm_seats": r["llm_seats"], "n_decisions": 6,
         "parse_fail_count": 0, "per_seat": {}}
        for r in sweep_records
    ]
    (tmp_path / "telemetry.jsonl").write_text(
        "\n".join(json.dumps(r) for r in telemetry_records) + ("\n" if telemetry_records else "")
    )
    return sweep_records


def test_build_dashboard_on_fresh_inflight_campaign(tmp_path) -> None:
    """Zero finished games (fresh sealed campaign) must not crash."""
    _write_campaign_fixture(tmp_path, n_games_finished=0)
    dash = build_dashboard(tmp_path)
    assert dash["match_id"] == "canonical-v1-2026-07-04"
    assert dash["entrants"] == ["Delta", "Echo", "Foxtrot", "Golf"]
    assert dash["num_games"] == 2
    assert dash["games_complete"] == 0
    assert dash["games"] == []
    assert dash["started_at"] == "2026-07-04T10:06:10-04:00"
    assert dash["seed_commitment"] == "abc123"


def test_build_dashboard_missing_run_dir_files_returns_sane_defaults(tmp_path) -> None:
    dash = build_dashboard(tmp_path)
    assert dash["match_id"] is None
    assert dash["entrants"] == []
    assert dash["games_complete"] == 0
    assert dash["games"] == []
    assert dash["self_notes"] == []


def test_build_dashboard_per_game_scores_by_handle(tmp_path) -> None:
    _write_campaign_fixture(tmp_path)
    dash = build_dashboard(tmp_path)
    assert dash["games_complete"] == 2
    game0 = dash["games"][0]
    assert game0["by_handle_scores"] == {
        "Delta": 2.0, "Echo": 3.0, "Foxtrot": 1.0, "Golf": 6.0,
    }
    assert game0["winners_handles"] == ["Golf"]
    assert game0["freerider_score"] == 6.0
    assert game0["llm_mean_score"] == 2.0
    assert game0["margin"] == 4.0


def test_build_dashboard_standings_cumulative_scores_and_wins(tmp_path) -> None:
    _write_campaign_fixture(tmp_path)
    dash = build_dashboard(tmp_path)
    standings = dash["standings"]
    assert standings["Golf"]["cumulative_score"] == 7.0  # 6.0 + 1.0
    assert standings["Golf"]["wins"] == 1
    assert standings["Delta"]["cumulative_score"] == 6.0  # 2.0 + 4.0
    assert standings["Echo"]["cumulative_score"] == 7.0  # 3.0 + 4.0
    assert standings["Echo"]["wins"] == 1


def test_build_dashboard_includes_self_notes(tmp_path) -> None:
    _write_campaign_fixture(tmp_path, n_games_finished=0)
    payload = {
        "game_index": 0, "seat": 0, "entrant_identity": "Delta",
        "records": [{"facts": {"game_index": 0}, "self_note": "Golf seems generous."}],
    }
    (tmp_path / "campaign_memory_game0_seat0.json").write_text(json.dumps(payload))
    dash = build_dashboard(tmp_path)
    assert dash["self_notes"] == [{
        "game_index": 0, "seat": 0, "entrant_identity": "Delta",
        "self_note": "Golf seems generous.",
    }]


def test_build_dashboard_subsidy_and_llm_llm_supports_default_zero_without_decisions(tmp_path) -> None:
    """No decision logs on disk (e.g. transcripts/decisions not yet flushed
    for this game) -> subsidy/support counts are 0, not a crash."""
    _write_campaign_fixture(tmp_path)
    dash = build_dashboard(tmp_path)
    for g in dash["games"]:
        assert g["subsidy"] == 0
        assert g["llm_llm_supports"] == 0
