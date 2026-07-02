"""Verify the sim sweep emits harm-typed reputation-breach counters and
exposes CLI flags to override the breach penalties.

Post-2026-07-02 the reputation ledger is HARM-TYPED (Primitive A): a breach
counts only when it harms a committed ally. OpportunisticBetrayer's solo
stabs bounce (strength 1 vs 1) and so no longer register; a Sycophant
(declares Hold + ALLY, then Greedy-moves onto a committed cooperator ally's
supply, capturing it — H1) does reliably harm. Isolating the penalty's score
effect still needs a penalties-off arm, and quantifying "did the deceptive
heuristic actually harm a committed party" needs per-committer breach counts
(state.reputation), not just the recipient-keyed betrayal_count_per_player.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


# seed=15 with this fixed 4-seat matchup reliably produces harm-typed intent
# breaches by seat 0 (Sycophant captures an allied Cooperator's supply) within
# 10 turns on the conflict preset (continental_sweep, map_radius=2), while the
# honest Cooperators — whose only deviations are pro-social Move->Support
# redirects — commit zero harm-typed breaches (verified under the unit-scoped
# harm attribution).
SEATS = "Sycophant,Cooperator,Cooperator,Cooperator"
SEED = "15"


def _run_sweep(out_path: Path, extra_args: list[str]) -> list[dict]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [
            sys.executable, "scripts/foedus_sim_sweep.py",
            "--num-games", "1",
            "--max-turns", "10",
            "--archetype", "continental_sweep",
            "--map-radius", "2",
            "--seats", SEATS,
            "--seed", SEED,
            "--workers", "1",
            "--out", str(out_path),
            *extra_args,
        ],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, \
        f"sweep exited {result.returncode}: stderr={result.stderr}"
    return [json.loads(line) for line in out_path.read_text().strip().splitlines()]


def test_sweep_emits_reputation_breach_counters(tmp_path):
    """Per-player F6 reputation breach counts appear in each JSONL record,
    are non-negative ints, and reflect real breach behavior."""
    records = _run_sweep(tmp_path / "sweep.jsonl", [])
    rec = records[0]
    for field in ("reputation_intent_breaches_per_player",
                  "reputation_pact_breaches_per_player"):
        assert field in rec, f"missing {field}"
        assert len(rec[field]) == 4
        assert all(isinstance(v, int) and v >= 0 for v in rec[field])
    assert rec["reputation_intent_breaches_per_player"][0] > 0, \
        "seed=15 matchup should trigger real breaches by seat 0"
    assert rec["reputation_intent_breaches_per_player"][1:] == [0, 0, 0]
    assert rec["reputation_pact_breaches_per_player"] == [0, 0, 0, 0]


def test_intent_breach_penalty_flag_reduces_breacher_score(tmp_path):
    """--intent-breach-penalty overrides GameConfig.intent_breach_penalty,
    letting a sweep isolate F6's score effect with a penalties-off arm."""
    on = _run_sweep(tmp_path / "on.jsonl", [])[0]
    off = _run_sweep(tmp_path / "off.jsonl",
                     ["--intent-breach-penalty", "0"])[0]
    assert on["reputation_intent_breaches_per_player"][0] > 0
    assert off["final_scores"][0] > on["final_scores"][0], \
        "disabling the intent-breach penalty should raise the breacher's score"
    # Same seed/matchup: only the breacher's score should move.
    assert off["final_scores"][1:] == on["final_scores"][1:]


def test_pact_breach_penalty_flag_accepted(tmp_path):
    """--pact-breach-penalty is accepted and plumbed to GameConfig (no
    heuristic currently proposes pacts, so this is a plumbing check)."""
    records = _run_sweep(tmp_path / "sweep.jsonl",
                         ["--pact-breach-penalty", "0"])
    assert len(records) == 1
