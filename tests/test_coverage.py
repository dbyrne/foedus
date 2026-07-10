"""Tests for foedus.eval._coverage -- the shared corpus-read guardrail
(M-foedus-haiku-fitness-probe, post-mortem on a report that silently parsed
0 of its 72 real orders-phase records and reported "zero degeneracy" as a
clean finding). An eval/report tool that reads or parses a fraction of its
corpus below a sane threshold must fail loudly, not print a plausible-
looking result computed from an empty or near-empty read.
"""

from __future__ import annotations

import pytest

from foedus.eval._coverage import CoverageError, assert_coverage


class TestAssertCoverage:
    def test_zero_total_raises(self):
        with pytest.raises(CoverageError, match="0 records read"):
            assert_coverage(parsed=0, total=0, label="widget parse")

    def test_zero_parsed_of_nonzero_total_raises(self):
        # This is the exact shape of the original bug: every real
        # raw_response was markdown-fenced, _orders_dict only handled bare
        # JSON, so 0 of 72 orders-phase records parsed while the report
        # printed a clean "zero all-Hold turns" instead of failing.
        with pytest.raises(CoverageError, match=r"0 of 72"):
            assert_coverage(parsed=0, total=72, label="widget parse")

    def test_coverage_just_below_threshold_raises(self):
        # 94% < the 95% default threshold.
        with pytest.raises(CoverageError, match="94.0%"):
            assert_coverage(parsed=94, total=100, label="widget parse")

    def test_coverage_at_threshold_does_not_raise(self):
        assert_coverage(parsed=95, total=100, label="widget parse")

    def test_full_coverage_does_not_raise(self):
        assert_coverage(parsed=100, total=100, label="widget parse")

    def test_custom_min_frac_is_honored(self):
        # 80% clears a relaxed 0.5 threshold.
        assert_coverage(parsed=80, total=100, label="widget parse", min_frac=0.5)
        with pytest.raises(CoverageError):
            assert_coverage(parsed=40, total=100, label="widget parse", min_frac=0.5)

    def test_label_appears_in_the_error_message(self):
        with pytest.raises(CoverageError, match="orders-phase degeneracy parse"):
            assert_coverage(parsed=0, total=5, label="orders-phase degeneracy parse")
