"""Tests for multi-LLM-seat support in scripts/foedus_llm_diplomat_run.py --
the slice-2 coordination probe needs to drive several LLMDiplomat seats at
once (e.g. --llm-seats 0,1,2 --heuristics DishonestCooperator: 3 LLM seats
coordinating against a scripted freerider).

The #1 risk of sharing a run across multiple LLM seats is cross-seat
contamination -- seat A's scripted response leaking into seat B's decision
log. `run_one_llm_game` constructs one fresh `llm_agent_factory()` instance
per LLM seat, so contamination would only happen from a wiring bug (wrong
seat -> agent assignment); these tests pin that down with distinct scripted
StubLLMClients per seat and a marker embedded in each seat's raw response.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat

import foedus_llm_diplomat_run as harness


def _marked_stub_factory(seat: int, n_turns: int):
    """A factory whose scripted responses embed a seat-specific marker in
    an unused top-level JSON field -- parsing ignores unknown keys (see
    parse_negotiation_response / parse_orders_response), but the raw
    response text is stored verbatim in decision_log, so the marker
    survives into the log unperturbed. That makes it a strong contamination
    probe: if seat B's log ever contains seat A's marker, wiring is broken.
    """
    def factory():
        responses = [
            json.dumps({
                "press": {"stance": {}, "intents": []},
                "pacts": {"propose": [], "accept": []},
                "_seat_marker": f"SEAT{seat}_ONLY",
            }),
            json.dumps({"orders": {}, "_seat_marker": f"SEAT{seat}_ONLY"}),
        ] * n_turns
        return LLMDiplomat(client=StubLLMClient(responses))
    return factory


def _dispatch_factory(seats: list[int], n_turns: int):
    """`llm_agent_factory` takes no args, so to hand each seat a DIFFERENT
    stub we dispatch by call order. `run_one_llm_game` must construct
    per-seat agents in ascending seat order for this to line up -- that's
    part of what this test pins down.
    """
    factories = {s: _marked_stub_factory(s, n_turns) for s in seats}
    call_order = iter(sorted(seats))

    def factory():
        return factories[next(call_order)]()
    return factory


def test_multi_seat_game_completes_with_per_seat_agents_and_telemetry() -> None:
    seats = [0, 1, 2]
    n_turns = 2
    sweep, telemetry, final_state, agents_by_seat = harness.run_one_llm_game(
        game_id=0, seed=3, llm_seats=seats,
        heuristic_names=["DishonestCooperator"],
        max_turns=n_turns,
        llm_agent_factory=_dispatch_factory(seats, n_turns),
    )

    assert final_state.is_terminal()
    assert isinstance(agents_by_seat, dict)
    assert set(agents_by_seat) == set(seats)

    assert sweep["agents"] == [
        "LLMDiplomat", "LLMDiplomat", "LLMDiplomat", "DishonestCooperator",
    ]
    assert sweep["llm_seats"] == seats
    assert len(sweep["final_scores"]) == 4

    assert telemetry["llm_seats"] == seats
    assert telemetry["n_decisions"] == sum(
        len(agents_by_seat[s].decision_log) for s in seats
    )
    assert telemetry["parse_fail_count"] == 0
    for s in seats:
        assert telemetry["per_seat"][s]["n_decisions"] == len(
            agents_by_seat[s].decision_log
        )
        assert telemetry["per_seat"][s]["parse_fail_count"] == 0


def test_multi_seat_no_cross_seat_contamination() -> None:
    """The core non-contamination proof: each seat's decision log only ever
    contains that seat's own marker, and every record's `player` field
    matches the seat whose agent produced it."""
    seats = [0, 1, 2]
    n_turns = 2
    _sweep, _telemetry, _final, agents_by_seat = harness.run_one_llm_game(
        game_id=1, seed=4, llm_seats=seats,
        heuristic_names=["DishonestCooperator"],
        max_turns=n_turns,
        llm_agent_factory=_dispatch_factory(seats, n_turns),
    )

    for s in seats:
        agent = agents_by_seat[s]
        assert agent.decision_log, f"seat {s} made no decisions"
        for record in agent.decision_log:
            assert record["player"] == s
            raw = record["raw_response"]
            assert f"SEAT{s}_ONLY" in raw
            for other in seats:
                if other != s:
                    assert f"SEAT{other}_ONLY" not in raw


def test_llm_seats_takes_precedence_over_llm_seat_and_single_seat_shape_unchanged() -> None:
    """Back-compat: llm_seats=[N] (single element) must still return the
    historical single-agent shape (not a dict), matching the pre-existing
    llm_seat=N behavior exactly."""
    def factory():
        responses = [
            json.dumps({"press": {"stance": {}, "intents": []},
                        "pacts": {"propose": [], "accept": []}}),
            json.dumps({"orders": {}}),
        ] * 2
        return LLMDiplomat(client=StubLLMClient(responses))

    sweep, telemetry, final_state, agent = harness.run_one_llm_game(
        game_id=0, seed=1, llm_seats=[0],
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=2,
        llm_agent_factory=factory,
    )
    assert not isinstance(agent, dict)
    assert hasattr(agent, "decision_log")
    assert telemetry["llm_seat"] == 0
    assert telemetry["n_decisions"] == len(agent.decision_log)


def test_llm_seats_rejects_duplicate_seats() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        harness.run_one_llm_game(
            game_id=0, seed=1, llm_seats=[0, 0],
            heuristic_names=["GreedyHold", "GreedyHold"],
            max_turns=1,
            llm_agent_factory=lambda: LLMDiplomat(client=StubLLMClient([])),
        )


def test_llm_seats_rejects_out_of_range_seat() -> None:
    with pytest.raises(ValueError, match="out of range"):
        harness.run_one_llm_game(
            game_id=0, seed=1, llm_seats=[0, 5],
            heuristic_names=["GreedyHold"],
            max_turns=1,
            llm_agent_factory=lambda: LLMDiplomat(client=StubLLMClient([])),
        )


# --- CLI-level tests (main()) -----------------------------------------------


def _cli_stub_factory(n_turns: int = 3):
    def factory():
        responses = [
            json.dumps({"press": {"stance": {}, "intents": []},
                        "pacts": {"propose": [], "accept": []}}),
            json.dumps({"orders": {}}),
        ] * n_turns
        return LLMDiplomat(client=StubLLMClient(responses))
    return factory


def test_cli_llm_seats_probe_roster_writes_per_seat_logs_and_telemetry(tmp_path) -> None:
    out_dir = tmp_path / "out"
    rc = harness.main([
        "--num-games", "1", "--max-turns", "2",
        "--llm-seats", "0,1,2",
        "--heuristics", "DishonestCooperator",
        "--out-dir", str(out_dir),
    ], llm_agent_factory=_cli_stub_factory(2))
    assert rc == 0

    sweep = json.loads((out_dir / "sweep.jsonl").read_text().strip())
    assert sweep["agents"] == [
        "LLMDiplomat", "LLMDiplomat", "LLMDiplomat", "DishonestCooperator",
    ]

    telemetry = json.loads((out_dir / "telemetry.jsonl").read_text().strip())
    assert set(str(k) for k in telemetry["per_seat"]) == {"0", "1", "2"}

    seat_files = sorted(out_dir.glob("decisions_game0_seat*.jsonl"))
    assert len(seat_files) == 3
    for f in seat_files:
        records = [json.loads(line) for line in f.read_text().splitlines()]
        assert records


def test_cli_back_compat_single_llm_seat_still_writes_unqualified_decisions_file(tmp_path) -> None:
    out_dir = tmp_path / "out"
    rc = harness.main([
        "--num-games", "1", "--max-turns", "2",
        "--llm-seat", "0",
        "--heuristics", "GreedyHold,GreedyHold,GreedyHold",
        "--out-dir", str(out_dir),
    ], llm_agent_factory=_cli_stub_factory(2))
    assert rc == 0
    assert (out_dir / "decisions_game0.jsonl").exists()
    assert not list(out_dir.glob("decisions_game0_seat*.jsonl"))


def test_cli_heuristics_count_mismatch_errors_clearly(capsys) -> None:
    # 3 llm seats + --num-players 5 => 2 non-LLM seats needed, but 2 names
    # given ("A", "B") -- deliberately NOT a mismatch. Use a real mismatch:
    # 3 names given, but only 2 non-LLM seats needed.
    with pytest.raises(SystemExit):
        harness.main([
            "--num-games", "1", "--max-turns", "1",
            "--llm-seats", "0,1,2",
            "--heuristics", "A,B,C",
            "--num-players", "5",
        ], llm_agent_factory=_cli_stub_factory(1))
    err = capsys.readouterr().err
    assert "non-LLM seat" in err


def test_cli_duplicate_llm_seats_errors_clearly(capsys) -> None:
    with pytest.raises(SystemExit):
        harness.main([
            "--num-games", "1", "--max-turns", "1",
            "--llm-seats", "0,0,1",
            "--heuristics", "GreedyHold",
        ], llm_agent_factory=_cli_stub_factory(1))
    err = capsys.readouterr().err
    assert "duplicate" in err


def test_cli_single_heuristic_fills_all_non_llm_seats(tmp_path) -> None:
    out_dir = tmp_path / "out"
    rc = harness.main([
        "--num-games", "1", "--max-turns", "2",
        "--llm-seats", "0,1",
        "--heuristics", "DishonestCooperator",
        "--num-players", "4",
        "--out-dir", str(out_dir),
    ], llm_agent_factory=_cli_stub_factory(2))
    assert rc == 0
    sweep = json.loads((out_dir / "sweep.jsonl").read_text().strip())
    assert sweep["agents"] == [
        "LLMDiplomat", "LLMDiplomat", "DishonestCooperator", "DishonestCooperator",
    ]
