"""Live-intent visibility + dependency-aware signal_done auto-clear."""
from foedus.core import (
    AidSpend,
    Hold,
    Intent,
    IntentRevised,
    Move,
    Press,
    Support,
)
from foedus.press import (
    intent_dependencies,
    signal_done,
    submit_aid_spends,
    submit_press_tokens,
)
from tests.helpers import build_state_with_units


def _two_player_adjacent_state():
    return build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )


def test_intent_revision_emits_event():
    s = _two_player_adjacent_state()
    intent = Intent(unit_id=0, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[intent]))
    assert any(
        isinstance(ev, IntentRevised) and ev.player == 0 and ev.previous is None
        for ev in s.intent_revisions
    )


def test_intent_revision_carries_previous():
    s = _two_player_adjacent_state()
    i1 = Intent(unit_id=0, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[i1]))
    i2 = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[i2]))
    revisions = [ev for ev in s.intent_revisions if ev.player == 0]
    assert revisions[-1].previous == i1
    assert revisions[-1].intent == i2


def test_dependent_done_auto_clears_on_revision():
    s = _two_player_adjacent_state()
    # P0 supports P1's unit 1.
    p0_intent = Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent]))
    # P1 declares a Move intent for unit 1.
    p1_intent = Intent(unit_id=1, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent]))
    # P0 signals done.
    s = signal_done(s, 0)
    assert 0 in s.round_done
    # P1 revises — should auto-clear P0's done flag.
    p1_intent2 = Intent(unit_id=1, declared_order=Hold(), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent2]))
    assert 0 not in s.round_done
    assert any(
        ev.player == 0 and ev.source_player == 1 and ev.source_unit == 1
        for ev in s.done_clears
    )


def test_self_revision_does_not_clear_own_done():
    s = _two_player_adjacent_state()
    p0_intent = Intent(unit_id=0, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent]))
    s = signal_done(s, 0)
    # P0 revises P0's own intent — done unaffected.
    p0_intent2 = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent2]))
    # signal_done in the existing code REJECTS submissions from done players.
    # The cleared-then-resubmit case is covered by the dependent test above.
    # This test asserts that self-revision DOESN'T trigger any clear:
    assert all(ev.player != 0 for ev in s.done_clears)


def test_unrelated_unit_revision_keeps_done_set():
    """P depends on (Q, U). Q revises a different unit V — P's done stays set."""
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},
        ownership={0: 0, 1: 1, 2: 1},  # P1 has two units (1 and 2)
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )
    p0_intent = Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent]))
    # P1 declares for unit 2 (not the one P0 depends on).
    p1_intent = Intent(unit_id=2, declared_order=Move(dest=0), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent]))
    s = signal_done(s, 0)
    # P1 revises unit 2's intent — should NOT affect P0.
    p1_intent2 = Intent(unit_id=2, declared_order=Hold(), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent2]))
    assert 0 in s.round_done


def test_no_transitive_cascade():
    """P depends on Q; Q depends on R. R revises — Q clears, P stays set."""
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},
        ownership={0: 0, 1: 1, 2: 2},
        edges={0: {1}, 1: {0, 2}, 2: {1}},
        num_players=3,
    )
    # P0 supports P1's unit 1 (P0 depends on P1).
    s = submit_press_tokens(s, 0, Press(
        stance={},
        intents=[Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)],
    ))
    # P1 supports P2's unit 2 (P1 depends on P2).
    s = submit_press_tokens(s, 1, Press(
        stance={},
        intents=[Intent(unit_id=1, declared_order=Support(target=2), visible_to=None)],
    ))
    # P2 declares for unit 2.
    s = submit_press_tokens(s, 2, Press(
        stance={},
        intents=[Intent(unit_id=2, declared_order=Move(dest=1), visible_to=None)],
    ))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    # P2 revises unit 2 — only P1 should auto-clear.
    s = submit_press_tokens(s, 2, Press(
        stance={},
        intents=[Intent(unit_id=2, declared_order=Hold(), visible_to=None)],
    ))
    assert 1 not in s.round_done  # P1 directly depends on (P2, 2) — clears
    assert 0 in s.round_done       # P0 only depends on P1, not transitive


def test_first_declaration_does_not_clear_dependent_done():
    """E3: P depends on (Q, U) via existing Support. Q declares an intent
    for U for the first time this round. P's done flag stays set."""
    s = _two_player_adjacent_state()
    # P0 declares Support of P1's unit 1 (creates dependency).
    p0_intent = Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent]))
    s = signal_done(s, 0)
    assert 0 in s.round_done
    # P1's first declaration for unit 1 — should NOT clear P0's done.
    p1_intent = Intent(unit_id=1, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent]))
    assert 0 in s.round_done, "first declaration should not auto-clear per E3"
    # IntentRevised event still emitted for visibility.
    assert any(
        ev.player == 1 and ev.previous is None and ev.intent == p1_intent
        for ev in s.intent_revisions
    )


def test_round_closes_when_all_done_after_revision():
    """A revision that triggers no auto-clears (or whose dependents weren't
    done) should still allow the round to close once all-done holds again."""
    s = _two_player_adjacent_state()
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    from foedus.press import is_round_complete
    assert is_round_complete(s)


def test_intent_retraction_emits_event_with_none_intent():
    s = _two_player_adjacent_state()
    i1 = Intent(unit_id=0, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[i1]))
    # Retract by submitting an empty intents list (no entry for unit 0).
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    retraction_events = [
        ev for ev in s.intent_revisions
        if ev.player == 0 and ev.intent is None
    ]
    assert len(retraction_events) == 1
    assert retraction_events[0].previous == i1
