"""Tests for foedus/spectate/readers.py -- read-only loaders over a run-dir's
campaign_plan.json / seed_manifest / sweep.jsonl / telemetry.jsonl /
timing.log / decision logs / campaign-memory self-notes. All tolerant of
missing files (a fresh/in-flight campaign has most of these as empty or
absent) since the run dir is untouchable and may be read mid-flight."""

from __future__ import annotations

import json

from foedus.spectate.readers import (
    load_campaign_plan,
    load_decisions,
    load_self_notes,
    load_sweep,
    load_telemetry,
    load_timing,
)


def test_load_campaign_plan_reads_json(tmp_path) -> None:
    plan = {"match_id": "x", "num_games": 8, "entrant_identities": ["Delta", "Golf"]}
    (tmp_path / "campaign_plan.json").write_text(json.dumps(plan))
    assert load_campaign_plan(tmp_path) == plan


def test_load_campaign_plan_missing_returns_none(tmp_path) -> None:
    assert load_campaign_plan(tmp_path) is None


def test_load_sweep_reads_jsonl_lines(tmp_path) -> None:
    lines = [{"game_id": 0, "final_scores": [1, 2]}, {"game_id": 1, "final_scores": [3, 4]}]
    (tmp_path / "sweep.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    assert load_sweep(tmp_path) == lines


def test_load_sweep_missing_file_returns_empty_list(tmp_path) -> None:
    assert load_sweep(tmp_path) == []


def test_load_sweep_empty_file_returns_empty_list(tmp_path) -> None:
    (tmp_path / "sweep.jsonl").write_text("")
    assert load_sweep(tmp_path) == []


def test_load_telemetry_reads_jsonl_lines(tmp_path) -> None:
    lines = [{"game_id": 0, "n_decisions": 5}]
    (tmp_path / "telemetry.jsonl").write_text(json.dumps(lines[0]) + "\n")
    assert load_telemetry(tmp_path) == lines


def test_load_timing_parses_start_and_end(tmp_path) -> None:
    (tmp_path / "timing.log").write_text(
        "CAMPAIGN START: 2026-07-04T10:06:10-04:00\n"
        "CAMPAIGN END: 2026-07-04T12:30:00-04:00 rc=0 elapsed=8630.0\n"
    )
    timing = load_timing(tmp_path)
    assert timing["started_at"] == "2026-07-04T10:06:10-04:00"
    assert timing["ended_at"] == "2026-07-04T12:30:00-04:00"
    assert timing["rc"] == 0
    assert timing["elapsed_s"] == 8630.0


def test_load_timing_in_flight_has_no_end(tmp_path) -> None:
    (tmp_path / "timing.log").write_text("CAMPAIGN START: 2026-07-04T10:06:10-04:00\n")
    timing = load_timing(tmp_path)
    assert timing["started_at"] == "2026-07-04T10:06:10-04:00"
    assert timing["ended_at"] is None
    assert timing["rc"] is None


def test_load_timing_missing_file(tmp_path) -> None:
    assert load_timing(tmp_path) == {"started_at": None, "ended_at": None, "rc": None, "elapsed_s": None}


def test_load_decisions_multi_seat_naming(tmp_path) -> None:
    rec = {"turn": 1, "phase": "orders", "player": 0}
    (tmp_path / "decisions_game2_seat0.jsonl").write_text(json.dumps(rec) + "\n")
    (tmp_path / "decisions_game2_seat1.jsonl").write_text("")
    by_seat = load_decisions(tmp_path, game_id=2, llm_seats=[0, 1])
    assert by_seat == {0: [rec], 1: []}


def test_load_decisions_single_seat_naming(tmp_path) -> None:
    rec = {"turn": 1, "phase": "orders", "player": 0}
    (tmp_path / "decisions_game7.jsonl").write_text(json.dumps(rec) + "\n")
    by_seat = load_decisions(tmp_path, game_id=7, llm_seats=[0])
    assert by_seat == {0: [rec]}


def test_load_decisions_missing_returns_empty_lists(tmp_path) -> None:
    assert load_decisions(tmp_path, game_id=0, llm_seats=[0, 1]) == {0: [], 1: []}


def test_load_self_notes_extracts_verbatim_notes_newest_first(tmp_path) -> None:
    payload0 = {
        "game_index": 0, "seat": 0, "entrant_identity": "Delta",
        "records": [{"facts": {"game_index": 0}, "self_note": "Golf seems generous."}],
    }
    payload1 = {
        "game_index": 1, "seat": 1, "entrant_identity": "Echo",
        "records": [
            {"facts": {"game_index": 0}, "self_note": "Golf seems generous."},
            {"facts": {"game_index": 1}, "self_note": "Golf betrayed me turn 4."},
        ],
    }
    (tmp_path / "campaign_memory_game0_seat0.json").write_text(json.dumps(payload0))
    (tmp_path / "campaign_memory_game1_seat1.json").write_text(json.dumps(payload1))

    notes = load_self_notes(tmp_path)
    # Newest game_index first; within a game, files/records are stable-sorted.
    assert notes[0] == {
        "game_index": 1, "seat": 1, "entrant_identity": "Echo",
        "self_note": "Golf betrayed me turn 4.",
    }
    assert {"game_index": 0, "seat": 0, "entrant_identity": "Delta",
            "self_note": "Golf seems generous."} in notes


def test_load_self_notes_skips_blank_notes(tmp_path) -> None:
    payload = {
        "game_index": 0, "seat": 0, "entrant_identity": "Delta",
        "records": [{"facts": {"game_index": 0}, "self_note": ""}],
    }
    (tmp_path / "campaign_memory_game0_seat0.json").write_text(json.dumps(payload))
    assert load_self_notes(tmp_path) == []


def test_load_self_notes_no_files_returns_empty_list(tmp_path) -> None:
    assert load_self_notes(tmp_path) == []


def test_load_self_notes_dedupes_across_cumulative_files(tmp_path) -> None:
    """campaign_memory files are cumulative -- the same seat's file at game N
    re-carries every prior game's record. The same (seat, game_index) note
    must appear once, not once per file it shows up in."""
    payload_game0 = {
        "game_index": 0, "seat": 0, "entrant_identity": "Delta",
        "records": [{"facts": {"game_index": 0}, "self_note": "Golf is generous."}],
    }
    payload_game1 = {
        "game_index": 1, "seat": 0, "entrant_identity": "Delta",
        "records": [
            {"facts": {"game_index": 0}, "self_note": "Golf is generous."},
            {"facts": {"game_index": 1}, "self_note": "Golf betrayed me."},
        ],
    }
    (tmp_path / "campaign_memory_game0_seat0.json").write_text(json.dumps(payload_game0))
    (tmp_path / "campaign_memory_game1_seat0.json").write_text(json.dumps(payload_game1))
    notes = load_self_notes(tmp_path)
    assert len(notes) == 2
    assert {n["game_index"] for n in notes} == {0, 1}
