"""Tests for fog-of-war exposure of press, chat, and betrayal data."""

from __future__ import annotations

from foedus.core import (
    BetrayalObservation,
    ChatMessage,
    Hold,
    Intent,
    Press,
    Stance,
    Unit,
)
from foedus.fog import visible_state_for

from tests.helpers import line_map, make_state


def _state_with_history():
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2)
    s.press_history.append({
        0: Press(stance={1: Stance.ALLY},
                 intents={1: [Intent(unit_id=0, declared_order=Hold())]}),
        1: Press(stance={0: Stance.HOSTILE}, intents={}),
    })
    s.chat_history.append([
        ChatMessage(turn=0, sequence=0, sender=0, recipients=None,
                    body="hi all"),
        ChatMessage(turn=0, sequence=1, sender=0,
                    recipients=frozenset({1}), body="hi 1"),
        ChatMessage(turn=0, sequence=2, sender=1, recipients=None,
                    body="hello"),
    ])
    s.betrayals[0] = []
    s.betrayals[1] = [BetrayalObservation(
        turn=1, betrayer=0,
        intent=Intent(unit_id=0, declared_order=Hold()),
        actual_order=Hold(),
    )]
    return s


def test_public_stance_matrix_visible_to_all() -> None:
    s = _state_with_history()
    v0 = visible_state_for(s, 0)
    v1 = visible_state_for(s, 1)
    assert v0["public_stance_matrix"] == v1["public_stance_matrix"]
    assert v0["public_stance_matrix"][0][1] == "ally"
    assert v0["public_stance_matrix"][1][0] == "hostile"


def test_inbound_intents_only_to_recipient() -> None:
    s = _state_with_history()
    v0 = visible_state_for(s, 0)
    v1 = visible_state_for(s, 1)
    assert v1["your_inbound_intents"][0] == [Intent(unit_id=0, declared_order=Hold())]
    assert v0["your_inbound_intents"] == {}


def test_chat_filtered_by_recipient() -> None:
    s = _state_with_history()
    v0 = visible_state_for(s, 0)
    v1 = visible_state_for(s, 1)
    bodies_0 = [m.body for m in v0["your_chat"]]
    assert set(bodies_0) == {"hi all", "hi 1", "hello"}
    bodies_1 = [m.body for m in v1["your_chat"]]
    assert set(bodies_1) == {"hi all", "hi 1", "hello"}


def test_betrayals_only_visible_to_betrayed() -> None:
    s = _state_with_history()
    v0 = visible_state_for(s, 0)
    v1 = visible_state_for(s, 1)
    assert v0["your_betrayals"] == []
    assert len(v1["your_betrayals"]) == 1
