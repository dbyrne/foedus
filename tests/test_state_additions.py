"""Tests for new GameConfig and GameState fields added in Press v0."""

from __future__ import annotations

from foedus.core import GameConfig, Phase
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def test_gameconfig_has_new_fields_with_defaults() -> None:
    cfg = GameConfig()
    assert cfg.detente_threshold == 5
    assert cfg.stagnation_cost == 1.0
    assert cfg.chat_char_cap == 500
    assert cfg.round_timer_seconds == 60.0


def test_gameconfig_peace_threshold_aliases_detente_threshold() -> None:
    """Backward compat: passing peace_threshold sets detente_threshold."""
    cfg = GameConfig(peace_threshold=7)
    assert cfg.detente_threshold == 7


def test_gameconfig_explicit_detente_threshold_takes_precedence() -> None:
    cfg = GameConfig(detente_threshold=3)
    assert cfg.detente_threshold == 3


def test_gamestate_has_new_press_fields_after_initial_state() -> None:
    cfg = GameConfig(num_players=3, seed=42)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    assert s.phase == Phase.NEGOTIATION
    assert s.mutual_ally_streak == 0
    assert s.press_history == []
    assert s.chat_history == []
    assert s.betrayals == {}
    assert s.round_chat == []
    assert s.round_press_pending == {}
    assert s.round_done == set()
