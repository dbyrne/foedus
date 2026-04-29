"""Bundle 7 — integration test for the analyzer."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _make_jsonl(tmp_path: Path) -> Path:
    """Create a tiny synthetic JSONL with 5 games."""
    records = []
    for i in range(5):
        records.append({
            "game_id": i,
            "seed": i,
            "agents": ["Greedy", "GreedyHold", "Defensive", "Random"],
            "max_turns_reached": 7,
            "total_turns": 7,
            "is_terminal": True,
            "winners": [1],
            "final_scores": [10.0, 20.0, 5.0, 7.0],
            "supply_counts_per_turn": {
                str(t): [t, t+1, 1, 1] for t in range(1, 8)
            },
            "score_per_turn": {
                str(t): [t * 1.0, t * 2.0, 1.0, 1.0]
                for t in range(1, 8)
            },
            "order_type_counts": {
                "Hold": 10, "Move": 18, "SupportMove": 0, "SupportHold": 0,
            },
            "dislodgement_count": 0,
            "betrayal_count_per_player": [0, 0, 0, 0],
            "detente_reached": False,
            "eliminated": [],
        })
    out = tmp_path / "input.jsonl"
    with out.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return out


def test_analyzer_produces_markdown_report(tmp_path: Path) -> None:
    jsonl = _make_jsonl(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "foedus_sim_analyze.py"),
         str(jsonl)],
        env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, \
        f"analyzer exited {result.returncode}: stderr={result.stderr}"
    out = result.stdout
    # Spot-check sections.
    assert "# Bundle 7 — Sim Sweep Analysis" in out
    assert "Total games analyzed:** 5" in out
    assert "## Per-heuristic final score" in out
    assert "## Pairing win-rate matrix" in out
    assert "## Lead-change frequency" in out
    assert "## Order-type distribution" in out
    assert "## Dislodgement rate" in out
    assert "## Betrayer success vs TitForTat" in out
    # Greedy mean = 10, GreedyHold mean = 20.
    assert "Greedy" in out and "GreedyHold" in out
    # Order-type: roughly 10/(10+18) Hold = 35.7%
    assert "Move:" in out and "Hold:" in out
