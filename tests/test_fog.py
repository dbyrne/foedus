"""Fog of war: per-player visible-state filtering."""

from __future__ import annotations

from foedus.core import Unit
from foedus.fog import visible_state_for

from tests.helpers import line_map, make_state


def _visible_unit_ids(view: dict) -> set[int]:
    return {u["id"] for u in view["visible_units"]}


def test_own_units_always_visible() -> None:
    m = line_map(7)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 6),  # far away from other own unit
        Unit(2, 1, 3),  # enemy in the middle (not adjacent to either own unit)
    ])
    view = visible_state_for(s, 0)
    assert {0, 1}.issubset(_visible_unit_ids(view))


def test_distant_enemy_hidden() -> None:
    m = line_map(7)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 6),  # too far for player 0 to see (not adjacent)
    ])
    view = visible_state_for(s, 0)
    assert 1 not in _visible_unit_ids(view)


def test_adjacent_enemy_visible() -> None:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 1),  # adjacent to u0
    ])
    view = visible_state_for(s, 0)
    assert 1 in _visible_unit_ids(view)


def test_fog_radius_2_extends_view() -> None:
    """fog_radius=2 lets you see 2 hops out."""
    m = line_map(7)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 2),  # 2 hops from u0
    ], fog_radius=2)
    view = visible_state_for(s, 0)
    assert 1 in _visible_unit_ids(view)


def test_fog_radius_1_does_not_see_2_hops() -> None:
    m = line_map(7)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 2),  # 2 hops away — should be hidden with fog_radius=1
    ], fog_radius=1)
    view = visible_state_for(s, 0)
    assert 1 not in _visible_unit_ids(view)


def test_ownership_is_public() -> None:
    """Per v1 design, ownership is public to all players."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
    ])
    view = visible_state_for(s, 0)
    # Player 0 sees player 1's home ownership
    assert view["ownership"][4] == 1


def test_player_with_no_units_sees_no_units() -> None:
    """A player with no units has no fog window — visible_units only contains
    units they can see (which is none, since they have no units of their own).
    """
    m = line_map(5)
    s = make_state(m, [Unit(0, 1, 0)], num_players=2)
    view = visible_state_for(s, 0)  # player 0 has no units
    assert _visible_unit_ids(view) == set()
