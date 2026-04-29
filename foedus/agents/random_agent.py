"""Backward-compat re-export of RandomAgent (Bundle 7).

The implementation lives in foedus.agents.heuristics.random_agent now.
This module re-exports it under its historical import path so existing
callers (including foedus-godot tests that reference the string
"foedus.agents.random_agent.RandomAgent") keep working.
"""

from __future__ import annotations

from foedus.agents.heuristics.random_agent import RandomAgent

__all__ = ["RandomAgent"]
