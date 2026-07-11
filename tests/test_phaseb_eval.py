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


def test_mechanical_vs_strategic_decomposition():
    """The B1 confound decomposition: campaign fallback per arm, base-fallback-
    when-losing, and the clean-parse subset all compute from banked per-game
    parse-fail counts."""
    import foedus_phaseb_analysis as A

    def row(arm, scores, elim, pf, n, seat=0):
        return {"arm": arm, "model_seat": seat, "final_scores": scores,
                "eliminated": elim, "parse_fail_count": pf, "n_decisions": n}

    by_seed = {
        # seed 0: both arms parse cleanly (1/10), identical placement (both last)
        0: {"trained": row("trained", [10, 20, 30, 40], [], 1, 10),
            "base": row("base", [10, 20, 30, 40], [], 1, 10)},
        # seed 1: base is noisy (8/10) and loses the seat (trained 1st, base last)
        1: {"trained": row("trained", [40, 10, 20, 30], [], 1, 10),
            "base": row("base", [5, 10, 20, 30], [], 8, 10)},
    }
    mv = A._mechanical_vs_strategic(by_seed, 2)
    assert mv["campaign_fallback_rate"]["trained"].startswith("2/20")
    assert mv["campaign_fallback_rate"]["base"].startswith("9/20")
    bl = mv["base_fallback_when_losing"]
    assert bl["n_seeds_trained_outplaced_base"] == 1                 # only seed 1
    assert bl["mean_base_fallback_rate_when_losing"] == pytest.approx(0.8)
    # τ=0.20 clean subset includes only seed 0 (base seed1 fbrate 0.8 excluded)
    sub20 = [s for s in mv["clean_parse_subset_sensitivity"]
             if s["clean_threshold_fallback_rate"] == 0.20][0]
    assert sub20["n_pairs_both_clean"] == 1 and sub20["seeds"] == [0]
    assert isinstance(mv["headline"], str) and mv["headline"]


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


# --- G2: constrained mode + seed-disjointness + decision banking -------------

def test_make_model_agent_wraps_client_when_constrained():
    """--constrained wires PhaseConstrainedClient around the OllamaClient (no
    network call: construction only)."""
    import argparse
    import foedus_phaseb_paired_eval as pb
    from foedus.agents.llm.client import OllamaClient
    from foedus.agents.llm.schema import PhaseConstrainedClient

    args = argparse.Namespace(
        trained_model="t", base_model="b", ollama_host=None,
        ollama_timeout=1.0, constrained=True)
    agent = pb._make_model_agent("base", args, None)
    assert isinstance(agent._client, PhaseConstrainedClient)
    assert isinstance(agent._client.inner, OllamaClient)
    assert agent._client.inner.model == "b"

    args.constrained = False
    agent = pb._make_model_agent("trained", args, None)
    assert isinstance(agent._client, OllamaClient)   # unwrapped when OFF
    assert agent._client.model == "t"


def test_assert_seed_disjointness(tmp_path):
    import foedus_phaseb_paired_eval as pb

    m = tmp_path / "corpus_manifest.json"
    m.write_text(json.dumps({"seeds": [111, 222, 333]}))

    rec = pb._assert_seed_disjointness([1, 2, 3], [str(m)])
    assert rec["disjoint"] is True
    assert rec["checked_sources"][0]["n_seeds"] == 3

    with pytest.raises(SystemExit):                       # overlap -> abort
        pb._assert_seed_disjointness([222, 5], [str(m)])

    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"seeds": []}))
    with pytest.raises(SystemExit):                       # empty -> loud fail
        pb._assert_seed_disjointness([1], [str(empty)])


def test_runner_constrained_recorded_and_resume_guarded(tmp_path):
    """--constrained is sealed into the secret + plan, and --resume refuses a
    flipped flag (a resume must not mix constrained + unconstrained games)."""
    import foedus_phaseb_paired_eval as pb

    out = tmp_path / "run"
    base = ["--match-id", "phaseb-g2-flag", "--num-seeds", "2",
            "--out-dir", str(out), "--seed-rng", "7", "--constrained"]
    assert pb.main(base + ["--dry-run"]) == 0
    secret = json.loads((out / "seed_manifest.secret.json").read_text())
    plan = json.loads((out / "phaseb_plan.json").read_text())
    assert secret["constrained"] is True
    assert plan["constrained"] is True

    # resume WITHOUT --constrained -> refused
    with pytest.raises(SystemExit):
        pb.main(["--match-id", "phaseb-g2-flag", "--num-seeds", "2",
                 "--out-dir", str(out), "--resume"])


