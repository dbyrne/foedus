"""Round-trip tests for press tokens through the full round lifecycle."""

from __future__ import annotations

from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Intent,
    Move,
    Phase,
    Press,
    Stance,
)
from foedus.mapgen import generate_map
from foedus.press import (
    advance_turn,
    finalize_round,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import initial_state


def _fresh(num_players: int = 3) -> GameState:
    cfg = GameConfig(num_players=num_players, seed=42, max_turns=99)
    m = generate_map(num_players, seed=42)
    return initial_state(cfg, m)


def test_stance_archives_to_press_history() -> None:
    s = _fresh(num_players=2)
    p0 = Press(stance={1: Stance.ALLY}, intents=[])
    p1 = Press(stance={0: Stance.HOSTILE}, intents=[])
    s = submit_press_tokens(s, 0, p0)
    s = submit_press_tokens(s, 1, p1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.press_history[-1][0] == p0
    assert s.press_history[-1][1] == p1


def test_intent_archives_with_visible_to() -> None:
    s = _fresh(num_players=2)
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=frozenset({1}))
    p = Press(stance={}, intents=[intent])
    s = submit_press_tokens(s, 0, p)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.press_history[-1][0].intents[0] == intent


def test_revision_before_done_overwrites_pending() -> None:
    s = _fresh(num_players=2)
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents=[]))
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    assert s.round_press_pending[0].stance == {1: Stance.ALLY}


def test_revision_after_done_silently_dropped() -> None:
    s = _fresh(num_players=2)
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents=[]))
    s = signal_done(s, 0)
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents=[]))
    assert s.round_press_pending[0].stance == {1: Stance.ALLY}


def test_empty_press_via_advance_turn_archives_empty_press() -> None:
    s = _fresh(num_players=2)
    s = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.press_history[-1][0] == Press(stance={}, intents=[])
    assert s.press_history[-1][1] == Press(stance={}, intents=[])


def test_returning_to_negotiation_phase_after_finalize() -> None:
    s = _fresh(num_players=2)
    s = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.phase == Phase.NEGOTIATION


# --- Bundle 6: chat-done tracking --------------------------------------


def test_signal_chat_done_marks_player() -> None:
    from foedus.press import signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    assert 0 not in s.chat_done
    s2 = signal_chat_done(s, 0)
    assert 0 in s2.chat_done
    assert 1 not in s2.chat_done


def test_signal_chat_done_idempotent() -> None:
    from foedus.press import signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s2 = signal_chat_done(s, 0)
    s3 = signal_chat_done(s2, 0)
    assert s3.chat_done == {0}


def test_signal_chat_done_skips_eliminated() -> None:
    from foedus.press import signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s.eliminated.add(1)
    s2 = signal_chat_done(s, 1)
    assert s2.chat_done == set(), \
        "eliminated player should not be added to chat_done"


def test_is_chat_phase_complete_false_when_some_pending() -> None:
    from foedus.press import is_chat_phase_complete, signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    assert is_chat_phase_complete(s) is False
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    assert is_chat_phase_complete(s) is False, "p2 still pending"


def test_is_chat_phase_complete_true_when_all_signaled() -> None:
    from foedus.press import is_chat_phase_complete, signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    for p in range(3):
        s = signal_chat_done(s, p)
    assert is_chat_phase_complete(s) is True


def test_is_chat_phase_complete_skips_eliminated() -> None:
    """Eliminated players are not required to signal."""
    from foedus.press import is_chat_phase_complete, signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s.eliminated.add(2)
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    assert is_chat_phase_complete(s) is True


def test_finalize_round_resets_chat_done() -> None:
    """finalize_round must clear chat_done for the next round."""
    from foedus.press import (
        finalize_round, signal_chat_done, signal_done,
        submit_press_tokens,
    )
    cfg = GameConfig(num_players=2, max_turns=10)
    m = generate_map(2, seed=42)
    s = initial_state(cfg, m)
    for p in range(2):
        s = submit_press_tokens(s, p, Press(stance={}, intents=[]))
        s = signal_chat_done(s, p)
        s = signal_done(s, p)
    s = finalize_round(s, {})
    assert s.chat_done == set(), "chat_done not reset"
