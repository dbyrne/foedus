"""Leader counterweight — a per-turn supply upkeep tax on players controlling
more than `supply_upkeep_free` supplies. Prototyped as a toggle (default off)
to re-test Fable's "mild leader counterweight" WITH retreats enabled.

cost(player) = supply_upkeep * max(0, supplies - supply_upkeep_free), deducted
from that player's score each turn.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import GameConfig, Hold, Unit
from foedus.resolve import resolve_turn

from tests.helpers import line_map, make_state


def test_leader_upkeep_disabled_by_default() -> None:
    assert GameConfig().supply_upkeep == 0.0
    assert GameConfig().supply_upkeep_free == 3


def test_no_tax_when_upkeep_zero() -> None:
    m = line_map(5)  # n0=HOME p0, n1,n2,n3=SUPPLY, n4=HOME p1
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 0, 1), Unit(2, 0, 2),
                       Unit(3, 1, 4)])
    out = resolve_turn(s, {0: {0: Hold(), 1: Hold(), 2: Hold()},
                           1: {3: Hold()}})
    # p0 owns 3 supplies (n0,n1,n2): +3 income, no tax.
    assert out.last_turn_score_delta[0] == 3.0


def test_upkeep_taxes_supplies_above_free_threshold() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 0, 1), Unit(2, 0, 2),
                       Unit(3, 1, 4)])
    s.config = replace(s.config, supply_upkeep=1.0, supply_upkeep_free=1)
    out = resolve_turn(s, {0: {0: Hold(), 1: Hold(), 2: Hold()},
                           1: {3: Hold()}})
    # p0 owns 3 supplies: income 3, upkeep 1.0*(3-1)=2, net +1.
    assert out.last_turn_score_delta[0] == 1.0
    # p1 owns 1 supply (<= free): income 1, no upkeep, net +1.
    assert out.last_turn_score_delta[1] == 1.0


def test_upkeep_scales_with_rate() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 0, 1), Unit(2, 0, 2),
                       Unit(3, 1, 4)])
    s.config = replace(s.config, supply_upkeep=0.5, supply_upkeep_free=1)
    out = resolve_turn(s, {0: {0: Hold(), 1: Hold(), 2: Hold()},
                           1: {3: Hold()}})
    # p0: income 3, upkeep 0.5*(3-1)=1.0, net +2.0.
    assert out.last_turn_score_delta[0] == 2.0
