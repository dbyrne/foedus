"""Bootstrap CI helpers for depth eval.

Uses standard nonparametric bootstrap with percentile method.
stdlib only — no scipy/numpy.
"""
from __future__ import annotations
import random


def bootstrap_ci_mean(
    data: list[float],
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float]:
    """Percentile-bootstrap CI for the mean of `data`.

    Returns (lo, hi) at the given confidence level. Returns (0.0, 0.0)
    on empty input.
    """
    if not data:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(data)
    means = []
    for _ in range(n_resamples):
        sample = [data[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    lo_idx = int(alpha * n_resamples)
    hi_idx = int((1.0 - alpha) * n_resamples) - 1
    return (means[lo_idx], means[hi_idx])
