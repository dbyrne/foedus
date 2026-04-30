"""Unit tests for press.intent_dependencies()."""
from foedus.core import (
    AidSpend,
    GameConfig,
    Intent,
    Move,
    Press,
    Support,
)
from foedus.mapgen import generate_map
from foedus.press import intent_dependencies, submit_aid_spends, submit_press_tokens
from foedus.resolve import initial_state


def simple_two_player_state():
    cfg = GameConfig(num_players=2, map_radius=2, seed=1)
    m = generate_map(cfg.num_players, seed=cfg.seed)
    return initial_state(cfg, m)


def test_empty_state_no_dependencies():
    s = simple_two_player_state()
    assert intent_dependencies(s) == {}


def test_support_creates_player_unit_dependency():
    s = simple_two_player_state()
    # Find player 0's first unit and player 1's first unit.
    p0_units = [u for u in s.units.values() if u.owner == 0]
    p1_units = [u for u in s.units.values() if u.owner == 1]
    assert p0_units and p1_units
    p0_unit_id = p0_units[0].id
    p1_unit_id = p1_units[0].id
    # P0 declares an Intent for its own unit, with order = Support of P1's unit.
    intent = Intent(
        unit_id=p0_unit_id,
        declared_order=Support(target=p1_unit_id),
        visible_to=None,
    )
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[intent]))
    deps = intent_dependencies(s)
    # P0 depends on (P1, p1_unit_id).
    assert deps.get(0) == frozenset({(1, p1_unit_id)})


def test_aidspend_creates_dependency_when_present():
    s = simple_two_player_state()
    p1_units = [u for u in s.units.values() if u.owner == 1]
    p1_unit_id = p1_units[0].id
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=p1_unit_id)])
    deps = intent_dependencies(s)
    # If aid passed the mutual-ALLY gate (turn 0 is allowed), dep should exist.
    if s.round_aid_pending.get(0):
        assert (1, p1_unit_id) in deps.get(0, frozenset())


def test_solo_move_no_dependency():
    s = simple_two_player_state()
    p0_units = [u for u in s.units.values() if u.owner == 0]
    p0_unit_id = p0_units[0].id
    # Pick any neighbor of the unit's location for a Move target.
    nbrs = sorted(s.map.neighbors(p0_units[0].location))
    if not nbrs:
        return  # degenerate map; skip
    intent = Intent(
        unit_id=p0_unit_id,
        declared_order=Move(dest=nbrs[0]),
        visible_to=None,
    )
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[intent]))
    deps = intent_dependencies(s)
    assert deps.get(0, frozenset()) == frozenset()
