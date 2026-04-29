"""Bundle 4 — détente reset on betrayal (B5).

Fixes the v1 bug where peaceful collective victory could close on a table of
all-Sycophant declaring ALLY but secretly racing for supplies (intent breaks
fired BetrayalObservations but did not interrupt the streak).

When `config.betrayal_resets_detente` is True (default), any
BetrayalObservation observed in finalize_round resets `mutual_ally_streak`
to 0. Set False to preserve v1 behavior.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    GameState,
    Hold,
    Intent,
    Move,
    Press,
    Stance,
    Unit,
)
from foedus.press import (
    finalize_round,
    signal_done,
    submit_press_tokens,
)

from tests.helpers import line_map, make_state


def _setup() -> GameState:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)],
                   num_players=2, max_turns=99,
                   detente_threshold=2)
    return s


def _ally_press(s: GameState, p: int, others: list[int],
                intents: list[Intent] | None = None) -> GameState:
    return submit_press_tokens(
        s, p,
        Press(stance={q: Stance.ALLY for q in others},
              intents=intents or []),
    )


def test_streak_resets_on_betrayal() -> None:
    """If any betrayal is observed this turn, streak resets to 0 (default behavior)."""
    s = _setup()
    # Turn 1: both players ALLY, no intents declared, no betrayal.
    s = _ally_press(s, 0, [1])
    s = _ally_press(s, 1, [0])
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.mutual_ally_streak == 1

    # Turn 2: both ALLY, but p0 declares Move intent and then Holds (betrayal).
    s = _ally_press(s, 0, [1], intents=[
        Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
    ])
    s = _ally_press(s, 1, [0])
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # Streak should reset because of the betrayal.
    assert s.mutual_ally_streak == 0


def test_streak_does_not_reset_when_disabled() -> None:
    """With betrayal_resets_detente=False, the streak continues despite betrayal."""
    s = _setup()
    s = replace(s, config=replace(s.config, betrayal_resets_detente=False))

    # Turn 1: ALLY + p0 betrays (declares Move, holds).
    s = _ally_press(s, 0, [1], intents=[
        Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
    ])
    s = _ally_press(s, 1, [0])
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # Pre-Bundle-4 behavior: streak still increments despite betrayal.
    assert s.mutual_ally_streak == 1


def test_lying_table_cannot_reach_detente() -> None:
    """All-Sycophant table (declares ALLY, breaks intents under the hood)
    no longer closes peaceful collective victory.

    Detente threshold = 2 in this setup; if the streak reset works, two
    consecutive turns of betrayal block the streak from ever climbing.
    """
    s = _setup()
    for _ in range(4):
        s = _ally_press(s, 0, [1], intents=[
            Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
        ])
        s = _ally_press(s, 1, [0], intents=[
            Intent(unit_id=1, declared_order=Move(dest=3), visible_to=None)
        ])
        s = signal_done(s, 0)
        s = signal_done(s, 1)
        s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # Despite 4 mutual-ALLY turns, every turn had betrayals → streak never grew.
    assert s.mutual_ally_streak == 0
    assert not s.detente_reached
