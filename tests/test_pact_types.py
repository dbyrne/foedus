"""Tests for the F5 Pact types in core.py (Phase 0b, binding joint intents)."""

from __future__ import annotations

from foedus.core import (
    Hold,
    Move,
    Pact,
    PactBreach,
    PactProposal,
    PactStatus,
    PactTerm,
    Support,
)


def test_pact_status_enum() -> None:
    assert PactStatus.PROPOSED.value == "proposed"
    assert PactStatus.ACCEPTED.value == "accepted"


def test_pact_term_constructible() -> None:
    t = PactTerm(player=0, unit_id=3, declared_order=Move(dest=8))
    assert t.player == 0
    assert t.unit_id == 3
    assert t.declared_order == Move(dest=8)


def test_pact_term_is_frozen() -> None:
    t = PactTerm(player=0, unit_id=3, declared_order=Hold())
    try:
        t.player = 1  # type: ignore[misc]
    except (AttributeError, Exception):
        return
    raise AssertionError("PactTerm should be frozen")


def test_pact_constructible() -> None:
    terms = (
        PactTerm(player=0, unit_id=1, declared_order=Move(dest=8)),
        PactTerm(player=2, unit_id=5, declared_order=Support(target=1)),
    )
    p = Pact(
        pact_id=0,
        proposer=0,
        counterparty=2,
        terms=terms,
        status=PactStatus.PROPOSED,
        proposed_turn=3,
    )
    assert p.pact_id == 0
    assert p.proposer == 0
    assert p.counterparty == 2
    assert p.terms == terms
    assert p.status == PactStatus.PROPOSED
    assert p.proposed_turn == 3


def test_pact_is_frozen() -> None:
    p = Pact(pact_id=0, proposer=0, counterparty=1, terms=(),
             status=PactStatus.PROPOSED, proposed_turn=0)
    try:
        p.status = PactStatus.ACCEPTED  # type: ignore[misc]
    except (AttributeError, Exception):
        return
    raise AssertionError("Pact should be frozen")


def test_pact_breach_constructible() -> None:
    term = PactTerm(player=0, unit_id=1, declared_order=Move(dest=8))
    b = PactBreach(turn=4, pact_id=2, breacher=0, term=term,
                   actual_order=Hold())
    assert b.turn == 4
    assert b.pact_id == 2
    assert b.breacher == 0
    assert b.term == term
    assert b.actual_order == Hold()


def test_pact_proposal_constructible() -> None:
    terms = (PactTerm(player=0, unit_id=1, declared_order=Hold()),)
    prop = PactProposal(counterparty=2, terms=terms)
    assert prop.counterparty == 2
    assert prop.terms == terms
