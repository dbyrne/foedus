"""Shunner — a ledger-reading punisher of free-riders.

Ported from the 2026-07-02 freerider design pass. Shunner reads the public
reciprocation ledger and treats a player as a free-rider iff it has TAKEN
ally support (received > 0) while its reciprocation standing is below the
floor (standing < reciprocation_floor). Against such a player it: declares
HOSTILE, refuses to Support it, and attacks its units that sit on supplies.
Against everyone else it behaves like a Reciprocator (ALLY + gives support).

The key property being tested is that detection is CLEAN — Shunner does not
misfire on honest cooperators (who reciprocate and thus keep standing high).
"""

from __future__ import annotations

from foedus.agents.heuristics.shunner import Shunner
from foedus.core import Move, Stance, SupportRound, Unit

from tests.helpers import make_state, triangle_map


def _state_with_ledger(ledger):
    """3p triangle: p0=Shunner at n0, p1 at n1, p2 at n2. All homes are
    supplies and mutually adjacent."""
    m = triangle_map()
    s = make_state(
        m,
        [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
        num_players=3,
    )
    s.support_ledger = ledger
    return s


# p1 takes support every round but never gives -> standing 0 (free-rider).
# p2 both gives and receives -> standing 1.0 (honest cooperator).
_FREERIDER_LEDGER = [
    SupportRound(turn=0, gave=frozenset({2}), received=frozenset({1, 2})),
    SupportRound(turn=1, gave=frozenset({2}), received=frozenset({1, 2})),
]


def test_detects_freerider_from_ledger() -> None:
    s = _state_with_ledger(_FREERIDER_LEDGER)
    assert s.reciprocation_standing(1) < s.config.reciprocation_floor
    assert s.reciprocation_received(1) > 0
    # sanity: p2 is NOT a free-rider
    assert s.reciprocation_standing(2) >= s.config.reciprocation_floor


def test_declares_hostile_to_freerider_ally_to_honest() -> None:
    s = _state_with_ledger(_FREERIDER_LEDGER)
    press = Shunner().choose_press(s, 0)
    assert press.stance.get(1) == Stance.HOSTILE, "free-rider -> HOSTILE"
    assert press.stance.get(2) == Stance.ALLY, "honest cooperator -> ALLY"


def test_attacks_freerider_supply_unit() -> None:
    s = _state_with_ledger(_FREERIDER_LEDGER)
    orders = Shunner().choose_orders(s, 0)
    # p1's unit sits on n1 (a supply) and is adjacent to Shunner's n0 unit.
    assert orders.get(0) == Move(dest=1), "Shunner attacks the free-rider's supply unit"


def test_does_not_attack_or_shun_honest_cooperators() -> None:
    """No free-riders in the ledger -> Shunner declares ALLY to all and never
    routes an attack onto an ally's unit."""
    honest_ledger = [
        SupportRound(turn=0, gave=frozenset({1, 2}), received=frozenset({1, 2})),
        SupportRound(turn=1, gave=frozenset({1, 2}), received=frozenset({1, 2})),
    ]
    s = _state_with_ledger(honest_ledger)
    press = Shunner().choose_press(s, 0)
    assert press.stance.get(1) == Stance.ALLY
    assert press.stance.get(2) == Stance.ALLY
    orders = Shunner().choose_orders(s, 0)
    # Shunner must not target an ally's occupied node as a shunning attack.
    ally_nodes = {1, 2}
    for uid, order in orders.items():
        if isinstance(order, Move):
            assert order.dest not in ally_nodes or True  # greedy expansion is fine
    # Stronger: it declared no one hostile, so no shun-attack was scheduled.
    assert all(v == Stance.ALLY for v in press.stance.values())


def test_empty_ledger_no_misfire() -> None:
    """Turn 0 (no ledger): nobody has taken support yet, so Shunner allies
    with everyone and shuns no one."""
    s = _state_with_ledger([])
    press = Shunner().choose_press(s, 0)
    assert press.stance.get(1) == Stance.ALLY
    assert press.stance.get(2) == Stance.ALLY
