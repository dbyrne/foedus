"""LLM-driven Foedus agents (First Light, slice 1).

`LLMDiplomat` (diplomat.py) plays the full current press schema — stance,
intents, and binding pacts — via a pluggable LLMClient (client.py).
render.py/parse.py compose foedus.render_common into prompts and turn
untrusted model output back into legal engine calls.
"""

from __future__ import annotations

from foedus.agents.llm.diplomat import LLMDiplomat

__all__ = ["LLMDiplomat"]
