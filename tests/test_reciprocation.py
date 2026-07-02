"""Primitive B — reciprocation standing + reciprocation-gated alliance bonus.

Free-riding is a rolling property: over a window of the last W turns, a player's
`given` (turns it issued >=1 uncut cross-player Support of a standing ALLY) vs
`received` (turns an ally supported it). recip = given/max(1,received).

The alliance-capture bonus (resolve.py 8b) is re-gated on the MOVER's
reciprocation standing: a free-rider (received>0, given=0 -> recip 0) is denied
the mover-side bonus it used to parasitize, while the SUPPORTER always earns
its side (we reward the giver). This replaces the deleted aid-spend gate.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Map,
    Move,
    NodeType,
    Press,
    Stance,
    SupportRound,
    Support,
    Unit,
)
from foedus.fog import visible_state_for
from foedus.press import finalize_round, signal_done, submit_press_tokens


# --- helpers ----------------------------------------------------------------


def _line4() -> Map:
    """n0(HOME p0) - n1(SUPPLY) - n2(SUPPLY) - n3(HOME p1)."""
    coords = {i: (i, 0) for i in range(4)}
    edges = {
        0: frozenset({1}), 1: frozenset({0, 2}),
        2: frozenset({1, 3}), 3: frozenset({2}),
    }
    node_types = {0: NodeType.HOME, 1: NodeType.SUPPLY,
                  2: NodeType.SUPPLY, 3: NodeType.HOME}
    return Map(coords=coords, edges=edges, node_types=node_types,
               home_assignments={0: 0, 3: 1})


def _state(units, *, num_players=2, ownership=None, support_ledger=None,
           reciprocation_floor=0.5) -> GameState:
    m = _line4()
    own = {n: None for n in m.nodes}
    own[0], own[3] = 0, 1
    for u in units:
        own[u.location] = u.owner
    if ownership:
        own.update(ownership)
    cfg = GameConfig(num_players=num_players, max_turns=50, build_period=999,
                     detente_threshold=0, high_value_supply_fraction=0.0,
                     reciprocation_floor=reciprocation_floor)
    return GameState(
        turn=0, map=m, units={u.id: u for u in units}, ownership=own,
        scores={p: 0.0 for p in range(num_players)}, eliminated=set(),
        next_unit_id=max((u.id for u in units), default=-1) + 1, config=cfg,
        support_ledger=list(support_ledger or []),
    )


def _finalize(state, press_by_player, orders):
    for p in range(state.config.num_players):
        if p in state.eliminated:
            continue
        press = press_by_player.get(p, Press(stance={}, intents=[]))
        state = submit_press_tokens(state, p, press)
        state = signal_done(state, p)
    return finalize_round(state, orders)


# --- ledger recording -------------------------------------------------------


def test_ally_support_records_give_and_receive() -> None:
    """p0 (ALLY->p1) supports p1's move -> p0 gave, p1 received this turn."""
    s = _state([Unit(0, 0, 0), Unit(1, 1, 2)], ownership={2: 1})
    s2 = _finalize(
        s,
        {0: Press(stance={1: Stance.ALLY}, intents=[]),
         1: Press(stance={0: Stance.ALLY}, intents=[])},
        {0: {0: Support(target=1)}, 1: {1: Move(dest=1)}},
    )
    last = s2.support_ledger[-1]
    assert last.gave == frozenset({0})
    assert last.received == frozenset({1})


def test_nonally_support_not_recorded() -> None:
    """A cross-player support where the giver did NOT declare ALLY doesn't
    count toward reciprocation."""
    s = _state([Unit(0, 0, 0), Unit(1, 1, 2)], ownership={2: 1})
    s2 = _finalize(
        s,
        {0: Press(stance={}, intents=[])},  # p0 NEUTRAL toward p1
        {0: {0: Support(target=1)}, 1: {1: Move(dest=1)}},
    )
    last = s2.support_ledger[-1]
    assert last.gave == frozenset()
    assert last.received == frozenset()


def test_cut_support_not_recorded() -> None:
    """A support cut by an enemy attack doesn't count (only uncut supports)."""
    # p0@n1 supports p1's u1@n2 move to n... ; p2 cuts p0 by attacking n1.
    m = _line4()
    units = [Unit(0, 0, 1), Unit(1, 1, 2), Unit(2, 2, 0)]
    own = {n: None for n in m.nodes}
    own.update({0: 2, 1: 0, 2: 1, 3: 1})
    cfg = GameConfig(num_players=3, max_turns=50, build_period=999,
                     detente_threshold=0)
    s = GameState(turn=0, map=m, units={u.id: u for u in units}, ownership=own,
                  scores={0: 0.0, 1: 0.0, 2: 0.0}, eliminated=set(),
                  next_unit_id=3, config=cfg)
    s2 = _finalize(
        s,
        {0: Press(stance={1: Stance.ALLY}, intents=[])},
        # p0 supports p1's move n2->n3; p2 attacks n1 (cuts p0's support).
        {0: {0: Support(target=1)}, 1: {1: Move(dest=3)}, 2: {2: Move(dest=1)}},
    )
    last = s2.support_ledger[-1]
    assert 0 not in last.gave  # cut -> not credited


