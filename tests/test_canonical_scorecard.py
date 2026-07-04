"""Unit tests for the new pure helpers in the canonical-campaign scorecard.

The core freerider metrics are reused from `foedus.eval.memory_metrics` (already
covered by its own suite); these tests cover only what this analyzer adds: the
timeout-vs-true parse-fail classification, the stance-hostility scalar, and the
first-half/second-half trend helpers.
"""

from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import foedus_canonical_scorecard as sc  # noqa: E402


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
