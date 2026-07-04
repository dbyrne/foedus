"""Tests for the SFT dataset builder (foedus.train.build_sft).

The builder turns the harness's per-seat decision-log JSONL (the format the
LLM arena harness emits: turn/phase/player/prompt{system,user}/raw_response/
parsed/fell_back/n_coerced) into SFT chat pairs, keeping only *valid teacher
decisions* and deduping identical (prompt, response) pairs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from foedus.train.build_sft import (
    BuildStats,
    build_dataset,
    is_valid_teacher,
    load_winners,
    main,
    parse_game_seat,
    to_chat_example,
)

# --- record factories -------------------------------------------------------

CLEAN_JSON = '{"press": {"stance": {"1": "ally"}}, "orders": []}'


def rec(
    *,
    turn=0,
    phase="negotiate",
    player=0,
    system="SYS",
    user="USR",
    raw_response=CLEAN_JSON,
    fell_back=False,
    n_coerced=0,
):
    return {
        "turn": turn,
        "phase": phase,
        "player": player,
        "prompt": {"system": system, "user": user},
        "raw_response": raw_response,
        "parsed": "SomeDecision(...)",
        "fell_back": fell_back,
        "n_coerced": n_coerced,
    }


def write_decisions(directory: Path, game: int, seat: int, records: list[dict]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"decisions_game{game}_seat{seat}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def write_decisions_unsuffixed(directory: Path, game: int, records: list[dict]) -> Path:
    """Single-seat harness mode: decisions_game{N}.jsonl (no _seat suffix)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"decisions_game{game}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def write_sweep(directory: Path, rows: list[dict]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "sweep.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


# --- is_valid_teacher -------------------------------------------------------


def test_accepts_clean_json_not_fell_back():
    assert is_valid_teacher(rec()) is True


def test_rejects_fell_back_even_if_json_present():
    # fell_back rows are never valid, regardless of raw_response content.
    assert is_valid_teacher(rec(fell_back=True)) is False


def test_rejects_client_error_sentinel():
    sentinel = "<client error: RuntimeError('claude -p timed out after 180.0s')>"
    assert is_valid_teacher(rec(raw_response=sentinel, fell_back=False)) is False


def test_rejects_reasoning_prose_that_is_not_json():
    # Real corpus rows where the model narrated instead of emitting JSON, yet
    # were logged with fell_back=False. The brief requires *real JSON*.
    prose = "Looking at this situation, node 3 is the highest-value supply center..."
    assert is_valid_teacher(rec(raw_response=prose, fell_back=False)) is False


def test_rejects_empty_raw_response():
    assert is_valid_teacher(rec(raw_response="")) is False
    assert is_valid_teacher(rec(raw_response="   ")) is False


def test_accepts_fenced_json_block():
    fenced = "```json\n" + CLEAN_JSON + "\n```"
    assert is_valid_teacher(rec(raw_response=fenced)) is True


def test_rejects_bare_json_scalar():
    # A decision is always a JSON object (or array); a bare scalar that merely
    # happens to parse as JSON is not a valid teacher decision.
    assert is_valid_teacher(rec(raw_response="42")) is False
    assert is_valid_teacher(rec(raw_response='"just a string"')) is False
    assert is_valid_teacher(rec(raw_response="null")) is False


# --- to_chat_example --------------------------------------------------------


def test_chat_example_shape_and_verbatim_assistant():
    ex = to_chat_example(rec(system="S1", user="U1", raw_response=CLEAN_JSON))
    assert list(ex.keys()) == ["messages"]
    roles = [m["role"] for m in ex["messages"]]
    assert roles == ["system", "user", "assistant"]
    assert ex["messages"][0]["content"] == "S1"
    assert ex["messages"][1]["content"] == "U1"
    # assistant target is the teacher's raw_response, verbatim
    assert ex["messages"][2]["content"] == CLEAN_JSON


# --- filename + winners parsing ---------------------------------------------


def test_parse_game_seat_from_filename():
    assert parse_game_seat(Path("runs/x/decisions_game2_seat3.jsonl")) == (2, 3)


def test_parse_game_seat_unsuffixed_single_seat():
    # harness default single-seat mode: no _seat suffix -> seat is None
    assert parse_game_seat(Path("runs/x/decisions_game5.jsonl")) == (5, None)


def test_load_winners_reads_sweep(tmp_path):
    write_sweep(
        tmp_path,
        [
            {"game_id": 0, "winners": [1]},
            {"game_id": 1, "winners": [0, 3]},  # tied-top / détente shared win
        ],
    )
    winners = load_winners(tmp_path)
    assert winners == {0: {1}, 1: {0, 3}}


def test_load_winners_missing_sweep_returns_empty(tmp_path):
    assert load_winners(tmp_path) == {}


# --- build_dataset ----------------------------------------------------------


