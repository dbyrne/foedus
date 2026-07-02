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
