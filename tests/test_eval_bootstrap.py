"""Tests for bootstrap CI helpers."""
import random
import pytest
from foedus.eval.bootstrap import bootstrap_ci_mean


def test_bootstrap_ci_contains_true_mean():
    rng = random.Random(42)
    data = [rng.gauss(10.0, 1.0) for _ in range(500)]
    lo, hi = bootstrap_ci_mean(data, n_resamples=200, seed=0)
    sample_mean = sum(data) / len(data)
    assert lo < sample_mean < hi
    assert hi - lo < 0.5


def test_bootstrap_empty_data_returns_zero_zero():
    assert bootstrap_ci_mean([], n_resamples=50, seed=0) == (0.0, 0.0)


def test_bootstrap_constant_data_returns_constant_ci():
    lo, hi = bootstrap_ci_mean([5.0] * 100, n_resamples=50, seed=0)
    assert lo == pytest.approx(5.0)
    assert hi == pytest.approx(5.0)
