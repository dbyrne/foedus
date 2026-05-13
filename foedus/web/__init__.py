"""Async web-play MVP — FastAPI + sqlite over the foedus engine.

Optional dependency. Install with:
    pip install foedus[web]
"""
from __future__ import annotations

from foedus.web.app import make_web_app

__all__ = ["make_web_app"]
