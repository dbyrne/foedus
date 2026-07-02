"""Bundle 6 — prompt rendering tests."""

from __future__ import annotations

from dataclasses import replace

from foedus.core import BetrayalObservation, GameConfig, Intent, Hold, Move, Unit
from foedus.game_server.render import render_chat_prompt, render_commit_prompt
from foedus.mapgen import generate_map
from foedus.resolve import initial_state

from tests.helpers import line_map, make_state, triangle_map


def test_chat_prompt_includes_turn_and_player_header() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert "TURN 1/7" in out
    assert "YOU ARE PLAYER 0" in out
    assert "PHASE: NEGOTIATION (chat round)" in out


def test_chat_prompt_lists_active_opponents() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert "Active opponents: [1, 2, 3]" in out


def test_chat_prompt_shows_supply_count_and_streak() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert "Your supply count: 1" in out
    assert "Mutual-ally streak: 0/" in out


def test_chat_prompt_includes_response_schema() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert '"recipients"' in out and '"body"' in out


def test_commit_prompt_includes_map_and_units() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_commit_prompt(s, 0)
    assert "MAP" in out
    assert "VISIBLE UNITS:" in out
    assert "YOUR UNITS" in out


def test_commit_prompt_lists_legal_orders() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_commit_prompt(s, 0)
    # P0's home unit is u0; it should be listed with at least one Hold option.
    assert "u0 at node" in out
    assert "[0] Hold" in out


def test_commit_prompt_includes_combined_schema() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_commit_prompt(s, 0)
    assert '"press"' in out and '"orders"' in out
    assert '"stance"' in out and '"intents"' in out


# --- Phase 0a (F1/F2): arena legibility ------------------------------------


def test_commit_prompt_states_capture_rule() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_commit_prompt(s, 0)
    assert "CAPTURE RULE" in out
    assert "Holding" in out


def test_commit_prompt_shows_supply_value_on_map() -> None:
    m = line_map(3)
    m = replace(m, supply_values={1: 2})
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    out = render_commit_prompt(s, 0)
    assert "1$2" in out


def test_commit_prompt_shows_income_ledger() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    out = render_commit_prompt(s, 0)
    assert "INCOME:" in out
    assert "Build turns:" in out


def test_commit_prompt_annotates_support_target_owner_and_location() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
                   num_players=3)
    out = render_commit_prompt(s, 0)
    assert "Support(target=u1 [P1 @ n1])" in out
    assert "Support(target=u2 [P2 @ n2])" in out


def test_commit_prompt_shows_adjacency_table() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
                   num_players=3)
    out = render_commit_prompt(s, 0)
    assert "ADJACENCY" in out


def test_commit_prompt_shows_turn_calendar() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2,
                   build_period=3, max_turns=7)
    out = render_commit_prompt(s, 0)
    assert "TURN CALENDAR" in out
    assert "[3, 6]" in out


def test_commit_prompt_shows_betrayal_ledger() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
                   num_players=3)
    obs = BetrayalObservation(
        turn=1, betrayer=1,
        intent=Intent(unit_id=1, declared_order=Hold(), visible_to=None),
        actual_order=Move(dest=0),
    )
    s = replace(s, betrayals={0: [obs]})
    out = render_commit_prompt(s, 0)
    assert "BETRAYAL LEDGER" in out
    assert "p1=1" in out


def test_chat_prompt_states_capture_rule() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert "CAPTURE RULE" in out


def test_chat_prompt_shows_turn_calendar() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert "TURN CALENDAR" in out