# --- rolling window + helpers -----------------------------------------------


def test_window_trims_to_configured_size() -> None:
    """support_ledger keeps only the last `reciprocation_window` entries."""
    ledger = [SupportRound(turn=t, gave=frozenset(), received=frozenset())
              for t in range(10)]
    s = _state([Unit(0, 0, 0), Unit(1, 1, 3)], support_ledger=ledger)
    s2 = _finalize(s, {}, {0: {0: Hold()}, 1: {1: Hold()}})
    assert len(s2.support_ledger) == s.config.reciprocation_window


def test_given_received_standing_helpers() -> None:
    ledger = [
        SupportRound(turn=0, gave=frozenset({0}), received=frozenset({1})),
        SupportRound(turn=1, gave=frozenset({0}), received=frozenset({1})),
        SupportRound(turn=2, gave=frozenset(), received=frozenset({1})),
        SupportRound(turn=3, gave=frozenset(), received=frozenset({1})),
    ]
    s = _state([Unit(0, 0, 0), Unit(1, 1, 3)], support_ledger=ledger)
    assert s.reciprocation_given(0) == 2
    assert s.reciprocation_received(0) == 0
    assert s.reciprocation_given(1) == 0
    assert s.reciprocation_received(1) == 4
    assert s.reciprocation_standing(1) == 0.0        # freerider
    assert s.reciprocation_standing(0) == 2.0        # given 2 / max(1,0)
    assert s.freeride_debt(1) == 4
    assert s.freeride_debt(0) == 0


# --- alliance-bonus re-gate --------------------------------------------------


@pytest.fixture
def alliance_bonus_3(monkeypatch):
    monkeypatch.setenv("FOEDUS_ALLIANCE_BONUS", "3")


def _bonus_scenario(mover_ledger):
    """p0 (mover) moves u0@n0 -> n1(supply); p1 (supporter, ALLY->p0) backs it
    from n2. Alliance bonus fires. `mover_ledger` sets p0's prior standing."""
    s = _state([Unit(0, 0, 0), Unit(1, 1, 2)], ownership={2: 1},
               support_ledger=mover_ledger)
    return _finalize(
        s,
        {0: Press(stance={1: Stance.ALLY}, intents=[]),
         1: Press(stance={0: Stance.ALLY}, intents=[])},
        {0: {0: Move(dest=1)}, 1: {1: Support(target=0)}},
    )


def test_freerider_mover_denied_alliance_bonus(alliance_bonus_3) -> None:
    """p0 has taken support but never given (recip 0) -> denied the mover-side
    bonus; p1 (supporter) still earns its side."""
    freerider = [SupportRound(turn=t, gave=frozenset(),
                              received=frozenset({0})) for t in range(4)]
    recip = [SupportRound(turn=t, gave=frozenset({0}),
                          received=frozenset({0})) for t in range(4)]
    s_free = _bonus_scenario(freerider)
    s_recip = _bonus_scenario(recip)
    # Mover p0 gets +3 only when in good standing.
    assert s_recip.scores[0] - s_free.scores[0] == 3.0
    # Supporter p1 earns its side regardless of the mover's standing.
    assert s_recip.scores[1] == s_free.scores[1]


def test_never_received_mover_not_treated_as_freerider(alliance_bonus_3) -> None:
    """A mover that never took ally support (received==0) is not free-riding,
    so it keeps the bonus even with given==0 (empty ledger)."""
    s_empty = _bonus_scenario([])
    recip = [SupportRound(turn=t, gave=frozenset({0}),
                          received=frozenset({0})) for t in range(4)]
    s_recip = _bonus_scenario(recip)
    assert s_empty.scores[0] == s_recip.scores[0]  # both get the mover bonus


def test_supporter_bonus_unconditional(alliance_bonus_3) -> None:
    """Even a free-riding SUPPORTER earns the supporter-side bonus — the gate
    only withholds the MOVER-side reward."""
    # p1 is the supporter and a freerider; it should still get its +3.
    s = _state([Unit(0, 0, 0), Unit(1, 1, 2)], ownership={2: 1},
               support_ledger=[SupportRound(turn=t, gave=frozenset(),
                                            received=frozenset({1}))
                               for t in range(4)])
    s2 = _finalize(
        s,
        {0: Press(stance={1: Stance.ALLY}, intents=[]),
         1: Press(stance={0: Stance.ALLY}, intents=[])},
        {0: {0: Move(dest=1)}, 1: {1: Support(target=0)}},
    )
    # p1 supported a capture -> earns the supporter bonus regardless of its own
    # (bad) standing. Its score exceeds bare home income (1.0).
    assert s2.scores[1] >= 1.0 + 3.0


# --- public exposure --------------------------------------------------------


def test_public_reciprocation_in_fog() -> None:
    ledger = [SupportRound(turn=0, gave=frozenset({0}),
                           received=frozenset({1}))]
    s = _state([Unit(0, 0, 0), Unit(1, 1, 3)], support_ledger=ledger)
    view = visible_state_for(s, 1)
    rec = view["public_reciprocation"]
    assert rec[0]["given"] == 1 and rec[0]["received"] == 0
    assert rec[1]["given"] == 0 and rec[1]["received"] == 1
