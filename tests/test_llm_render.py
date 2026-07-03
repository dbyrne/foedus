"""Tests for foedus.agents.llm.render — prompt composition built from
foedus.render_common primitives (no re-implementation of rendering).
"""

from __future__ import annotations

import re

from foedus.core import Intent, Move
from foedus.fog import visible_state_for
from foedus.agents.llm.render import (
    render_negotiation_prompt,
    render_orders_prompt,
)

from tests.helpers import simple_two_player_state

_LABEL_RE = re.compile(r"\d+\$\d+|\d+H\b|\bu\d+\b")


def test_render_negotiation_prompt_contains_map_and_response_format() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    system, user = render_negotiation_prompt(state, view, 0)
    assert "JSON" in system
    assert "press" in user
    assert "pacts" in user
    assert "stance" in user
    assert "RESPONSE FORMAT" in user
    assert "CAPTURE RULE" in user


def test_render_negotiation_prompt_lists_own_units_and_legal_orders() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_negotiation_prompt(state, view, 0)
    own_unit_ids = [u.id for u in state.units.values() if u.owner == 0]
    assert own_unit_ids, "fixture should give player 0 at least one unit"
    for uid in own_unit_ids:
        assert f"u{uid}" in user


def test_render_orders_prompt_contains_legal_orders_and_response_format() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    system, user = render_orders_prompt(state, view, 0, own_intents=[])
    assert "JSON" in system
    assert "RESPONSE FORMAT" in user
    assert "orders" in user
    own_unit_ids = [u.id for u in state.units.values() if u.owner == 0]
    for uid in own_unit_ids:
        assert f"u{uid}" in user


def test_render_orders_prompt_echoes_own_declared_intents() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    own_unit = next(u for u in state.units.values() if u.owner == 0)
    intents = [Intent(unit_id=own_unit.id, declared_order=Move(dest=own_unit.location),
                      visible_to=None)]
    _, user = render_orders_prompt(state, view, 0, own_intents=intents)
    assert "DECLARED INTENTS" in user
    assert "BetrayalObservation" in user


def test_render_orders_prompt_without_intents_omits_intents_section() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_orders_prompt(state, view, 0, own_intents=[])
    assert "DECLARED INTENTS" not in user


def _section(user: str, start_marker: str, end_marker: str) -> str:
    start = user.index(start_marker)
    end = user.index(end_marker, start)
    return user[start:end]


# --- machine-facing sections use bare integer ids (parse-robustness fix) --


def test_render_negotiation_prompt_legal_orders_use_bare_ids() -> None:
    """The legal-orders list under YOUR UNITS is the exact text an LLM
    copies into declared_order JSON -- value-annotated labels here (7$1,
    2H, u5) are invalid JSON tokens and are the root cause of the ~42%
    parse-fail rate. Only the human-readable MAP section may keep them."""
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_negotiation_prompt(state, view, 0)
    section = _section(user, "YOUR UNITS (for declaring intents):",
                        "=== RESPONSE FORMAT ===")
    assert not _LABEL_RE.search(section), section
    # sanity: the map section elsewhere in the same prompt still annotates.
    assert "$" in user or "H" in user


def test_render_orders_prompt_legal_orders_use_bare_ids() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_orders_prompt(state, view, 0, own_intents=[])
    section = _section(user, "YOUR UNITS — choose ONE order per unit:",
                        "=== RESPONSE FORMAT ===")
    assert not _LABEL_RE.search(section), section
    assert "$" in user or "H" in user


def test_render_negotiation_prompt_has_bare_id_instruction() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_negotiation_prompt(state, view, 0)
    assert "bare integer" in user.lower()


def test_render_orders_prompt_has_bare_id_instruction() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_orders_prompt(state, view, 0, own_intents=[])
    assert "bare integer" in user.lower()
