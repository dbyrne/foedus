"""Backward-compat re-export of HeuristicAgent → Greedy (Bundle 7).

The implementation lives in foedus.agents.heuristics.greedy.Greedy now.
This module re-exports it as HeuristicAgent so existing callers
(including foedus-godot tests that reference the string
"foedus.agents.heuristic.HeuristicAgent") keep working.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy import Greedy as HeuristicAgent

__all__ = ["HeuristicAgent"]
