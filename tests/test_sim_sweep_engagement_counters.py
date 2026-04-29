"""Verify the sim sweep emits the five engagement counter fields."""
import json
import os
import subprocess
import sys
from pathlib import Path


REQUIRED_FIELDS = (
    "aid_spends_count",
    "alliance_bonuses_fired",
    "combat_rewards_fired",
    "supporter_rewards_fired",
    "leverage_bonuses_fired",
    "betrayals_observed",
    "detente_streak_resets",
)


def test_sweep_emits_engagement_counters(tmp_path):
    """Run a tiny sweep and assert every JSONL line has all 5 counters."""
    out = tmp_path / "sweep.jsonl"
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [
            sys.executable, "scripts/foedus_sim_sweep.py",
            "--num-games", "3",
            "--max-turns", "5",
            "--workers", "1",
            "--output", str(out),
            "--seed", "12345",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True, text=True, check=True,
    )
    assert out.exists(), result.stderr
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        rec = json.loads(line)
        for field in REQUIRED_FIELDS:
            assert field in rec, f"missing {field} in record: {rec.keys()}"
            assert isinstance(rec[field], int), \
                f"{field} should be int, got {type(rec[field])}"
            assert rec[field] >= 0, f"{field} should be non-negative"
