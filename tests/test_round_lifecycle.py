"""Tests for round-lifecycle engine functions in foedus/press.py."""

from __future__ import annotations

from foedus.core import GameConfig, GameState, Hold, Intent, Phase, Press, Stance
from foedus.mapgen import generate_map
from foedus.press import submit_press_tokens
from foedus.resolve import initial_state


def _fresh_state(num_players: int = 3) -> GameState:
    cfg = GameConfig(num_players=num_players, seed=42)
    m = generate_map(num_players, seed=42)
    return initial_state(cfg, m)


def test_submit_press_tokens_records_pending() -> None:
    s = _fresh_state()
    p = Press(stance={1: Stance.ALLY}, intents=[])
    s = submit_press_tokens(s, 0, p)
    assert s.round_press_pending[0] == p


def test_submit_press_tokens_overwrites_on_revision() -> None:
    s = _fresh_state()
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents=[]))
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    assert s.round_press_pending[0].stance == {1: Stance.ALLY}


def test_submit_press_tokens_rejects_after_done() -> None:
    s = _fresh_state()
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    s.round_done.add(0)  # simulate signal_done; we'll test it separately
    s2 = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents=[]))
    # Submission silently dropped, pending press unchanged.
    assert s2.round_press_pending[0].stance == {1: Stance.ALLY}


def test_submit_press_tokens_rejects_when_phase_not_negotiation() -> None:
    s = _fresh_state()
    s.phase = Phase.ORDERS
    s2 = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    assert 0 not in s2.round_press_pending


def test_submit_press_tokens_rejects_eliminated_player() -> None:
    s = _fresh_state()
    s.eliminated.add(0)
    s2 = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    assert 0 not in s2.round_press_pending


def test_submit_press_tokens_drops_intents_for_non_owned_units() -> None:
    s = _fresh_state(3)
    # Player 0 owns one unit; trying to declare an intent about another player's
    # unit should be silently dropped on submit.
    other_unit_id = next(u.id for u in s.units.values() if u.owner != 0)
    p = Press(
        stance={},
        intents=[Intent(unit_id=other_unit_id, declared_order=Hold(),
                        visible_to=frozenset({1}))],
    )
    s = submit_press_tokens(s, 0, p)
    # The full Press is recorded but the offending intent is dropped on submit.
    assert s.round_press_pending[0].intents == []


from foedus.press import signal_done


def test_signal_done_marks_player() -> None:
    s = _fresh_state()
    s = signal_done(s, 0)
    assert 0 in s.round_done


def test_signal_done_is_idempotent() -> None:
    s = _fresh_state()
    s = signal_done(s, 0)
    s = signal_done(s, 0)
    assert s.round_done == {0}


def test_signal_done_rejects_eliminated() -> None:
    s = _fresh_state()
    s.eliminated.add(0)
    s = signal_done(s, 0)
    assert 0 not in s.round_done


def test_signal_done_rejects_outside_negotiation_phase() -> None:
    s = _fresh_state()
    s.phase = Phase.ORDERS
    s = signal_done(s, 0)
    assert 0 not in s.round_done


from foedus.press import force_round_end, is_round_complete


def test_is_round_complete_false_when_no_one_done() -> None:
    s = _fresh_state(num_players=3)
    assert is_round_complete(s) is False


def test_is_round_complete_false_with_partial_done() -> None:
    s = _fresh_state(num_players=3)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    assert is_round_complete(s) is False


def test_is_round_complete_true_when_all_survivors_done() -> None:
    s = _fresh_state(num_players=3)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = signal_done(s, 2)
    assert is_round_complete(s) is True


def test_is_round_complete_skips_eliminated_players() -> None:
    s = _fresh_state(num_players=3)
    s.eliminated.add(2)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    assert is_round_complete(s) is True


def test_force_round_end_marks_unsubmitted_as_done_with_empty_press() -> None:
    s = _fresh_state(num_players=3)
    # Player 0 submits and signals done. Players 1 and 2 do nothing.
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    s = signal_done(s, 0)
    s = force_round_end(s)
    assert s.round_done == {0, 1, 2}
    assert s.round_press_pending[0].stance == {1: Stance.ALLY}
    assert s.round_press_pending.get(1, Press(stance={}, intents=[])).stance == {}
    assert s.round_press_pending.get(2, Press(stance={}, intents=[])).stance == {}


