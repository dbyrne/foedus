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


def test_pending_press_exposes_own_round_submission() -> None:
    from foedus.core import GameConfig, Press, Stance
    from foedus.mapgen import generate_map
    from foedus.press import submit_press_tokens
    from foedus.resolve import initial_state

    cfg = GameConfig(num_players=2, seed=42)
    s = initial_state(cfg, generate_map(2, seed=42))
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents={}))
    v0 = visible_state_for(s, 0)
    v1 = visible_state_for(s, 1)
    # Player 0 sees their own pending press.
    assert v0["your_pending_press"] is not None
    assert v0["your_pending_press"].stance == {1: Stance.ALLY}
    # Player 1 has not submitted, sees None.
    assert v1["your_pending_press"] is None


def test_pending_press_never_exposes_others() -> None:
    from foedus.core import GameConfig, Press, Stance
    from foedus.mapgen import generate_map
    from foedus.press import submit_press_tokens
    from foedus.resolve import initial_state

    cfg = GameConfig(num_players=2, seed=42)
    s = initial_state(cfg, generate_map(2, seed=42))
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents={}))
    v1 = visible_state_for(s, 1)
    # Player 1 should NOT see player 0's pending press.
    assert v1["your_pending_press"] is None
    # And there's no way for v1 to see player 0's stance from current round
    # (last completed round = empty press_history).
    # Sanity check: the public_stance_matrix doesn't contain in-progress data.
    # Since press_history is empty, the matrix would show NEUTRAL defaults.


def test_round_chat_so_far_exposes_in_progress_chat() -> None:
    from foedus.core import ChatDraft, GameConfig
    from foedus.mapgen import generate_map
    from foedus.press import record_chat_message
    from foedus.resolve import initial_state

    cfg = GameConfig(num_players=3, seed=42)
    s = initial_state(cfg, generate_map(3, seed=42))
    s = record_chat_message(s, 0, ChatDraft(None, "public test"))
    s = record_chat_message(s, 0, ChatDraft(frozenset({1}), "dm to 1"))
    v0 = visible_state_for(s, 0)
    v1 = visible_state_for(s, 1)
    v2 = visible_state_for(s, 2)
    # Player 0 sees both (own messages).
    assert {m.body for m in v0["round_chat_so_far"]} == {"public test", "dm to 1"}
    # Player 1 sees both (broadcast + DM addressed to them).
    assert {m.body for m in v1["round_chat_so_far"]} == {"public test", "dm to 1"}
    # Player 2 sees only the public broadcast.
    assert {m.body for m in v2["round_chat_so_far"]} == {"public test"}


def test_current_round_phase_in_view() -> None:
    from foedus.core import GameConfig
    from foedus.mapgen import generate_map
    from foedus.resolve import initial_state

    cfg = GameConfig(num_players=2, seed=42)
    s = initial_state(cfg, generate_map(2, seed=42))
    v = visible_state_for(s, 0)
    assert v["current_round_phase"] == "negotiation"
