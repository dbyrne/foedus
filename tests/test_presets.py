"""Tests for foedus.presets — Phase 0a (F3): a conflict-forcing config
preset so playtests don't default into the peaceful-land-grab config the
4-agent playtest hit (abundant neutral centers, max_turns=7 -> units never
made contact within the game length)."""

from __future__ import annotations

from foedus.core import Archetype, GameConfig
from foedus.mapgen import generate_map
from foedus.presets import conflict_forcing_config
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
