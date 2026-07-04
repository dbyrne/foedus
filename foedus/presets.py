"""Named GameConfig presets.

Phase 0a (F3): the default GameConfig (max_turns=25, map_radius=3) has
enough room for players to expand peacefully all game long without ever
touching. The 4-agent playtest used a *smaller* max_turns=7 with the
default map_radius and still saw zero combat, zero eliminations, and zero
betrayals through turn 4 — abundant neutral centers meant nobody needed to
contest anything. `conflict_forcing_config` trades map space for turn count
to force units into contact well before the game ends, while giving the
détente/scoring track enough turns to matter.

See docs/superpowers/specs/2026-07-01-foedus-phase0-arena-fixes-design.md
section 0a (F3) and the playtest findings it cites.
"""

from __future__ import annotations

from foedus.core import Archetype, GameConfig


def conflict_forcing_config(num_players: int = 4,
                            seed: int | None = None) -> GameConfig:
    """A tighter, longer game that forces early contact between players.

    - `max_turns=15` (vs default 25): enough turns for the alliance/détente
      track to matter without dragging on.
    - `map_radius=2` (vs default 3): shrinks the map so players' expansion
      frontiers meet, instead of spreading out across a mostly-neutral
      board for the whole game.
    - `archetype=CONTINENTAL_SWEEP`: dense connectivity (0-1 cells removed,
      ~50% supply density) — the playtest's own config — so scarcity, not
      terrain chokepoints, is what drives contact.
    """
    return GameConfig(
        num_players=num_players,
        max_turns=15,
        seed=seed,
        archetype=Archetype.CONTINENTAL_SWEEP,
        map_radius=2,
    )


def ruleset_v1(num_players: int = 4,
               seed: int | None = None) -> GameConfig:
    """The standard competition board (ruleset v1).

    The single source of truth for the arena/gym board once ratified, so
    every experiment and match accumulates on one ladder. Parameters were
    picked empirically from cheap heuristic sweeps; see
    docs/design/2026-07-04-ruleset-v1.md for the evidence and trade-offs.

    - `num_players=4`: highest skill discrimination on the standard map and
      the lowest elimination-variance; 5-6 seats measurably *lose*
      discrimination to crowding at this radius (§6.2).
    - `max_turns=12`: discrimination saturates by turn 8 (§6.3), but 12 is
      the shortest length that keeps the détente/alliance win condition
      live — `detente_threshold = 4 + num_players = 8` needs turns beyond it
      to be reachable, giving a turns 8-12 race-to-peace window (§7.3).
      15 turns adds cost and elimination noise but no discrimination.
    - `map_radius=2` (19 hexes): decisive — radius 2 recovers the true skill
      ladder perfectly (Kendall tau = 1.0); radius 1 (7 hexes) is
      elimination-dominated and cannot (tau ~ 0) (§6.1).
    - `archetype=CONTINENTAL_SWEEP`: dense connectivity so scarcity, not
      terrain, drives contact — same rationale as `conflict_forcing_config`.

    The détente threshold is left at the engine default (`4 + num_players`,
    table-size-scaled) rather than overridden (§7.3). Match-level structure
    (seat rotation, sealed seeds, games-per-match, roster, rating) is a
    protocol layered *around* this config, not fields on it — the engine
    stays a pure state-transition core.
    """
    return GameConfig(
        num_players=num_players,
        max_turns=12,
        seed=seed,
        archetype=Archetype.CONTINENTAL_SWEEP,
        map_radius=2,
    )
