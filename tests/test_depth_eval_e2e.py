"""End-to-end smoke test for foedus_depth_eval.py.

Runs a tiny battery (n=5 per probe, 1 probe) and asserts the produced
JSON parses, has the right shape, and the sibling markdown is written.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def test_depth_eval_runs_end_to_end(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    out_json = tmp_path / "depth.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [
            sys.executable, "scripts/foedus_depth_eval.py",
            "--output", str(out_json),
            "--n-tier1", "5",
            "--n-tier2", "5",
            "--probes", "pure_expansion",
            "--max-turns", "5",
            "--workers", "1",
            "--seed", "12345",
        ],
        cwd=repo_root, env=env,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, \
        f"depth-eval failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert out_json.exists()
    data = json.loads(out_json.read_text())
    assert "run_id" in data
    assert "git_sha" in data
    assert "tier1_random_pool" in data
    assert data["tier1_random_pool"]["n_games"] == 5
    assert "rankings" in data["tier1_random_pool"]
    assert "engagement" in data["tier1_random_pool"]
    assert "pairwise_winrate" in data["tier1_random_pool"]
    assert "tier2_probes" in data
    assert len(data["tier2_probes"]) == 1
    assert data["tier2_probes"][0]["name"] == "pure_expansion"
    md = out_json.with_suffix(".md")
    assert md.exists()
    md_text = md.read_text()
    assert "Depth Eval Report" in md_text
    assert "pure_expansion" in md_text
