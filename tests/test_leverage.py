"""Bundle 4 — directional leverage and combat-bonus tests.

Trust ledger semantics:
- aid_given[(A, B)] is cumulative tokens A has successfully spent on B.
- leverage(A, B) = aid_given[A, B] - aid_given[B, A] (signed).
- leverage_bonus(A, B) = min(LEV_BONUS_MAX, leverage // LEV_RATIO) when leverage > 0.
- The combat bonus applies to A's Move strength when targeting a hex
  owned by B (or containing B's unit).
- Permanent: no decay across turns; only reciprocation defuses it.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    AidSpend,
    GameState,
    Hold,
    Move,
    Press,
    Stance,
    Unit,
)
from foedus.press import (
    finalize_round,
    signal_done,
    submit_aid_spends,
    submit_press_tokens,
)

from tests.helpers import line_map, make_state


def _setup() -> GameState:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)],
                   num_players=2, max_turns=99)
    s = replace(s, aid_tokens={0: 5, 1: 5})
    # Mutual-ALLY archived press, so aid spends are eligible.
    s = replace(s, press_history=[{
        0: Press(stance={1: Stance.ALLY}, intents=[]),
        1: Press(stance={0: Stance.ALLY}, intents=[]),
    }])
    return s


def _ally_press(s: GameState, p: int, others: list[int]) -> GameState:
    return submit_press_tokens(
        s, p,
        Press(stance={q: Stance.ALLY for q in others}, intents=[]),
    )


def test_leverage_bonus_zero_at_baseline() -> None:
    s = _setup()
    assert s.leverage(0, 1) == 0
    assert s.leverage_bonus(0, 1) == 0


def test_leverage_accumulates_on_landed_aid() -> None:
    s = _setup()
    spend = AidSpend(target_unit=1)
    s = submit_aid_spends(s, 0, [spend])
    s = _ally_press(s, 0, [1])
    s = _ally_press(s, 1, [0])
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.aid_given[(0, 1)] == 1
    assert s.leverage(0, 1) == 1
    assert s.leverage(1, 0) == -1


def test_leverage_persists_across_turns() -> None:
    """No decay: leverage is permanent until reciprocated."""
    s = _setup()
    spend = AidSpend(target_unit=1)
    s = submit_aid_spends(s, 0, [spend])
    s = _ally_press(s, 0, [1])
    s = _ally_press(s, 1, [0])
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    initial_lev = s.leverage(0, 1)
    # Run 5 more turns with no further aid.
    for _ in range(5):
        s = _ally_press(s, 0, [1])
        s = _ally_press(s, 1, [0])
        s = signal_done(s, 0)
        s = signal_done(s, 1)
        s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.leverage(0, 1) == initial_lev


def test_leverage_reciprocation_zeros_balance() -> None:
    """If B aids A back equally, leverage(A, B) returns to 0."""
    s = _setup()
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_aid_spends(s, 1, [AidSpend(target_unit=0)])
    s = _ally_press(s, 0, [1])
    s = _ally_press(s, 1, [0])
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.aid_given[(0, 1)] == 1
    assert s.aid_given[(1, 0)] == 1
    assert s.leverage(0, 1) == 0
    assert s.leverage(1, 0) == 0


def test_leverage_bonus_caps_at_max() -> None:
    """leverage_bonus(A, B) capped at config.leverage_bonus_max."""
    s = _setup()
    s = replace(s, aid_given={(0, 1): 100})
    # Default ratio=2, max=2. 100 // 2 = 50, capped at 2.
    assert s.leverage_bonus(0, 1) == 2


def test_leverage_bonus_uses_ratio() -> None:
    """leverage // ratio determines the bonus increment."""
    s = _setup()
    # ratio=2: 1 → 0, 2 → 1, 3 → 1, 4 → 2 (capped).
    s = replace(s, aid_given={(0, 1): 1})
    assert s.leverage_bonus(0, 1) == 0
    s = replace(s, aid_given={(0, 1): 2})
    assert s.leverage_bonus(0, 1) == 1
    s = replace(s, aid_given={(0, 1): 4})
    assert s.leverage_bonus(0, 1) == 2  # capped at max=2


def test_leverage_bonus_negative_returns_zero() -> None:
    """When B has more leverage on A than vice versa, A's bonus on B is 0."""
    s = _setup()
    s = replace(s, aid_given={(1, 0): 5, (0, 1): 0})
    assert s.leverage(0, 1) == -5
    assert s.leverage_bonus(0, 1) == 0


def test_leverage_combat_bonus_applied_to_attack() -> None:
    """A's Move into B's-owned hex gets +leverage_bonus(A, B) strength.

    Setup: line 0-1-2-3-4. p0 at node 0; p1 at node 4. p1 owns nodes 3, 4
    (his half of the line). Give p0 leverage(0, 1) = 4 (max bonus).
    Then p0 attacks p1 by trying to take nearest contested hex... but in
    a line map with single units, head-to-head not applicable. Let me set
    a more direct attack scenario.
    """
    m = line_map(5)
    # P0 at node 1, P1 at node 2. P1 owns node 2.
    s = make_state(m, [Unit(0, 0, 1), Unit(1, 1, 2)],
                   num_players=2, max_turns=99)
    s = replace(s, ownership={0: 0, 1: 0, 2: 1, 3: 1, 4: 1})
    s = replace(s, aid_given={(0, 1): 4})  # leverage_bonus = 2
    # P0 attacks P1's u1 at node 2; P1 holds.
    # Without leverage: p0 move_str = 1, p1 hold_str = 1; ties bounce.
    # With leverage bonus +2: p0 move_str = 3 > p1 hold_str = 1; p0 dislodges p1.
    from foedus.resolve import resolve_turn
    s_after = resolve_turn(s, {0: {0: Move(dest=2)}, 1: {1: Hold()}})
    assert 1 not in s_after.units  # u1 dislodged
    assert s_after.units[0].location == 2  # u0 advanced


def test_leverage_bonus_emits_log_line() -> None:
    """When leverage bonus fires, resolve.py logs a "leverage bonus" line.

    Required for the depth-eval framework's `leverage_bonuses_fired`
    counter (which scans state.log for the substring "leverage bonus").
    """
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 1), Unit(1, 1, 2)],
                   num_players=2, max_turns=99)
    s = replace(s, ownership={0: 0, 1: 0, 2: 1, 3: 1, 4: 1})
    s = replace(s, aid_given={(0, 1): 4})  # leverage_bonus = 2
    from foedus.resolve import resolve_turn
    s_after = resolve_turn(s, {0: {0: Move(dest=2)}, 1: {1: Hold()}})
    new_lines = [l for l in s_after.log if "leverage bonus" in l]
    assert len(new_lines) == 1, (
        f"expected exactly one 'leverage bonus' log line, got: {new_lines}"
    )
    line = new_lines[0]
    assert "+2" in line
    assert "p0" in line  # attacker
    assert "p1" in line  # target
    assert "u0" in line  # attacking unit


def test_leverage_bonus_no_log_when_zero() -> None:
    """No leverage emit when bonus is 0 — counter stays clean on baseline."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 1), Unit(1, 1, 2)],
                   num_players=2, max_turns=99)
    s = replace(s, ownership={0: 0, 1: 0, 2: 1, 3: 1, 4: 1})
    # No aid_given → no leverage → no bonus → no emit.
    from foedus.resolve import resolve_turn
    s_after = resolve_turn(s, {0: {0: Move(dest=2)}, 1: {1: Hold()}})
    assert not any("leverage bonus" in l for l in s_after.log)
