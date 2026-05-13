"""Small utility helpers for foedus.web."""
from __future__ import annotations
from datetime import datetime, timezone


def as_utc(dt: datetime | None) -> datetime | None:
    """Normalize a possibly-naive datetime (e.g. as read from sqlite where
    DateTime(timezone=True) drops tzinfo on read) to a timezone-aware
    UTC datetime. Returns None unchanged."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
