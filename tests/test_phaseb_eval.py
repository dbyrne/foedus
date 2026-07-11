"""Unit tests for the G1 Phase B seed-paired eval helpers + runner glue.

Covers the pure pieces (seat planning, board fingerprint, competition ranks,
the paired sign test) and the runner's seed-pairing fairness assertion — all
without any LLM call (a StubLLMClient drives the one end-to-end pairing test).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from foedus.core import Archetype, GameConfig
from foedus.mapgen import generate_map
from foedus.resolve import initial_state
from foedus.eval.phaseb import (
    GOLF_ROLE,
    MODEL_ROLE,
    board_fingerprint,
    competition_ranks,
    plan_paired_seating,
    summary_stats,
    two_sided_sign_test,
)


# --- plan_paired_seating -------------------------------------------------

def test_model_seat_rotates_over_all_positions():
    anchors = ["Cooperator", "TitForTat"]
    seats = [plan_paired_seating(i, freerider_class="DishonestCooperator",
                                 anchor_classes=anchors).model_seat
             for i in range(4)]
    assert seats == [0, 1, 2, 3]  # perfectly rotated, one per position
    # 8 seeds = two full cycles -> balanced
    seats8 = [plan_paired_seating(i, freerider_class="DishonestCooperator",
                                  anchor_classes=anchors).model_seat
              for i in range(8)]
    assert sorted(seats8) == [0, 0, 1, 1, 2, 2, 3, 3]


def test_roles_fill_non_model_seats_in_ascending_order():
    p = plan_paired_seating(0, freerider_class="DishonestCooperator",
                            anchor_classes=["Cooperator", "TitForTat"])
    # MODEL at seat 0; non-model seats [1,2,3] -> Golf, Cooperator, TitForTat
    assert p.model_seat == 0
    assert p.golf_seat == 1
    assert p.anchor_seats == [2, 3]
    assert p.role_by_seat == [MODEL_ROLE, GOLF_ROLE, "Cooperator", "TitForTat"]
    # heuristic_names is what run_one_llm_game consumes for the 3 non-LLM seats
    assert p.heuristic_names == ["DishonestCooperator", "Cooperator", "TitForTat"]


def test_golf_seat_is_lowest_non_model_seat_when_model_moves():
    p = plan_paired_seating(1, freerider_class="DishonestCooperator",
                            anchor_classes=["Cooperator", "TitForTat"])
    assert p.model_seat == 1
    assert p.golf_seat == 0  # lowest non-model index
    assert p.anchor_seats == [2, 3]
    assert p.role_by_seat[1] == MODEL_ROLE
    assert p.role_by_seat[0] == GOLF_ROLE


def test_plan_rejects_inconsistent_num_seats():
    with pytest.raises(ValueError):
        plan_paired_seating(0, freerider_class="DishonestCooperator",
                            anchor_classes=["Cooperator", "TitForTat"],
                            num_seats=5)


# --- board_fingerprint (the pairing-fairness invariant) ------------------

def _initial(seed: int, num_players: int = 4):
    cfg = GameConfig(num_players=num_players, max_turns=12, seed=seed,
                     archetype=Archetype.CONTINENTAL_SWEEP, map_radius=2)
    m = generate_map(num_players, seed=seed, archetype=cfg.archetype,
                     map_radius=cfg.map_radius)
    return initial_state(cfg, m)


def test_board_fingerprint_identical_for_same_seed():
    # Same seed rebuilt twice -> byte-identical board -> identical fingerprint.
    # This is exactly what the two arms of a pair rely on.
    assert board_fingerprint(_initial(12345)) == board_fingerprint(_initial(12345))


def test_board_fingerprint_differs_across_seeds():
    assert board_fingerprint(_initial(1)) != board_fingerprint(_initial(2))


def test_board_fingerprint_stable_string():
    fp = board_fingerprint(_initial(7))
    assert isinstance(fp, str) and len(fp) == 64  # sha256 hex


# --- competition_ranks ---------------------------------------------------

def test_ranks_no_ties_no_elim():
    # seat 2 highest, then 0, then 3, then 1
    assert competition_ranks([10.0, 1.0, 30.0, 5.0], []) == [2, 4, 1, 3]


def test_ranks_with_tie_uses_1224():
    # seats 0 and 1 tie at the top, seat 2 next
    assert competition_ranks([10.0, 10.0, 5.0, 1.0], []) == [1, 1, 3, 4]


def test_ranks_eliminated_share_worst():
    # seat 3 eliminated -> worst rank (= #survivors + 1 = 4); survivors ranked
    ranks = competition_ranks([10.0, 5.0, 20.0, 0.0], [3])
    assert ranks[3] == 4
    assert ranks[2] == 1 and ranks[0] == 2 and ranks[1] == 3


def test_ranks_match_engine_compute_match_result():
    # Cross-check against the engine's own _compute_ranks on a terminal state.
    from foedus.scoring import _compute_ranks
    scores = {0: 7.0, 1: 7.0, 2: 3.0, 3: 0.0}
    survivors = [0, 1, 2]
    engine = _compute_ranks(scores, survivors, 4)  # seat 3 eliminated
    mine = competition_ranks([7.0, 7.0, 3.0, 0.0], [3])
    assert mine == [engine[p] for p in range(4)]


# --- two_sided_sign_test -------------------------------------------------

def test_sign_test_all_positive():
    r = two_sided_sign_test([1.0, 2.0, 0.5, 3.0])
    assert r.n_positive == 4 and r.n_negative == 0 and r.n_zero == 0
    # 2 * 0.5^4 = 0.125
    assert r.p_value == pytest.approx(0.125)


def test_sign_test_drops_ties():
    r = two_sided_sign_test([1.0, 0.0, 2.0, 0.0, 3.0])
    assert r.n_pairs == 5 and r.n_zero == 2 and r.n_nonzero == 3
    assert r.n_positive == 3 and r.n_negative == 0
    assert r.p_value == pytest.approx(2 * 0.5 ** 3)


def test_sign_test_even_split_is_one():
    r = two_sided_sign_test([1.0, -1.0, 2.0, -2.0])
    assert r.n_positive == 2 and r.n_negative == 2
    assert r.p_value == pytest.approx(1.0)


def test_sign_test_all_zero():
    r = two_sided_sign_test([0.0, 0.0])
    assert r.n_nonzero == 0 and r.p_value == 1.0


def test_summary_stats_empty_and_nonempty():
    assert summary_stats([]) == {"n": 0, "mean": None, "min": None, "max": None}
    s = summary_stats([2.0, 4.0])
    assert s["n"] == 2 and s["mean"] == 3.0 and s["min"] == 2.0 and s["max"] == 4.0


# --- end-to-end pairing fairness via the runner (StubLLMClient, no network) --

def test_runner_pair_is_byte_identical_board(tmp_path):
    """Run ONE seed's pair (trained + base arms) with a scripted StubLLMClient
    for BOTH arms and assert the runner recorded an identical board fingerprint
    for the two arms — the load-bearing seed-pairing fairness invariant, proven
    without any LLM/network call."""
    import foedus_phaseb_paired_eval as pb

    # A stub that always Holds / stays neutral: enough scripted lines for a
    # full 3-turn game's negotiate+orders calls on the single MODEL seat.
    def stub_factory():
        from foedus.agents.llm.client import StubLLMClient
        from foedus.agents.llm.diplomat import LLMDiplomat
        return LLMDiplomat(client=StubLLMClient(["{}"] * 400))

    rc = pb.main([
        "--match-id", "phaseb-unit-test",
        "--num-seeds", "1",
        "--max-turns", "3",
        "--out-dir", str(tmp_path / "run"),
        "--seed-rng", "42",
    ], agent_factory=stub_factory)
    assert rc == 0

    rows = [json.loads(l) for l in (tmp_path / "run" / "sweep.jsonl").read_text().splitlines() if l.strip()]
    assert len(rows) == 2  # one pair = two arms
    by_arm = {r["arm"]: r for r in rows}
    assert set(by_arm) == {"trained", "base"}
    # Same seed -> identical board fingerprint + identical seat layout.
    assert by_arm["trained"]["board_fingerprint"] == by_arm["base"]["board_fingerprint"]
    assert by_arm["trained"]["role_by_seat"] == by_arm["base"]["role_by_seat"]
    assert by_arm["trained"]["agents"] == by_arm["base"]["agents"]
    assert by_arm["trained"]["model_seat"] == by_arm["base"]["model_seat"]


def test_runner_dry_run_seals_without_games(tmp_path):
    """--dry-run publishes the sealed commitment + plan + secret and runs NO
    game (no agent factory invoked)."""
    import foedus_phaseb_paired_eval as pb

    out = tmp_path / "run"
    rc = pb.main([
        "--match-id", "phaseb-seal-test",
        "--num-seeds", "8",
        "--out-dir", str(out),
        "--seed-rng", "1",
        "--dry-run",
    ])
    assert rc == 0
    sealed = json.loads((out / "seed_manifest.sealed.json").read_text())
    assert sealed["commit"] and sealed["seeds"] is None  # committed hash, seeds hidden
    secret = json.loads((out / "seed_manifest.secret.json").read_text())
    assert len(secret["seeds"]) == 8
    plan = json.loads((out / "phaseb_plan.json").read_text())
    assert plan["num_seeds"] == 8 and len(plan["seatings"]) == 8
    assert not (out / "sweep.jsonl").exists()  # no games ran


def test_runner_refuses_to_reseal_existing_commitment(tmp_path):
    """Once sealed, a non-resume call (even --dry-run) refuses to overwrite the
    committed seeds — protects the published commitment."""
    import foedus_phaseb_paired_eval as pb
    out = tmp_path / "run"
    base = ["--match-id", "phaseb-reseal", "--num-seeds", "4",
            "--out-dir", str(out), "--seed-rng", "3"]
    assert pb.main(base + ["--dry-run"]) == 0
    with pytest.raises(SystemExit):
        pb.main(base + ["--dry-run"])          # second seal attempt -> refused
    with pytest.raises(SystemExit):
        pb.main(base)                           # fresh (non-resume) run -> refused


def test_runner_resume_from_fresh_seal_runs_all(tmp_path):
    """--resume right after a seal (no sweep.jsonl yet) starts from 0 banked and
    completes every pair, then reveals + verifies."""
    import foedus_phaseb_paired_eval as pb

    def stub_factory():
        from foedus.agents.llm.client import StubLLMClient
        from foedus.agents.llm.diplomat import LLMDiplomat
        return LLMDiplomat(client=StubLLMClient(["{}"] * 400))

    out = tmp_path / "run"
    base = ["--match-id", "phaseb-resume", "--num-seeds", "2", "--max-turns", "2",
            "--out-dir", str(out), "--seed-rng", "5"]
    assert pb.main(base + ["--dry-run"]) == 0
    assert not (out / "sweep.jsonl").exists()
    assert pb.main(base + ["--resume"], agent_factory=stub_factory) == 0
    rows = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines() if l.strip()]
    assert len(rows) == 4  # 2 seeds * 2 arms
    revealed = json.loads((out / "seed_manifest.revealed.json").read_text())
    assert revealed["seeds"] is not None and len(revealed["seeds"]) == 2
