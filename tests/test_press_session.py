"""Bundle 6 — GameSession press-flow integration tests."""

from __future__ import annotations

import pytest

from foedus.agents.heuristic import HeuristicAgent
from foedus.core import GameConfig, Press
from foedus.game_server.session import GameSession, SeatSpec
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def _build_session(num_llm: int = 2, num_agents: int = 2,
                   seed: int = 42, max_turns: int = 7) -> GameSession:
    """Build a session with `num_llm` human (LLM) seats and `num_agents`
    HeuristicAgent seats."""
    n = num_llm + num_agents
    cfg = GameConfig(num_players=n, max_turns=max_turns, seed=seed)
    m = generate_map(n, seed=seed)
    state = initial_state(cfg, m)
    seats = {}
    agents = {}
    for p in range(num_llm):
        seats[p] = SeatSpec(type="human", name=f"llm{p}")
    for p in range(num_llm, n):
        seats[p] = SeatSpec(type="agent", name=f"h{p}",
                            kind="foedus.agents.heuristic.HeuristicAgent")
        agents[p] = HeuristicAgent()
    return GameSession(game_id="g1", state=state, seats=seats,
                        agents=agents)


def test_init_round_marks_agent_seats_chat_and_round_done() -> None:
    """Agent seats should be in chat_done and round_done after
    init_round; LLM seats should not."""
    s = _build_session()
    assert s.state.chat_done == {2, 3}, \
        f"expected {{2,3}}, got {s.state.chat_done}"
    assert s.state.round_done == {2, 3}, \
        f"expected {{2,3}}, got {s.state.round_done}"


def test_submit_press_chat_marks_player_chat_done() -> None:
    s = _build_session()
    result = s.submit_press_chat(0, None)
    assert 0 in s.state.chat_done
    assert result["chat_phase_complete"] is False  # P1 still pending


def test_submit_press_chat_with_draft_records_message() -> None:
    s = _build_session()
    result = s.submit_press_chat(
        0, {"recipients": None, "body": "Hello all"}
    )
    assert 0 in s.state.chat_done
    assert any(m.body == "Hello all" for m in s.state.round_chat)
    assert result["message_dropped"] is False


def test_submit_press_chat_double_signal_raises() -> None:
    s = _build_session()
    s.submit_press_chat(0, None)
    with pytest.raises(ValueError):
        s.submit_press_chat(0, None)


def test_submit_press_chat_complete_when_all_llm_signaled() -> None:
    s = _build_session()
    s.submit_press_chat(0, None)
    result = s.submit_press_chat(1, None)
    assert result["chat_phase_complete"] is True


def test_submit_press_commit_blocked_until_chat_phase_complete() -> None:
    s = _build_session()
    s.submit_press_chat(0, None)
    # P1 hasn't signaled chat-done. Commit must reject.
    with pytest.raises(ValueError, match="chat phase not complete"):
        s.submit_press_commit(0, Press(stance={}, intents=[]), {})


def test_submit_press_commit_advances_round_when_all_committed() -> None:
    s = _build_session()
    s.submit_press_chat(0, None)
    s.submit_press_chat(1, None)
    # Now both LLMs commit.
    s.submit_press_commit(0, Press(stance={}, intents=[]), {})
    result = s.submit_press_commit(1, Press(stance={}, intents=[]), {})
    assert result["round_advanced"] is True
    # Turn should have advanced from 0 to 1.
    assert s.state.turn == 1


def test_full_round_resets_chat_done_for_next_round() -> None:
    s = _build_session()
    for p in (0, 1):
        s.submit_press_chat(p, None)
    s.submit_press_commit(0, Press(stance={}, intents=[]), {})
    s.submit_press_commit(1, Press(stance={}, intents=[]), {})
    # After advance, chat_done should be reset to just the agent seats
    # (init_round re-marked them).
    assert s.state.chat_done == {2, 3}
    assert s.state.round_done == {2, 3}
