"""Shared corpus-read coverage guardrail.

Grew out of a real incident (M-foedus-haiku-fitness-probe): a report script
silently parsed 0 of its 72 real orders-phase records -- every real
`raw_response` is markdown-fenced, the classifier only handled bare JSON --
and printed a clean "zero all-Hold turns" finding instead of failing. An
eval/report tool that reads or parses a fraction of its corpus below a sane
threshold must fail loudly, not produce a plausible-looking result computed
from an empty or near-empty read.
"""

from __future__ import annotations


class CoverageError(RuntimeError):
    """A corpus-read or corpus-parse step covered too little of its input to
    trust the result -- the caller should stop, not report a number."""


def assert_coverage(
    parsed: int, total: int, label: str, min_frac: float = 0.95
) -> None:
    """Raise `CoverageError` unless `parsed` covers at least `min_frac` of
    `total`. `total == 0` and `parsed == 0` (with `total > 0`) are always
    errors regardless of `min_frac` -- there is no threshold low enough to
    make "read/parsed nothing" an acceptable silent result."""
    if total == 0:
        raise CoverageError(f"{label}: 0 records read -- nothing to analyze "
                             "(empty corpus, or a wrong/stale path?)")
    if parsed == 0:
        raise CoverageError(
            f"{label}: 0 of {total} records parsed -- the parser silently "
            "rejected every record (schema drift or a format mismatch?)")
    frac = parsed / total
    if frac < min_frac:
        raise CoverageError(
            f"{label}: only {parsed}/{total} records parsed "
            f"({frac:.1%}, below the {min_frac:.0%} threshold)")
