"""Tests for the new Press v0 types in core.py."""

from __future__ import annotations

from foedus.core import (
    BetrayalObservation,
    ChatDraft,
    ChatMessage,
    Hold,
    Intent,
    Move,
    Phase,
    Press,
    Stance,
)


def test_phase_enum_has_negotiation_and_orders() -> None:
    assert Phase.NEGOTIATION.value == "negotiation"
    assert Phase.ORDERS.value == "orders"


def test_stance_enum_has_three_values() -> None:
    assert Stance.ALLY.value == "ally"
    assert Stance.NEUTRAL.value == "neutral"
    assert Stance.HOSTILE.value == "hostile"


def test_intent_constructible_with_unit_id_and_order() -> None:
    i = Intent(unit_id=3, declared_order=Move(dest=7), visible_to=None)
    assert i.unit_id == 3
    assert i.declared_order == Move(dest=7)


def test_intent_is_frozen() -> None:
    i = Intent(unit_id=1, declared_order=Hold(), visible_to=None)
    try:
        i.unit_id = 2  # type: ignore[misc]
    except (AttributeError, Exception):
        return
    raise AssertionError("Intent should be frozen")


def test_intent_visible_to_field() -> None:
    # Public intent.
    i_pub = Intent(unit_id=1, declared_order=Hold(), visible_to=None)
    assert i_pub.visible_to is None
    # Bilateral intent.
    i_priv = Intent(unit_id=1, declared_order=Hold(), visible_to=frozenset({2}))
    assert i_priv.visible_to == frozenset({2})
    # Group intent.
    i_grp = Intent(unit_id=1, declared_order=Hold(), visible_to=frozenset({2, 3}))
    assert i_grp.visible_to == frozenset({2, 3})


def test_press_intents_is_list() -> None:
    p = Press(stance={}, intents=[Intent(unit_id=0, declared_order=Hold(), visible_to=None)])
    assert isinstance(p.intents, list)
    assert len(p.intents) == 1


def test_press_constructible_with_empty_dicts() -> None:
    p = Press(stance={}, intents=[])
    assert p.stance == {}
    assert p.intents == []


def test_press_with_stance_and_intents() -> None:
    p = Press(
        stance={1: Stance.ALLY, 2: Stance.HOSTILE},
        intents=[Intent(unit_id=0, declared_order=Hold(), visible_to=frozenset({1}))],
    )
    assert p.stance[1] == Stance.ALLY
    assert len(p.intents) == 1


def test_chat_draft_constructible() -> None:
    d = ChatDraft(recipients=None, body="hello world")
    assert d.recipients is None
    assert d.body == "hello world"


def test_chat_message_constructible() -> None:
    m = ChatMessage(turn=2, sequence=0, sender=1,
                    recipients=frozenset({0}), body="psst")
    assert m.turn == 2
    assert m.sequence == 0
    assert m.sender == 1
    assert m.recipients == frozenset({0})
    assert m.body == "psst"


def test_betrayal_observation_constructible() -> None:
    intent = Intent(unit_id=3, declared_order=Move(dest=7), visible_to=None)
    actual = Hold()
    b = BetrayalObservation(turn=4, betrayer=0, intent=intent,
                            actual_order=actual)
    assert b.turn == 4
    assert b.betrayer == 0
    assert b.intent == intent
    assert b.actual_order == actual
