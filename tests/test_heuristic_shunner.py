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
from foedus.core import Hold, Map, Move, NodeType, Stance, SupportRound, Unit
from foedus.resolve import resolve_turn

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
    # Detection is what drives BOTH hostility and shun-attacks; with no
    # free-riders it must fire on no one, so no shun-attack is ever scheduled.
    assert Shunner()._freeriders(s, 0) == set()
    assert all(v == Stance.ALLY for v in press.stance.values())


def test_punish_phase_actually_dislodges_freerider_through_resolution() -> None:
    """End-to-end: Shunner's coordinated 2-unit attack (Move + Support = str 2)
    dislodges a free-rider holding a supply (hold str 1), run through the real
    resolver — not just asserted on choose_orders output."""
    # n1(SUPPLY) is flanked by two Shunner nodes (n0 home, n2) and the
    # free-rider's home n3.
    m = Map(
        coords={0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (1, 1)},
        edges={0: frozenset({1}), 1: frozenset({0, 2, 3}),
               2: frozenset({1}), 3: frozenset({1})},
        node_types={0: NodeType.HOME, 1: NodeType.SUPPLY,
                    2: NodeType.PLAIN, 3: NodeType.HOME},
        home_assignments={0: 0, 3: 1},
    )
    s = make_state(
        m,
        [Unit(0, 0, 0), Unit(1, 0, 2),   # Shunner units flanking n1
         Unit(5, 1, 1)],                 # free-rider unit on the supply n1
        num_players=2,
    )
    s.support_ledger = [
        SupportRound(turn=0, gave=frozenset(), received=frozenset({1})),
        SupportRound(turn=1, gave=frozenset(), received=frozenset({1})),
    ]
    assert s.reciprocation_standing(1) < s.config.reciprocation_floor
    shunner_orders = Shunner().choose_orders(s, 0)
    out = resolve_turn(s, {0: shunner_orders, 1: {5: Hold()}})
    assert 5 not in out.units, "free-rider dislodged by the coordinated attack"


def test_empty_ledger_no_misfire() -> None:
    """Turn 0 (no ledger): nobody has taken support yet, so Shunner allies
    with everyone and shuns no one."""
    s = _state_with_ledger([])
    press = Shunner().choose_press(s, 0)
    assert press.stance.get(1) == Stance.ALLY
    assert press.stance.get(2) == Stance.ALLY
