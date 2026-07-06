"""Smoke test for the campaign resolver-invariant verifier."""

from __future__ import annotations

import json
import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import foedus_verify_invariant as vi  # noqa: E402


def test_verify_holds_on_campaign_boards(tmp_path):
    # a minimal run dir: just the sweep seeds the verifier reads
    out = tmp_path / "run"
    out.mkdir()
    seeds = [38, 284, 351]  # the PR#39 known-bad seeds — the invariant must hold
    with (out / "sweep.jsonl").open("w") as f:
        for i, s in enumerate(seeds):
            f.write(json.dumps({"game_index": i, "seed": s}) + "\n")

    rep = vi.verify(str(out), pairings=3)
    assert rep["invariant_held"] is True
    assert rep["n_seeds"] == 3
    assert rep["total_turn_checks"] > 0
    assert rep["seed_manifest"] is None  # no revealed manifest in this fixture
