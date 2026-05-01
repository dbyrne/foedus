"""Tests for the anti-stagnation score penalty."""

from __future__ import annotations

from foedus.core import GameState, Hold, Move, Support, Unit
from foedus.press import _stagnation_cost_deltas

from tests.helpers import line_map, make_state


def _state_for_stagnation(stagnation_cost: float = 1.0) -> GameState:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
    ], num_players=2)
    s.config.stagnation_cost = stagnation_cost
    return s


def test_all_hold_triggers_penalty() -> None:
    s = _state_for_stagnation()
    canon = {0: Hold(), 1: Hold()}
    deltas = _stagnation_cost_deltas(canon, s)
    assert deltas[0] == -1.0
    assert deltas[1] == -1.0


def test_one_move_skips_penalty_for_that_player() -> None:
    s = _state_for_stagnation()
    canon = {0: Move(dest=1), 1: Hold()}
    deltas = _stagnation_cost_deltas(canon, s)
    assert 0 not in deltas
    assert deltas[1] == -1.0


def test_supporthold_only_still_passive() -> None:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 1),
        Unit(2, 1, 4),
    ], num_players=2)
    s.config.stagnation_cost = 1.0
    canon = {0: Support(target=1), 1: Hold(), 2: Hold()}
    deltas = _stagnation_cost_deltas(canon, s)
    assert deltas[0] == -1.0
    assert deltas[1] == -1.0


def test_supportmove_counts_as_active() -> None:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 1),
        Unit(2, 2, 4),
    ], num_players=3)
    s.config.stagnation_cost = 1.0
    canon = {
        0: Move(dest=1),
        1: Support(target=0, require_dest=1),
        2: Hold(),
    }
    deltas = _stagnation_cost_deltas(canon, s)
    assert 0 not in deltas
    assert 1 not in deltas
    assert deltas[2] == -1.0


def test_eliminated_player_exempt() -> None:
    s = _state_for_stagnation()
    s.eliminated.add(0)
    canon = {1: Hold()}
    deltas = _stagnation_cost_deltas(canon, s)
    assert 0 not in deltas
    assert deltas[1] == -1.0


def test_no_units_player_exempt() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2)  # only p0 has a unit
    s.config.stagnation_cost = 1.0
    canon = {0: Hold()}
    deltas = _stagnation_cost_deltas(canon, s)
    assert 1 not in deltas
    assert deltas[0] == -1.0


def test_stagnation_cost_zero_disables() -> None:
    s = _state_for_stagnation(stagnation_cost=0.0)
    canon = {0: Hold(), 1: Hold()}
    deltas = _stagnation_cost_deltas(canon, s)
    assert deltas == {}
