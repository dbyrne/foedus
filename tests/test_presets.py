"""Tests for foedus.presets — Phase 0a (F3): a conflict-forcing config
preset so playtests don't default into the peaceful-land-grab config the
4-agent playtest hit (abundant neutral centers, max_turns=7 -> units never
made contact within the game length)."""

from __future__ import annotations

from foedus.core import Archetype, GameConfig
from foedus.mapgen import generate_map
from foedus.presets import conflict_forcing_config, ruleset_v1
from foedus.resolve import initial_state


def test_conflict_forcing_config_raises_max_turns() -> None:
    cfg = conflict_forcing_config()
    assert cfg.max_turns >= 15


def test_conflict_forcing_config_tightens_map_radius_for_scarcity() -> None:
    default_radius = GameConfig().map_radius
    cfg = conflict_forcing_config()
    assert cfg.map_radius < default_radius


def test_conflict_forcing_config_uses_continental_sweep() -> None:
    cfg = conflict_forcing_config()
    assert cfg.archetype == Archetype.CONTINENTAL_SWEEP


def test_conflict_forcing_config_detente_threshold_reachable() -> None:
    cfg = conflict_forcing_config()
    assert cfg.detente_threshold < cfg.max_turns


def test_conflict_forcing_config_propagates_num_players_and_seed() -> None:
    cfg = conflict_forcing_config(num_players=3, seed=99)
    assert cfg.num_players == 3
    assert cfg.seed == 99


def test_conflict_forcing_config_produces_playable_state_for_each_player_count() -> None:
    for n in range(2, 7):
        cfg = conflict_forcing_config(num_players=n, seed=1)
        m = generate_map(cfg.num_players, seed=cfg.seed,
                         archetype=cfg.archetype, map_radius=cfg.map_radius)
        s = initial_state(cfg, m)
        assert len(s.units) == n
        assert s.config.num_players == n


# --- ruleset_v1: the standard competition format -------------------------
# Field values are load-bearing: they must match the ratified board spec in
# docs/design/2026-07-04-ruleset-v1.md (§7.1). Change them together.

def test_ruleset_v1_board_parameters_match_the_spec() -> None:
    cfg = ruleset_v1()
    assert cfg.num_players == 4
    assert cfg.max_turns == 12
    assert cfg.map_radius == 2
    assert cfg.archetype == Archetype.CONTINENTAL_SWEEP


def test_ruleset_v1_keeps_engine_default_detente_threshold() -> None:
    # §7.3: keep the table-size-scaled engine default (4 + num_players),
    # not an override.
    cfg = ruleset_v1()
    assert cfg.detente_threshold == 4 + cfg.num_players


def test_ruleset_v1_detente_is_live_across_the_supported_table_range() -> None:
    # §6.3 / §7.3: max_turns must exceed the détente threshold with headroom
    # so the alliance win condition is reachable, not degenerate, for every
    # supported seat count.
    for n in range(2, 7):
        cfg = ruleset_v1(num_players=n)
        assert cfg.detente_threshold < cfg.max_turns


def test_ruleset_v1_propagates_num_players_and_seed() -> None:
    cfg = ruleset_v1(num_players=5, seed=123)
    assert cfg.num_players == 5
    assert cfg.seed == 123


def test_ruleset_v1_tightens_the_map_versus_default() -> None:
    # Radius 2 (19 hexes) vs the engine default radius 3 — a deliberately
    # tighter board so skill, not spread, decides games.
    assert ruleset_v1().map_radius < GameConfig().map_radius


def test_ruleset_v1_produces_a_playable_state_for_each_player_count() -> None:
    for n in range(2, 7):
        cfg = ruleset_v1(num_players=n, seed=1)
        m = generate_map(cfg.num_players, seed=cfg.seed,
                         archetype=cfg.archetype, map_radius=cfg.map_radius)
        s = initial_state(cfg, m)
        assert len(s.units) == n
        assert s.config.num_players == n
