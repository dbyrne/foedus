"""Tests for chat message recording (Press v0)."""

from __future__ import annotations

from foedus.core import ChatDraft, GameConfig, GameState, Phase
from foedus.mapgen import generate_map
from foedus.press import record_chat_message, signal_done
from foedus.resolve import initial_state


def _fresh_state(num_players: int = 3) -> GameState:
    cfg = GameConfig(num_players=num_players, seed=42)
    m = generate_map(num_players, seed=42)
    return initial_state(cfg, m)


def test_record_public_broadcast() -> None:
    s = _fresh_state()
    d = ChatDraft(recipients=None, body="hello everyone")
    s = record_chat_message(s, sender=0, draft=d)
    assert len(s.round_chat) == 1
    assert s.round_chat[0].sender == 0
    assert s.round_chat[0].recipients is None
    assert s.round_chat[0].body == "hello everyone"
    assert s.round_chat[0].sequence == 0
    assert s.round_chat[0].turn == s.turn


def test_record_private_dm() -> None:
    s = _fresh_state()
    d = ChatDraft(recipients=frozenset({1}), body="psst")
    s = record_chat_message(s, sender=0, draft=d)
    assert s.round_chat[0].recipients == frozenset({1})


def test_sequence_numbers_are_monotonic() -> None:
    s = _fresh_state()
    s = record_chat_message(s, 0, ChatDraft(None, "a"))
    s = record_chat_message(s, 1, ChatDraft(None, "b"))
    s = record_chat_message(s, 2, ChatDraft(None, "c"))
    assert [m.sequence for m in s.round_chat] == [0, 1, 2]


def test_message_dropped_when_body_exceeds_cap() -> None:
    s = _fresh_state()
    cfg = s.config
    long_body = "x" * (cfg.chat_char_cap + 1)
    s = record_chat_message(s, 0, ChatDraft(None, long_body))
    assert s.round_chat == []


def test_message_dropped_when_sender_eliminated() -> None:
    s = _fresh_state()
    s.eliminated.add(0)
    s = record_chat_message(s, 0, ChatDraft(None, "ghost message"))
    assert s.round_chat == []


def test_message_dropped_when_recipient_eliminated() -> None:
    s = _fresh_state()
    s.eliminated.add(1)
    s = record_chat_message(s, 0, ChatDraft(frozenset({1}), "to ghost"))
    assert s.round_chat == []


def test_message_dropped_when_phase_not_negotiation() -> None:
    s = _fresh_state()
    s.phase = Phase.ORDERS
    s = record_chat_message(s, 0, ChatDraft(None, "wrong phase"))
    assert s.round_chat == []


def test_message_dropped_when_sender_already_done() -> None:
    s = _fresh_state()
    s = signal_done(s, 0)
    s = record_chat_message(s, 0, ChatDraft(None, "after done"))
    assert s.round_chat == []
