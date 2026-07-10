"""Unit tests for the new pure helpers in the canonical-campaign scorecard.

The core freerider metrics are reused from `foedus.eval.memory_metrics` (already
covered by its own suite); these tests cover only what this analyzer adds: the
timeout-vs-true parse-fail classification, the stance-hostility scalar, and the
first-half/second-half trend helpers.
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

import foedus_canonical_scorecard as sc  # noqa: E402
from foedus.eval._coverage import CoverageError  # noqa: E402


class TestClassifyFellBack:
    def test_not_fell_back_is_none(self):
        assert sc._classify_fell_back({"fell_back": False, "raw_response": "junk"}) is None

    def test_timeout_client_error(self):
        # the exact repr ClaudeCLIClient produces on a subprocess timeout
        rec = {"fell_back": True,
               "raw_response": "<client error: RuntimeError('claude -p timed out after 300.0s')>"}
        assert sc._classify_fell_back(rec) == "timeout"

    def test_other_transport_client_error(self):
        rec = {"fell_back": True,
               "raw_response": "<client error: ConnectionError('refused')>"}
        assert sc._classify_fell_back(rec) == "transport"

    def test_true_parse_failure(self):
        # the model answered, but the answer was unparseable -> genuine parse fail
        rec = {"fell_back": True, "raw_response": "here are my orders: hold everything"}
        assert sc._classify_fell_back(rec) == "parse"


class TestStanceHostility:
    def test_none_when_no_observations(self):
        assert sc._stance_hostility_fraction([]) is None
        assert sc._stance_hostility_fraction(
            [{"turn": 0, "hostile": 0, "neutral": 0, "ally": 0}]) is None

    def test_fraction(self):
        traj = [
            {"turn": 0, "hostile": 1, "neutral": 1, "ally": 0},
            {"turn": 1, "hostile": 2, "neutral": 0, "ally": 0},
        ]
        # 3 hostile of 4 observations
        assert sc._stance_hostility_fraction(traj) == 0.75


class TestTrendHelpers:
    def test_halves_mean_even(self):
        first, second = sc._halves_mean([1.0, 1.0, 3.0, 3.0])
        assert first == 1.0 and second == 3.0

    def test_halves_mean_odd_puts_extra_in_second(self):
        first, second = sc._halves_mean([2.0, 4.0, 6.0])
        assert first == 2.0                      # [:1]
        assert second == 5.0                     # mean(4,6)

    def test_halves_mean_skips_none(self):
        first, second = sc._halves_mean([None, 2.0, None, 4.0])
        assert first == 2.0 and second == 4.0

    def test_halves_mean_all_none(self):
        assert sc._halves_mean([None, None]) == (None, None)

    def test_delta_arrow_direction(self):
        assert "up" in sc._delta_arrow(1.0, 2.0)
        assert "down" in sc._delta_arrow(2.0, 1.0)
        assert "flat" in sc._delta_arrow(2.0, 2.0)


def _write_minimal_out(tmp_path, decisions_g0_s0):
    out = tmp_path / "run"
    out.mkdir()
    (out / "campaign_plan.json").write_text(json.dumps({"freerider_handles": ["Golf"]}))
    sweep_row = {
        "game_id": 0, "seed": 1, "agents": ["Delta", "Echo", "Golf"],
        "llm_seats": [0, 1], "identity_by_seat": ["Delta", "Echo", "Golf"],
        "final_scores": [3.0, 2.0, 1.0], "winners": [0],
    }
    (out / "sweep.jsonl").write_text(json.dumps(sweep_row) + "\n")
    (out / "telemetry.jsonl").write_text("")
    (out / "decisions_game0_seat0.jsonl").write_text(
        "\n".join(json.dumps(r) for r in decisions_g0_s0) + "\n"
        if decisions_g0_s0 else "")
    (out / "decisions_game0_seat1.jsonl").write_text("")
    return out


class TestBuildReportCoverageGuardrail:
    def test_build_report_end_to_end_reproduces_a_healthy_corpus(self, tmp_path):
        decisions = [
            {"turn": 1, "phase": "orders",
             "raw_response": json.dumps({"orders": {}}), "fell_back": False,
             "prompt": {"user": ""}},
        ]
        out = _write_minimal_out(tmp_path, decisions)
        rep = sc.build_report(str(out))
        assert rep["parse_fail_by_identity"]["Delta"] == {
            "decisions": 1, "timeout": 0, "transport": 0, "parse": 0,
        }

    def test_build_report_raises_on_zero_records_read(self, tmp_path):
        out = _write_minimal_out(tmp_path, decisions_g0_s0=[])
        with pytest.raises(CoverageError, match="0 records read"):
            sc.build_report(str(out))
