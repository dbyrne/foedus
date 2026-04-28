"""Tests for new GameConfig and GameState fields added in Press v0."""

from __future__ import annotations

from foedus.core import GameConfig, Phase
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def test_gameconfig_has_new_fields_with_defaults() -> None:
    cfg = GameConfig()
    # detente_threshold default scales with table size: 4 + num_players.
    # Default num_players=4, so the resolved default is 8. (Sonnet playtest.)
    assert cfg.detente_threshold == 8
    # Bundle 2 default change: stagnation_cost defaults to 0.0 (disabled)
    # because the hold-or-dislodge ownership rule made the penalty perverse.
    assert cfg.stagnation_cost == 0.0
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


def test_gameconfig_archetype_default_is_uniform() -> None:
    from foedus.core import Archetype, GameConfig
    cfg = GameConfig()
    assert cfg.archetype == Archetype.UNIFORM


def test_gameconfig_map_radius_default_is_3() -> None:
    from foedus.core import GameConfig
    cfg = GameConfig()
    assert cfg.map_radius == 3


def test_gameconfig_explicit_archetype() -> None:
    from foedus.core import Archetype, GameConfig
    cfg = GameConfig(archetype=Archetype.HIGHLAND_PASS)
    assert cfg.archetype == Archetype.HIGHLAND_PASS


def test_gameconfig_explicit_map_radius() -> None:
    from foedus.core import GameConfig
    cfg = GameConfig(map_radius=5)
    assert cfg.map_radius == 5


def test_gameconfig_archetype_string_coerced_to_enum() -> None:
    """When constructed from JSON-decoded data (e.g. game_server /games POST),
    archetype arrives as a string. __post_init__ coerces to the enum so
    downstream dispatchers (generate_map) work without type-checking."""
    from foedus.core import Archetype, GameConfig
    cfg = GameConfig(archetype="highland_pass")
    assert cfg.archetype == Archetype.HIGHLAND_PASS
    cfg2 = GameConfig(archetype="riverlands")
    assert cfg2.archetype == Archetype.RIVERLANDS


def test_gameconfig_invalid_archetype_string_raises() -> None:
    """Invalid archetype strings should raise ValueError at construction."""
    import pytest
    from foedus.core import GameConfig
    with pytest.raises(ValueError):
        GameConfig(archetype="not_an_archetype")


def test_gameconfig_full_json_roundtrip_via_kwargs() -> None:
    """Regression: simulating the game_server /games POST path. Config
    arrives as a dict-of-strings-and-ints from JSON; GameConfig(**dict)
    should accept it and produce a workable config."""
    import json
    from foedus.core import Archetype, GameConfig
    from foedus.mapgen import generate_map
    raw = json.loads('{"num_players": 4, "seed": 42, "archetype": "highland_pass"}')
    cfg = GameConfig(**raw)
    assert cfg.archetype == Archetype.HIGHLAND_PASS
    # And generate_map should accept the resulting config without crashing.
    m = generate_map(cfg.num_players, seed=cfg.seed,
                     archetype=cfg.archetype, map_radius=cfg.map_radius)
    from foedus.core import NodeType
    assert NodeType.MOUNTAIN in m.node_types.values()
