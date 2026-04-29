"""Smoke test for the JSON-to-Markdown depth report renderer."""
from foedus.eval.render import render_markdown


def _fake_artifact():
    return {
        "run_id": "test-run",
        "git_sha": "deadbeef",
        "git_branch": "main",
        "timestamp": "2026-04-29T12:00:00Z",
        "config": {"max_turns": 15, "players": 4},
        "stat_rigor": "point",
        "tier1_random_pool": {
            "n_games": 100,
            "seed": 42,
            "rankings": [
                {"agent": "GreedyHold", "mean_score": 60.0,
                 "ci95": None, "n_appearances": 50},
                {"agent": "Cooperator", "mean_score": 55.0,
                 "ci95": None, "n_appearances": 47},
            ],
            "pairwise_winrate": {
                "row_agents": ["GreedyHold", "Cooperator"],
                "col_agents": ["GreedyHold", "Cooperator"],
                "matrix": [[None, 0.55], [0.45, None]],
            },
            "engagement": {
                "dislodgements_per_game": 0.2,
                "aid_spends_per_game": 0.0,
            },
        },
        "tier2_probes": [
            {
                "name": "freerider_canary",
                "seats": ["DC", "C", "C", "C"],
                "n": 50,
                "score_diff": 5.5,
                "ci95": None,
                "engagement": {"dislodgements_per_game": 0.1},
            }
        ],
        "tier3_knob_sweep": None,
    }


def test_render_includes_run_id_and_sections():
    md = render_markdown(_fake_artifact())
    assert "test-run" in md
    assert "deadbeef" in md
    assert "## Tier 1" in md
    assert "GreedyHold" in md
    assert "60.0" in md
    assert "## Tier 2" in md
    assert "freerider_canary" in md


def test_render_handles_missing_ci():
    md = render_markdown(_fake_artifact())
    assert "GreedyHold" in md
