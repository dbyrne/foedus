"""Bundle 4 — aid resource tests.

Covers token generation, spending, mutual-ALLY gate, cap, and the
reactive aid landing rule (aid lands whenever recipient's unit survives).
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    AidSpend,
    GameState,
    Hold,
    Move,
    Press,
    Stance,
    Unit,
)
from foedus.press import (
    advance_turn,
    finalize_round,
    signal_done,
    submit_aid_spends,
    submit_press_tokens,
)

from tests.helpers import line_map, make_state


def _setup_two_player() -> GameState:
    """Two players, line map of 5 nodes, units at the home ends.

    Initial supplies: player 0 owns home node 0; player 1 owns home node 4.
    Interior nodes 1, 2, 3 are SUPPLY but unowned.
    """
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)],
                   num_players=2, max_turns=99)
    return s


def _archive_mutual_ally(s: GameState, players: list[int]) -> GameState:
    """Append a fake press_history entry where every named player declares
    ALLY toward each other. Lets later turns' submit_aid_spends pass the
    mutual-ALLY gate without going through a full negotiation round.
    """
    entry: dict[int, Press] = {}
    for p in players:
        stance = {q: Stance.ALLY for q in players if q != p}
        entry[p] = Press(stance=stance, intents=[])
    new_history = list(s.press_history) + [entry]
    return replace(s, press_history=new_history)


def test_token_generation_from_supply() -> None:
    """At end of finalize, each survivor gets floor(supply / divisor) tokens
    capped at config.aid_token_cap.
    """
    s = _setup_two_player()
    # Default divisor=3, cap=10. Each player has 1 supply (their home),
    # so floor(1/3) = 0 per turn. Run a turn and check.
    s = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.aid_tokens.get(0, 0) == 0
    assert s.aid_tokens.get(1, 0) == 0


def test_token_generation_scales_with_supplies() -> None:
    """A player with multiple supplies generates more tokens per turn."""
    s = _setup_two_player()
    # Force player 0 to own all 5 nodes (3 supplies + 2 homes).
    new_ownership = {n: 0 for n in s.map.nodes}
    s = replace(s, ownership=new_ownership)
    s = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # supply_count for player 0 is 5; floor(5/3) = 1.
    # supply_count for player 1 is 0; floor(0/3) = 0.
    assert s.aid_tokens.get(0, 0) == 1
    assert s.aid_tokens.get(1, 0) == 0


def test_token_cap_enforced() -> None:
    """Tokens cap at config.aid_token_cap regardless of supply count."""
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 9, 1: 0})
    new_ownership = {n: 0 for n in s.map.nodes}  # 5 supplies for p0
    s = replace(s, ownership=new_ownership)
    s = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # Would be 9 + 1 = 10; cap is 10. So 10.
    assert s.aid_tokens[0] == 10
    # Run another turn; would be 11 capped at 10.
    s = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.aid_tokens[0] == 10


def test_aid_for_self_dropped() -> None:
    """submit_aid_spends drops spends targeting the spender's own unit."""
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 5, 1: 0})
    spend = AidSpend(target_unit=0)  # u0 is p0's own
    s = submit_aid_spends(s, 0, [spend])
    assert s.round_aid_pending.get(0, []) == []


def test_aid_requires_mutual_ally() -> None:
    """submit_aid_spends drops spends to non-mutual-ALLY recipients."""
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 5, 1: 0})
    # Set up a previous-turn press with player 0 ALLY to 1 but 1 NEUTRAL to 0.
    one_way = {
        0: Press(stance={1: Stance.ALLY}, intents=[]),
        1: Press(stance={0: Stance.NEUTRAL}, intents=[]),
    }
    s = replace(s, press_history=[one_way])
    spend = AidSpend(target_unit=1)
    s = submit_aid_spends(s, 0, [spend])
    # Not mutual ALLY → dropped.
    assert s.round_aid_pending.get(0, []) == []


def test_aid_balance_caps_pending() -> None:
    """Submitting more aid than tokens caps at the available balance."""
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 1, 1: 0})
    s = _archive_mutual_ally(s, [0, 1])
    spends = [
        AidSpend(target_unit=1),
        AidSpend(target_unit=1),
        AidSpend(target_unit=1),
    ]
    s = submit_aid_spends(s, 0, spends)
    assert len(s.round_aid_pending[0]) == 1


def test_aid_lands_when_recipient_holds() -> None:
    """Reactive aid lands when the recipient Holds — aid_given increments."""
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 1, 1: 0})
    s = _archive_mutual_ally(s, [0, 1])
    # P0 aids P1's u1 — reactive, so it lands regardless of recipient's order.
    spend = AidSpend(target_unit=1)
    s = submit_aid_spends(s, 0, [spend])
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={0: Stance.ALLY}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # Aid landed: aid_given[(0, 1)] = 1.
    assert s.aid_given.get((0, 1), 0) == 1
    # Token consumed.
    # (Plus regen from supply/3; both players have 1 supply each = 0 regen.)
    assert s.aid_tokens[0] == 0


def test_reactive_aid_lands_on_any_target_order() -> None:
    """AidSpend lands regardless of what order the recipient actually submits.

    Under reactive aid, the aid is committed to the unit — not to a specific
    order. Whether the recipient Holds, Moves, or does anything else, the
    spend lands (and aid_given increments) as long as the unit survives.
    """
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 1, 1: 0})
    s = _archive_mutual_ally(s, [0, 1])
    # P0 aids P1's u1. P1 will Move instead of holding — but aid still lands.
    spend = AidSpend(target_unit=1)
    s = submit_aid_spends(s, 0, [spend])
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={0: Stance.ALLY}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    # P1 moves toward node 3 (adjacent on line map); move may bounce but unit survives.
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Move(dest=3)}})
    # Aid landed: aid_given[(0, 1)] = 1.
    assert s.aid_given.get((0, 1), 0) == 1
    # Token still consumed.
    assert s.aid_tokens[0] == 0


def test_aid_round_pending_cleared_at_finalize() -> None:
    """round_aid_pending is reset at finalize_round, like other round scratch."""
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 1, 1: 0})
    s = _archive_mutual_ally(s, [0, 1])
    spend = AidSpend(target_unit=1)
    s = submit_aid_spends(s, 0, [spend])
    assert s.round_aid_pending[0] == [spend]
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={0: Stance.ALLY}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.round_aid_pending == {}


def test_aid_revision_overwrites() -> None:
    """Multiple submit_aid_spends calls before signal_done overwrite."""
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 5, 1: 0})
    s = _archive_mutual_ally(s, [0, 1])
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_aid_spends(s, 0, [
        AidSpend(target_unit=1),
        AidSpend(target_unit=1),
    ])
    assert len(s.round_aid_pending[0]) == 2


def test_aid_post_done_dropped() -> None:
    """submit_aid_spends after signal_done is rejected (state unchanged)."""
    s = _setup_two_player()
    s = replace(s, aid_tokens={0: 5, 1: 0})
    s = _archive_mutual_ally(s, [0, 1])
    s = signal_done(s, 0)
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    assert s.round_aid_pending.get(0, []) == []
