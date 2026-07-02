"""Tests for F5 pact rendering helpers in foedus.render_common."""

from __future__ import annotations

from foedus.core import Hold, Move, Support
from foedus.core import PactTerm
from foedus.press import accept_pact, propose_pact
from foedus.render_common import render_active_pacts, render_pact_breach_ledger

from tests.helpers import line_map, make_state
from foedus.core import Unit


def _state():
    m = line_map(5)
    units = [Unit(0, 0, 0), Unit(1, 1, 4), Unit(2, 2, 2),
             Unit(3, 0, 1), Unit(4, 1, 3)]
    return make_state(m, units, num_players=3)


def _terms():
    return (
        PactTerm(player=0, unit_id=3, declared_order=Move(dest=2)),
        PactTerm(player=1, unit_id=4, declared_order=Support(target=3)),
    )


# --- render_active_pacts ----------------------------------------------------


def test_render_active_pacts_none() -> None:
    s = _state()
    out = render_active_pacts(s, 0)
    assert "ACTIVE PACTS" in out
    assert "none" in out.lower()


def test_render_active_pacts_proposed_shows_pending_acceptance() -> None:
    s = _state()
    s = propose_pact(s, 0, 1, _terms())
    out = render_active_pacts(s, 0)
    assert "pact #0" in out
    assert "proposed" in out.lower()
    # awaiting the counterparty's acceptance
    assert "p1" in out
    # both terms rendered with owner + unit + order
    assert "u3" in out and "u4" in out
    assert "Move(dest=2$1)" in out  # order_to_str with state annotation


def test_render_active_pacts_accepted_status() -> None:
    s = _state()
    s = propose_pact(s, 0, 1, _terms())
    s = accept_pact(s, 0, 1)
    out = render_active_pacts(s, 1)
    assert "accepted" in out.lower()


def test_render_active_pacts_hidden_from_third_party() -> None:
    s = _state()
    s = propose_pact(s, 0, 1, _terms())
    out = render_active_pacts(s, 2)
    assert "pact #0" not in out
    assert "none" in out.lower()


# --- render_pact_breach_ledger ----------------------------------------------


def test_render_pact_breach_ledger_none() -> None:
    s = _state()
    out = render_pact_breach_ledger(s, 0)
    assert "PACT BREACH" in out
    assert "none" in out.lower()


def test_render_pact_breach_ledger_lists_breach() -> None:
    from foedus.core import PactBreach
    s = _state()
    breach = PactBreach(
        turn=3, pact_id=0, breacher=1,
        term=PactTerm(player=1, unit_id=4, declared_order=Support(target=3)),
        actual_order=Hold(),
    )
    s.pact_breaches[0] = [breach]
    out = render_pact_breach_ledger(s, 0)
    assert "turn 3" in out
    assert "p1" in out
    assert "pact #0" in out
    assert "u4" in out
    assert "Hold" in out
