"""Smoke tests for the redesigned core types."""
from foedus.core import (
    DoneCleared,
    Hold,
    Intent,
    IntentRevised,
    Move,
    Support,
    SupportLapsed,
    SupportRound,
)


def test_support_default_no_pin():
    s = Support(target=7)
    assert s.target == 7
    assert s.require_dest is None


def test_support_with_pin():
    s = Support(target=7, require_dest=42)
    assert s.require_dest == 42


def test_support_round_construction():
    r = SupportRound(turn=3, gave=frozenset({0}), received=frozenset({1}))
    assert r.turn == 3
    assert r.gave == frozenset({0})
    assert r.received == frozenset({1})


def test_intent_revised_construction():
    intent = Intent(unit_id=1, declared_order=Move(dest=5), visible_to=None)
    ev = IntentRevised(turn=2, player=0, intent=intent, previous=None,
                      visible_to=None)
    assert ev.previous is None


def test_support_lapsed_reason_literal():
    ev = SupportLapsed(turn=1, supporter=2, target=3, reason="geometry_break")
    assert ev.reason == "geometry_break"


def test_done_cleared_construction():
    ev = DoneCleared(turn=1, player=0, source_player=2, source_unit=5)
    assert ev.source_unit == 5