def test_runner_disjointness_gate_blocks_contaminated_seal(tmp_path):
    """A seal whose drawn seeds intersect a corpus manifest aborts BEFORE any
    plan/game; a disjoint corpus seals fine and records the check in the plan."""
    import foedus_phaseb_paired_eval as pb

    # seed-rng 1 gives a deterministic seed draw; capture it first.
    probe = tmp_path / "probe"
    assert pb.main(["--match-id", "phaseb-g2-dis", "--num-seeds", "2",
                    "--out-dir", str(probe), "--seed-rng", "1",
                    "--dry-run"]) == 0
    drawn = json.loads((probe / "seed_manifest.secret.json").read_text())["seeds"]

    contaminated = tmp_path / "corpus_bad.json"
    contaminated.write_text(json.dumps({"seeds": [drawn[0], 42]}))
    with pytest.raises(SystemExit):
        pb.main(["--match-id", "phaseb-g2-dis", "--num-seeds", "2",
                 "--out-dir", str(tmp_path / "bad"), "--seed-rng", "1",
                 "--assert-disjoint-from", str(contaminated), "--dry-run"])

    clean = tmp_path / "corpus_ok.json"
    clean.write_text(json.dumps({"seeds": [42, 43]}))
    out = tmp_path / "good"
    assert pb.main(["--match-id", "phaseb-g2-dis", "--num-seeds", "2",
                    "--out-dir", str(out), "--seed-rng", "1",
                    "--assert-disjoint-from", str(clean), "--dry-run"]) == 0
    plan = json.loads((out / "phaseb_plan.json").read_text())
    assert plan["seed_disjointness"]["disjoint"] is True
    assert plan["seed_disjointness"]["checked_sources"][0]["n_seeds"] == 2


def test_runner_banks_model_decision_logs(tmp_path):
    """Every (seed, arm) game banks a lean decisions file whose row count
    equals the banked n_decisions — the input for the G2 residual analysis."""
    import foedus_phaseb_paired_eval as pb

    def stub_factory():
        from foedus.agents.llm.client import StubLLMClient
        from foedus.agents.llm.diplomat import LLMDiplomat
        return LLMDiplomat(client=StubLLMClient(["{}"] * 400))

    out = tmp_path / "run"
    rc = pb.main([
        "--match-id", "phaseb-g2-dec", "--num-seeds", "1", "--max-turns", "2",
        "--out-dir", str(out), "--seed-rng", "9",
    ], agent_factory=stub_factory)
    assert rc == 0
    rows = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines()
            if l.strip()]
    for r in rows:
        dec = out / "decisions" / f"decisions_seed{r['seed_index']}_{r['arm']}.jsonl"
        assert dec.exists()
        dec_rows = [json.loads(l) for l in dec.read_text().splitlines() if l.strip()]
        assert len(dec_rows) == r["n_decisions"]
        assert {d["phase"] for d in dec_rows} <= {"negotiate", "orders"}
        assert all("raw_response" in d and "fell_back" in d for d in dec_rows)


def test_residual_analysis_decomposes_and_guards(tmp_path):
    """foedus_g2_residual_analysis: correct per-arm decomposition on a synthetic
    run dir; hard-fails on a decisions/sweep row-count mismatch."""
    import foedus_g2_residual_analysis as ra

    run = tmp_path / "run"
    (run / "decisions").mkdir(parents=True)
    (run / "phaseb_plan.json").write_text(json.dumps(
        {"num_seeds": 1, "constrained": True}))
    (run / "seed_manifest.revealed.json").write_text(json.dumps({"seeds": [77]}))

    valid_orders = '{"orders": {"1": {"type": "Move", "dest": 9}}}'
    invalid_orders = 'not json at all'
    sweep = [
        {"seed_index": 0, "arm": "trained", "n_decisions": 2},
        {"seed_index": 0, "arm": "base", "n_decisions": 2},
    ]
    (run / "sweep.jsonl").write_text(
        "\n".join(json.dumps(r) for r in sweep) + "\n")

    def dec(arm, rows):
        p = run / "decisions" / f"decisions_seed0_{arm}.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    # trained: both schema-valid; one fell back on an illegal order (residual).
    dec("trained", [
        {"phase": "orders", "raw_response": valid_orders,
         "fell_back": False, "n_coerced": 0},
        {"phase": "orders", "raw_response": valid_orders,
         "fell_back": True, "n_coerced": 1},
    ])
    # base: one structural fallback (non-JSON), one clean.
    dec("base", [
        {"phase": "orders", "raw_response": invalid_orders,
         "fell_back": True, "n_coerced": 1},
        {"phase": "orders", "raw_response": valid_orders,
         "fell_back": False, "n_coerced": 0},
    ])

    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps({"seeds": [1, 2, 3]}))
    res = ra.analyze(run, [str(corpus)])

    tr, ba = res["per_arm"]["trained"], res["per_arm"]["base"]
    assert tr["structural_fallback"] == 0
    assert tr["residual_illegal_decisions"] == 1
    assert tr["orders_illegal_coerced"] == 1 and tr["orders_emitted"] == 2
    assert ba["structural_fallback"] == 1
    assert ba["residual_illegal_decisions"] == 0
    assert res["seed_disjointness"]["disjoint"] is True

    # Disjointness violation -> abort.
    bad_corpus = tmp_path / "corpus_bad.json"
    bad_corpus.write_text(json.dumps({"seeds": [77]}))
    with pytest.raises(SystemExit):
        ra.analyze(run, [str(bad_corpus)])

    # Row-count mismatch -> refuse to report.
    dec("base", [{"phase": "orders", "raw_response": valid_orders,
                  "fell_back": False, "n_coerced": 0}])
    with pytest.raises(SystemExit):
        ra.analyze(run, [str(corpus)])
