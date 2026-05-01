"""Tests for the aid_given cap (Patron remediation)."""
from dataclasses import replace

import pytest

from foedus.core import AidSpend, GameConfig


def test_default_cap_is_3():
    cfg = GameConfig()
    assert cfg.aid_given_cap == 3


def test_cap_is_configurable():
    cfg = GameConfig(aid_given_cap=5)
    assert cfg.aid_given_cap == 5


from foedus.core import (
    AidSpend,
    GameState,
    Hold,
    Map,
    Move,
    NodeType,
    Press,
    Stance,
    Unit,
)
from foedus.press import (
    finalize_round,
    signal_chat_done,
    signal_done,
    submit_aid_spends,
    submit_press_tokens,
)


def _two_player_state_with_press_history(aid_given_init=None,
                                          aid_tokens_init=None,
                                          cap=3):
    """Build a 2-player state suitable for aid-cap testing.

    Layout: P0 unit at node 0, P1 unit at node 1; nodes 0/1/2 fully connected.
    Sets up press_history with mutual ALLY so submit_aid_spends accepts.
    """
    nodes = [0, 1, 2]
    coords = {n: (n, 0) for n in nodes}
    edges = {0: frozenset({1, 2}), 1: frozenset({0, 2}), 2: frozenset({0, 1})}
    node_types = {0: NodeType.HOME, 1: NodeType.HOME, 2: NodeType.SUPPLY}
    home_assignments = {0: 0, 1: 1}
    m = Map(coords=coords, edges=edges, node_types=node_types,
            home_assignments=home_assignments)
    units = {
        0: Unit(id=0, owner=0, location=0),
        1: Unit(id=1, owner=1, location=1),
    }
    cfg = GameConfig(num_players=2, max_turns=10, seed=0,
                     aid_given_cap=cap)
    # Synthetic prior turn with mutual ALLY so submit_aid_spends accepts
    # spends on turn 1 (the gate checks press_history[-1]).
    prior_press = {
        0: Press(stance={1: Stance.ALLY}, intents=[]),
        1: Press(stance={0: Stance.ALLY}, intents=[]),
    }
    state = GameState(
        turn=0, map=m, units=units,
        ownership={0: 0, 1: 1, 2: None},
        scores={0: 0.0, 1: 0.0},
        eliminated=set(),
        next_unit_id=2,
        config=cfg,
        press_history=[prior_press],
        aid_tokens=aid_tokens_init or {0: 5, 1: 0},
        aid_given=aid_given_init or {},
    )
    return state


def test_aid_given_clamps_at_cap():
    """Pre-populate aid_given[(0,1)]=3 (cap); land one more aid; ledger stays at 3."""
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 3},
        aid_tokens_init={0: 1, 1: 0},
        cap=3,
    )
    # P0 spends one aid token on P1's unit 1.
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    # Both players Hold; P1's unit 1 still has a canon order so aid lands.
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    assert s2.aid_given[(0, 1)] == 3, "ledger should clamp at cap"


def test_token_still_consumed_past_cap():
    """At cap, the spend still consumes the token."""
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 3},
        aid_tokens_init={0: 1, 1: 0},
        cap=3,
    )
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    # P0 had 1 token; spent 1; should be 0 (modulo regeneration). Even with
    # regeneration from 1 controlled supply (n=1 home // divisor=3 = 0),
    # final balance = 0.
    assert s2.aid_tokens.get(0, 0) == 0, "token still consumed at cap"


def test_aid_strength_bonus_still_fires_past_cap():
    """At cap, the +1 strength bonus still applies to the recipient's order."""
    from foedus.resolve import _compute_aid_per_unit
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 3},
        aid_tokens_init={0: 1, 1: 0},
        cap=3,
    )
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    # Synthesize a canon dict where unit 1 has a Hold; compute aid_per_unit.
    canon = {0: Hold(), 1: Hold()}
    aid_per_unit = _compute_aid_per_unit(s, canon)
    assert aid_per_unit.get(1) == 1, "strength bonus fires regardless of cap"


def test_custom_cap_via_config():
    """A non-default cap value is respected by the clamp."""
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 5},
        aid_tokens_init={0: 1, 1: 0},
        cap=5,
    )
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    assert s2.aid_given[(0, 1)] == 5, "cap=5 should clamp at 5"


def test_leverage_bonus_naturally_bounded_by_cap():
    """With cap=3, leverage_bonus(A,B) cannot exceed 1."""
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 3, (1, 0): 0},
        cap=3,
    )
    # leverage(0, 1) = 3 - 0 = 3; bonus = min(2, 3//2) = 1.
    assert s.leverage(0, 1) == 3
    assert s.leverage_bonus(0, 1) == 1
    # Even after another spend lands at cap, leverage doesn't grow beyond 3.
    s = replace(s, aid_given={(0, 1): 3, (1, 0): 0}, aid_tokens={0: 1, 1: 0})
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    assert s2.leverage_bonus(0, 1) == 1, "bonus stays at +1 with cap=3"
