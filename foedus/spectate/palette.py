"""Shared colorblind-safe palette for spectator output.

Okabe-Ito, matching scripts/foedus_ruleset_figures.py's inline OI dict (kept
as a second copy rather than importing that script, which is a standalone
matplotlib figure generator with its own optional dependency, not a package
module). Never encode meaning as red-vs-green; every color here is meant to
be backed by a distinct marker/shape/label in the UI, not read alone.
"""

from __future__ import annotations

OKABE_ITO = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "skyblue": "#56B4E9",
    "purple": "#CC79A7",
    "green": "#009E73",
    "vermillion": "#D55E00",
    "yellow": "#F0E442",
    "black": "#000000",
}

# Semantic assignments used across the dashboard/replay UI. Stance colors are
# backed by text labels in the stance matrix / graph legend, never color alone.
STANCE_COLOR = {
    "ally": OKABE_ITO["blue"],
    "neutral": OKABE_ITO["black"],
    "hostile": OKABE_ITO["vermillion"],
}

ENTRANT_COLORS = [
    OKABE_ITO["blue"], OKABE_ITO["orange"], OKABE_ITO["skyblue"],
    OKABE_ITO["purple"], OKABE_ITO["green"], OKABE_ITO["yellow"],
]