def test_build_dataset_filters_and_counts(tmp_path):
    sentinel = "<client error: timeout>"
    prose = "Let me think about this..."
    write_decisions(
        tmp_path,
        game=0,
        seat=0,
        records=[
            rec(user="a", raw_response=CLEAN_JSON),            # kept
            rec(user="b", raw_response=CLEAN_JSON, fell_back=True),  # fell_back
            rec(user="c", raw_response=sentinel),              # sentinel -> not_json
            rec(user="d", raw_response=prose),                 # prose -> not_json
        ],
    )
    examples, stats = build_dataset([tmp_path])
    assert isinstance(stats, BuildStats)
    assert stats.records == 4
    assert stats.fell_back == 1
    assert stats.not_json == 2
    assert stats.written == 1
    assert len(examples) == 1
    assert examples[0]["messages"][1]["content"] == "a"


def test_build_dataset_dedups_identical_pairs(tmp_path):
    # Same (system, user, response) three times -> one written, two duplicates.
    records = [rec(user="same", raw_response=CLEAN_JSON) for _ in range(3)]
    write_decisions(tmp_path, game=0, seat=0, records=records)
    examples, stats = build_dataset([tmp_path])
    assert stats.written == 1
    assert stats.duplicates == 2
    assert len(examples) == 1


def test_build_dataset_keeps_distinct_pairs(tmp_path):
    write_decisions(
        tmp_path,
        game=0,
        seat=0,
        records=[
            rec(user="u1", raw_response=CLEAN_JSON),
            rec(user="u2", raw_response=CLEAN_JSON),
        ],
    )
    examples, stats = build_dataset([tmp_path])
    assert stats.written == 2


def test_build_dataset_winners_only(tmp_path):
    # seat 0 lost game 0; seat 1 won. --winners-only keeps only seat 1.
    write_sweep(tmp_path, [{"game_id": 0, "winners": [1]}])
    write_decisions(tmp_path, game=0, seat=0, records=[rec(player=0, user="loser")])
    write_decisions(tmp_path, game=0, seat=1, records=[rec(player=1, user="winner")])

    all_ex, all_stats = build_dataset([tmp_path], winners_only=False)
    assert all_stats.written == 2

    win_ex, win_stats = build_dataset([tmp_path], winners_only=True)
    assert win_stats.written == 1
    assert win_stats.winners_filtered == 1
    assert win_ex[0]["messages"][1]["content"] == "winner"


def test_build_dataset_reads_unsuffixed_single_seat_file(tmp_path):
    # The runner's default single-seat mode writes decisions_game{N}.jsonl.
    # Builder must pick these up, not silently ignore them.
    write_decisions_unsuffixed(
        tmp_path, game=0, records=[rec(user="x"), rec(user="y", raw_response=CLEAN_JSON)]
    )
    examples, stats = build_dataset([tmp_path])
    assert stats.files == 1
    assert stats.written == 2


def test_winners_only_uses_player_field_for_unsuffixed(tmp_path):
    # For unsuffixed single-seat files, winner attribution reads the record's
    # `player` field (the filename carries no seat).
    write_sweep(tmp_path, [{"game_id": 0, "winners": [2]}])
    write_decisions_unsuffixed(
        tmp_path,
        game=0,
        records=[rec(player=2, user="winner"), rec(player=1, user="loser")],
    )
    ex, stats = build_dataset([tmp_path], winners_only=True)
    assert stats.written == 1
    assert stats.winners_filtered == 1
    assert ex[0]["messages"][1]["content"] == "winner"


def test_build_dataset_counts_malformed_prompt(tmp_path):
    # valid JSON raw_response but the record is missing prompt fields
    bad = {
        "turn": 0,
        "phase": "orders",
        "player": 0,
        "raw_response": CLEAN_JSON,
        "fell_back": False,
    }
    write_decisions(tmp_path, 0, 0, [bad])
    _, stats = build_dataset([tmp_path])
    assert stats.malformed_prompt == 1
    assert stats.written == 0


def test_main_warns_loudly_on_empty_dataset(tmp_path, capsys):
    # No decision logs present -> loud warning (not a silent empty file).
    out = tmp_path / "empty.jsonl"
    code = main([str(tmp_path), "--out", str(out)])
    assert code == 0
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert out.read_text() == ""


def test_build_dataset_dedups_across_multiple_dirs(tmp_path):
    d1 = tmp_path / "run1"
    d2 = tmp_path / "run2"
    write_decisions(d1, 0, 0, [rec(user="shared", raw_response=CLEAN_JSON)])
    write_decisions(d2, 0, 0, [rec(user="shared", raw_response=CLEAN_JSON)])
    examples, stats = build_dataset([d1, d2])
    assert stats.files == 2
    assert stats.written == 1
    assert stats.duplicates == 1


# --- CLI --------------------------------------------------------------------


def test_main_writes_jsonl_output(tmp_path):
    from foedus.train.build_sft import main

    write_decisions(tmp_path, 0, 0, [rec(user="x", raw_response=CLEAN_JSON)])
    out = tmp_path / "sft.jsonl"
    code = main([str(tmp_path), "--out", str(out)])
    assert code == 0
    lines = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    assert lines[0]["messages"][2]["content"] == CLEAN_JSON
