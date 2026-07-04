"""Integration test for the canonical-campaign orchestrator's non-LLM plumbing.

Exercises `--dry-run` (no games, no LLM calls): the sealed seed manifest and the
per-game rotation plan. The game loop itself is driven by the existing
single-game harness and is validated by the live preflight run, not here.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

pytest.importorskip("foedus.rating", reason="orchestrator import path is fine "
                    "without openskill, but keep parity with the run env")

import foedus_canonical_campaign as orch  # noqa: E402
from foedus.eval import campaign  # noqa: E402
import random  # noqa: E402


def test_dry_run_emits_sealed_manifest_and_plan(tmp_path):
    out = tmp_path / "run"
    rc = orch.main([
        "--match-id", "unit-test-match",
        "--num-games", "8",
        "--seed-rng", "999",
        "--out-dir", str(out),
        "--dry-run",
    ])
    assert rc == 0

    sealed = json.loads((out / "seed_manifest.sealed.json").read_text())
    assert sealed["match_id"] == "unit-test-match"
    assert sealed["num_games"] == 8
    assert len(sealed["commit"]) == 64
    # sealed = commit only (seeds/nonce withheld until reveal)
    assert sealed["seeds"] is None and sealed["nonce"] is None

    # commitment is reproducible from the same CSPRNG seed (bind-the-operator)
    expect_sealed, _, _ = campaign.seal("unit-test-match", 8, rng=random.Random(999))
    assert sealed["commit"] == expect_sealed.commit

    plan = json.loads((out / "campaign_plan.json").read_text())
    assert plan["board"] == {
        "num_players": 4, "max_turns": 12, "map_radius": 2,
        "archetype": "continental_sweep", "detente_threshold": 8,
    }
    assert plan["rotation"] is True
    # freerider (entrant 3) sits in seat (3 + k) % 4 each game
    for g in plan["seatings"]:
        k = g["game_index"]
        assert g["freerider_seats"] == [(3 + k) % 4]
        assert g["identity_by_seat"][(3 + k) % 4] == "DishonestCooperator"


def test_dry_run_no_rotation_pins_freerider(tmp_path):
    out = tmp_path / "run"
    rc = orch.main([
        "--match-id", "unit-test-norot",
        "--num-games", "4",
        "--seed-rng", "7",
        "--out-dir", str(out),
        "--no-rotation",
        "--dry-run",
    ])
    assert rc == 0
    plan = json.loads((out / "campaign_plan.json").read_text())
    assert plan["rotation"] is False
    for g in plan["seatings"]:
        assert g["freerider_seats"] == [3]  # pinned every game