def test_force_round_end_preserves_submitted_pending() -> None:
    s = _fresh_state(num_players=3)
    p1 = Press(stance={0: Stance.HOSTILE}, intents=[])
    s = submit_press_tokens(s, 1, p1)
    s = force_round_end(s)
    assert s.round_press_pending[1] == p1


from foedus.press import advance_turn, finalize_round


def test_advance_turn_with_empty_press_matches_old_resolve_turn() -> None:
    """advance_turn(state, orders) should be semantically equivalent to
    the old resolve_turn(state, orders) for any flow that never used press.

    Disable stagnation_cost so we're comparing against pre-Press v0
    score behavior — resolve_turn doesn't apply stagnation; finalize_round
    does. Equivalence only holds with stagnation off.
    """
    from foedus.core import Hold
    from foedus.resolve import resolve_turn

    s_old = _fresh_state(num_players=3)
    s_new = _fresh_state(num_players=3)
    s_old.config.stagnation_cost = 0.0
    s_new.config.stagnation_cost = 0.0
    orders = {0: {0: Hold()}, 1: {1: Hold()}, 2: {2: Hold()}}
    s_old = resolve_turn(s_old, orders)
    s_new = advance_turn(s_new, orders)
    assert {u.id: (u.owner, u.location) for u in s_old.units.values()} == \
           {u.id: (u.owner, u.location) for u in s_new.units.values()}
    assert s_old.scores == s_new.scores
    assert s_old.eliminated == s_new.eliminated


def test_finalize_round_archives_press_and_chat() -> None:
    from foedus.core import ChatDraft, Hold, Press, Stance
    from foedus.press import record_chat_message
    s = _fresh_state(num_players=3)
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={0: Stance.ALLY}, intents=[]))
    s = submit_press_tokens(s, 2, Press(stance={}, intents=[]))
    s = record_chat_message(s, 0, ChatDraft(None, "let's ally"))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = signal_done(s, 2)
    s = finalize_round(s, {p: {p: Hold()} for p in range(3)})
    assert len(s.press_history) == 1
    assert len(s.chat_history) == 1
    assert len(s.chat_history[0]) == 1
    assert s.chat_history[0][0].body == "let's ally"


def test_finalize_round_clears_round_scratch() -> None:
    from foedus.core import Hold
    s = _fresh_state(num_players=2)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {p: {p: Hold()} for p in range(2)})
    assert s.round_chat == []
    assert s.round_press_pending == {}
    assert s.round_done == set()
    assert s.phase == Phase.NEGOTIATION  # ready for next turn


def test_submit_press_tokens_drops_empty_visible_to() -> None:
    s = _fresh_state()
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=frozenset())
    p = Press(stance={}, intents=[intent])
    s = submit_press_tokens(s, 0, p)
    # Intent should be dropped (empty visible_to).
    assert s.round_press_pending[0].intents == []


def test_submit_press_tokens_filters_eliminated_from_visible_to() -> None:
    s = _fresh_state(num_players=3)
    s.eliminated.add(1)
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=frozenset({1, 2}))
    p = Press(stance={}, intents=[intent])
    s = submit_press_tokens(s, 0, p)
    # Eliminated player 1 should be filtered out, leaving visible_to={2}.
    stored = s.round_press_pending[0].intents[0]
    assert stored.visible_to == frozenset({2})


def test_submit_press_tokens_filters_self_from_visible_to() -> None:
    s = _fresh_state()
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=frozenset({0, 1}))
    p = Press(stance={}, intents=[intent])
    s = submit_press_tokens(s, 0, p)
    stored = s.round_press_pending[0].intents[0]
    assert stored.visible_to == frozenset({1})  # 0 (self) removed


def test_submit_press_tokens_keeps_public_intent_unchanged() -> None:
    s = _fresh_state()
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    p = Press(stance={}, intents=[intent])
    s = submit_press_tokens(s, 0, p)
    assert s.round_press_pending[0].intents[0].visible_to is None
