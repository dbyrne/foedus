"""Bundle 6 — prompt rendering tests."""

from __future__ import annotations

from foedus.core import GameConfig
from foedus.game_server.render import render_chat_prompt, render_commit_prompt
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


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
