"""Bundle 7 — integration test for the simulation harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_sweep_runs_and_produces_jsonl(tmp_path: Path) -> None:
    """Run the harness with --num-games 10 --max-turns 4 and verify
    the JSONL output structure."""
    out_path = tmp_path / "out.jsonl"
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "foedus_sim_sweep.py"),
         "--num-games", "10",
         "--max-turns", "4",
         "--out", str(out_path)],
        env=env,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, \
        f"sweep exited {result.returncode}: stderr={result.stderr}"
    lines = out_path.read_text().strip().split("\n")
    assert len(lines) == 10
    for line in lines:
        record = json.loads(line)
        # Schema checks.
        for key in ("game_id", "seed", "agents", "total_turns",
                    "is_terminal", "winners", "final_scores",
                    "supply_counts_per_turn", "score_per_turn",
                    "order_type_counts", "dislodgement_count",
                    "betrayal_count_per_player", "detente_reached",
                    "eliminated"):
            assert key in record, f"missing key {key!r}"
        # Logical checks.
        assert len(record["agents"]) == 4
        assert len(record["final_scores"]) == 4
        assert all(s >= 0 for s in record["final_scores"])
        assert record["total_turns"] <= 4
        assert record["is_terminal"] is True
