"""Integration test for scripts/foedus_haiku_probe_report.py's file-reading
glue (M-foedus-haiku-fitness-probe).

The classification rules themselves are unit-tested elsewhere:
tests/test_canonical_scorecard.py (parse-fail split), tests/test_punishment_metrics.py
(support-order + require_dest counting), tests/test_probe_metrics.py (degeneracy
flags + self-notes). This covers only what the script adds: reading a tiny
synthetic 2-game out-dir end-to-end into `build_report`.
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

import foedus_haiku_probe_report as report  # noqa: E402
from foedus.eval._coverage import CoverageError  # noqa: E402


def _negotiate(turn, raw, fell_back=False):
    return {"turn": turn, "phase": "negotiate", "raw_response": raw, "fell_back": fell_back}


def _orders(turn, raw, fell_back=False):
    return {"turn": turn, "phase": "orders", "raw_response": raw, "fell_back": fell_back}


def _write_run(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "campaign_plan.json").write_text(json.dumps({
        "freerider_handles": ["Golf"],
    }))
    sweep_rows = [
        {"game_id": 0, "agents": ["Delta", "Echo", "Foxtrot", "Golf"], "llm_seats": [0, 1, 2]},
        {"game_id": 1, "agents": ["Golf", "Delta", "Echo", "Foxtrot"], "llm_seats": [1, 2, 3]},
    ]
    with (out / "sweep.jsonl").open("w") as f:
        for row in sweep_rows:
            f.write(json.dumps(row) + "\n")

    # game 0, seat 0 (Delta): one bare Support, one require_dest ("pin") Support,
    # a genuine timeout fallback, and an all-Hold turn.
    decisions_g0_s0 = [
        _orders(1, json.dumps({"orders": {"1": {"type": "Support", "target": 2}}})),
        _orders(2, json.dumps({"orders": {
            "1": {"type": "Support", "target": 2, "require_dest": 5}}})),
        _orders(3, json.dumps({"orders": {"1": {"type": "Hold"}}})),
        _orders(4, "<client error: RuntimeError('claude -p timed out after 300.0s')>",
                fell_back=True),
    ]
    (out / "decisions_game0_seat0.jsonl").write_text(
        "\n".join(json.dumps(r) for r in decisions_g0_s0) + "\n")
    (out / "decisions_game0_seat1.jsonl").write_text("")
    (out / "decisions_game0_seat2.jsonl").write_text("")

    # game 1, seat 1 (Delta again, rotated seat): a genuine parse failure.
    decisions_g1_s1 = [
        _orders(1, "not valid json at all", fell_back=True),
    ]
    (out / "decisions_game1_seat1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in decisions_g1_s1) + "\n")
    (out / "decisions_game1_seat2.jsonl").write_text("")
    (out / "decisions_game1_seat3.jsonl").write_text("")

    (out / "campaign_memory_game1_seat1.json").write_text(json.dumps({
        "game_index": 1, "seat": 1, "entrant_identity": "Delta",
        "records": [
            {"facts": {"game_index": 0},
             "self_note": "Golf never pacts, watch actions not words."},
            {"facts": {"game_index": 1},
             "self_note": "Echo coordinated with me twice; trustworthy so far."},
        ],
    }))
    return out


def test_build_report_end_to_end(tmp_path):
    out = _write_run(tmp_path)

    rep = report.build_report(str(out))

    assert rep["n_games"] == 2

    # parse-fail: Delta had 4 decisions in g0 (1 timeout) + 1 decision in g1 (1 parse).
    delta = rep["parse_fail_by_identity"]["Delta"]
    assert delta == {"decisions": 5, "timeout": 1, "transport": 0, "parse": 1}

    # support orders: 1 bare + 1 pin declared by Delta across the corpus.
    delta_supports = rep["support_orders_by_identity"]["Delta"]
    assert delta_supports == {
        "bare": 1, "pin": 1, "total": 2, "orders_phase_decisions": 5,
    }

    # degeneracy: turn 3 was all-Hold for Delta.
    assert rep["degeneracy_by_identity"]["Delta"]["all_hold_turns"] == [3]

    # self-notes: both of Delta's cross-game notes surface, in game order.
    notes = rep["self_notes_by_identity"]["Delta"]
    assert [n["game_index"] for n in notes] == [0, 1]
    assert "trustworthy" in notes[1]["self_note"]

    # coverage: the happy-path fixture's non-fell_back orders records all
    # parse cleanly (100%) -- the guardrail must not false-positive here.
    assert rep["coverage"]["orders_phase_parsed"] == rep["coverage"]["orders_phase_total"]
    assert rep["coverage"]["orders_phase_total"] > 0


class TestCoverageGuardrail:
    """M-foedus-haiku-fitness-probe post-mortem: a report that silently
    parses 0 of its input records must fail loudly, not print a clean
    "zero degeneracy" result. These fixtures exercise the exact failure
    shapes that guardrail exists to catch."""

    def _minimal_out(self, tmp_path, decisions_g0_s0):
        out = tmp_path / "run"
        out.mkdir()
        (out / "campaign_plan.json").write_text(json.dumps({
            "freerider_handles": ["Golf"],
        }))
        sweep_rows = [
            {"game_id": 0, "agents": ["Delta", "Echo", "Foxtrot", "Golf"],
             "llm_seats": [0, 1, 2]},
        ]
        with (out / "sweep.jsonl").open("w") as f:
            for row in sweep_rows:
                f.write(json.dumps(row) + "\n")
        (out / "decisions_game0_seat0.jsonl").write_text(
            "\n".join(json.dumps(r) for r in decisions_g0_s0) + "\n"
            if decisions_g0_s0 else "")
        (out / "decisions_game0_seat1.jsonl").write_text("")
        (out / "decisions_game0_seat2.jsonl").write_text("")
        return out

    def test_zero_records_read_raises(self, tmp_path):
        out = self._minimal_out(tmp_path, decisions_g0_s0=[])
        with pytest.raises(CoverageError, match="0 records read"):
            report.build_report(str(out))

    def test_all_orders_records_unparseable_raises(self, tmp_path):
        # Reproduces the original bug's exact shape: every orders-phase
        # record is one the LIVE harness did NOT flag as a fallback
        # (fell_back=False -- it thought these were fine, matching every
        # real Haiku probe raw_response) but is genuinely unparseable by
        # this report's own re-parsing. If this guardrail had existed
        # before the fence-stripping fix, running the report against the
        # real (fenced) corpus would have hit exactly this and raised
        # immediately instead of printing "zero all-Hold turns."
        decisions = [
            _orders(t, "not json at all, garbage output", fell_back=False)
            for t in range(1, 6)
        ]
        out = self._minimal_out(tmp_path, decisions)
        with pytest.raises(CoverageError, match=r"0 of 5"):
            report.build_report(str(out))

    def test_coverage_just_below_threshold_raises(self, tmp_path):
        # 18/20 = 90% < the 95% default threshold -- a partial regression,
        # not a total parser outage, must still fail loudly rather than
        # silently under-reporting degeneracy for the 2 unreadable turns.
        good = [
            _orders(t, json.dumps({"orders": {"1": {"type": "Hold"}}}), fell_back=False)
            for t in range(1, 19)
        ]
        bad = [
            _orders(t, "not json at all", fell_back=False)
            for t in range(19, 21)
        ]
        out = self._minimal_out(tmp_path, good + bad)
        with pytest.raises(CoverageError, match=r"18/20"):
            report.build_report(str(out))

    def test_coverage_at_threshold_does_not_raise(self, tmp_path):
        # 19/20 = 95% -- exactly at the default threshold, must NOT raise
        # (the guardrail is a floor, not a demand for perfection).
        good = [
            _orders(t, json.dumps({"orders": {"1": {"type": "Hold"}}}), fell_back=False)
            for t in range(1, 20)
        ]
        bad = [_orders(20, "not json at all", fell_back=False)]
        out = self._minimal_out(tmp_path, good + bad)
        report.build_report(str(out))  # must not raise
