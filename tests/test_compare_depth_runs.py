"""Tests for compare_depth_runs.py."""
import json
import os
import subprocess
import sys
from pathlib import Path


def _write_artifact(path, dislodgements, freerider_diff):
    artifact = {
        "run_id": path.stem,
        "git_sha": "abc",
        "tier1_random_pool": {
            "engagement": {
                "dislodgements_per_game": dislodgements,
                "aid_spends_per_game": 0.0,
            },
            "rankings": [],
            "pairwise_winrate": {"row_agents": [], "col_agents": [], "matrix": []},
        },
        "tier2_probes": [
            {"name": "freerider_canary", "score_diff": freerider_diff,
             "ci95": None, "engagement": {}, "seats": [], "n": 0,
             "subject_index": 0, "description": ""},
        ],
    }
    path.write_text(json.dumps(artifact))


def test_compare_emits_delta_for_changed_metric(tmp_path):
    a = tmp_path / "before.json"
    b = tmp_path / "after.json"
    _write_artifact(a, dislodgements=0.17, freerider_diff=10.7)
    _write_artifact(b, dislodgements=1.88, freerider_diff=5.33)
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, "scripts/compare_depth_runs.py", str(a), str(b)],
        cwd=repo_root, env=env,
        capture_output=True, text=True, check=True,
    )
    assert "dislodgements_per_game" in result.stdout
    assert "freerider_canary" in result.stdout
    assert "+1.71" in result.stdout or "1.71" in result.stdout


def test_compare_unchanged_metrics_omitted_by_default(tmp_path):
    a = tmp_path / "before.json"
    b = tmp_path / "after.json"
    _write_artifact(a, dislodgements=0.17, freerider_diff=10.7)
    _write_artifact(b, dislodgements=0.17, freerider_diff=10.7)
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, "scripts/compare_depth_runs.py", str(a), str(b)],
        cwd=repo_root, env=env,
        capture_output=True, text=True, check=True,
    )
    assert ("no significant" in result.stdout.lower()
            or result.stdout.strip() == "")
