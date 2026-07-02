"""Détente reset on HARMFUL betrayal (Bundle 4 B5, harm-typed 2026-07-02).

`config.betrayal_resets_detente` (default True) resets `mutual_ally_streak` to
0 whenever a harm-typed betrayal is observed this turn. Post-reciprocity-model,
"betrayal" means harm (Primitive A): declaring ALLY while grabbing NEUTRAL land
is no longer a reset trigger — only actually dislodging/capturing from a
committed ally is. This keeps the anti-"détente by lying" fix pointed at real
aggression while letting a genuinely peaceful mutual-ALLY table build toward
the collective victory.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Intent,
    Move,
    Press,
    Stance,
    Support,
    Unit,
)
from foedus.press import finalize_round, signal_done, submit_press_tokens

from tests.helpers import harm_map


def _setup() -> GameState:
    """harm_map, 2 players, détente threshold 2. p0: u0@n0 + u2@n2; p1: u1@n1
    (+ safe home n3). p0 can dislodge p1's u1 via Move(u0->n1)+Support(u2)."""
    m = harm_map()
    ownership = {n: None for n in m.nodes}
    for node, player in m.home_assignments.items():
        ownership[node] = player
    ownership[1] = 1
    units = [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)]
    for u in units:
        ownership[u.location] = u.owner
    cfg = GameConfig(num_players=2, max_turns=99, build_period=999,
                     detente_threshold=2)
    return GameState(
        turn=0, map=m, units={u.id: u for u in units}, ownership=ownership,
        scores={0: 0.0, 1: 0.0}, eliminated=set(), next_unit_id=3, config=cfg,
    )


def _mutual_ally(s: GameState, intents0=None, intents1=None) -> GameState:
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY},
                                        intents=intents0 or []))
    s = submit_press_tokens(s, 1, Press(stance={0: Stance.ALLY},
                                        intents=intents1 or []))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    return s


_STAB = {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()}}
_PEACE = {0: {0: Hold(), 2: Hold()}, 1: {1: Hold()}}


def test_harmful_betrayal_resets_streak() -> None:
    s = _setup()
    # Turn 1: mutual ALLY, peaceful -> streak climbs to 1.
    s = _mutual_ally(s)
    s = finalize_round(s, _PEACE)
    assert s.mutual_ally_streak == 1
    # Turn 2: still declares mutual ALLY, but p0 stabs p1 (harmful) -> reset.
    s = _mutual_ally(s, intents0=[
        Intent(unit_id=0, declared_order=Hold(), visible_to=None)])
    s = finalize_round(s, _STAB)
    assert s.mutual_ally_streak == 0


def test_harmless_deviation_does_not_reset_streak() -> None:
    """Declaring a Move intent then Holding harms nobody -> no reset. A
    peaceful mutual-ALLY table keeps building toward détente."""
    s = _setup()
    for _ in range(2):
        s = _mutual_ally(s, intents0=[
            Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)])
        s = finalize_round(s, _PEACE)
    assert s.mutual_ally_streak == 2
    assert s.detente_reached  # genuine peace reaches the collective victory


def test_reset_disabled_keeps_streak_despite_harm() -> None:
    s = _setup()
    s = replace(s, config=replace(s.config, betrayal_resets_detente=False))
    s = _mutual_ally(s, intents0=[
        Intent(unit_id=0, declared_order=Hold(), visible_to=None)])
    s = finalize_round(s, _STAB)
    # Harmful betrayal happened, but reset is disabled -> streak still climbs.
    assert s.mutual_ally_streak == 1
