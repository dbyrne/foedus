"""Griefing scenario: a player rapidly toggles intent. Auto-clears only
fire for direct dependents; round still terminates when everyone settles.
"""
from foedus.core import Hold, Intent, Move, Press, Support
from foedus.press import (
    is_round_complete,
    signal_done,
    submit_press_tokens,
)
from tests.helpers import build_state_with_units


def test_repeated_revisions_dont_hang_round():
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},
        ownership={0: 0, 1: 1, 2: 2},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=3,
    )
    # P0 supports P1; P2 is unrelated.
    s = submit_press_tokens(s, 0, Press(
        stance={},
        intents=[Intent(unit_id=0, declared_order=Support(target=1),
                        visible_to=None)],
    ))
    s = submit_press_tokens(s, 2, Press(stance={}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 2)

    # P1 toggles intent 50 times. P0 auto-clears each time; P2 stays done.
    for i in range(50):
        order = Move(dest=2) if i % 2 == 0 else Hold()
        s = submit_press_tokens(s, 1, Press(
            stance={},
            intents=[Intent(unit_id=1, declared_order=order, visible_to=None)],
        ))
        # P0 must redo signal_done each time.
        s = signal_done(s, 0)
        assert 2 in s.round_done  # bystander unaffected

    # Eventually P1 commits.
    s = signal_done(s, 1)
    assert is_round_complete(s)
