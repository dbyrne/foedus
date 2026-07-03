"""Tests for foedus.agents.llm.campaign_memory — the CROSS-game record a
persistent LLMDiplomat carries between the games of a campaign.

Fog-legality is structural: every neutral fact is built from the seat's own
fogged view (public `scores`, observer-gated `your_pacts`/`your_pact_breaches`/
`your_betrayals`) plus its within-game ReciprocationMemory (itself fog-legal).
These tests pin the counting/rank semantics, the last-N cap, and the
serialization round-trip against scripted inputs (no engine, no model).
"""

from __future__ import annotations

import json

from foedus.core import (
    BetrayalObservation, Hold, Intent, Move, Pact, PactBreach, PactStatus,
    PactTerm, Support,
)
from foedus.agents.llm.memory import ReciprocationMemory
from foedus.agents.llm.campaign_memory import (
    CampaignMemory,
    GameFacts,
    GameRecord,
    OpponentGameFacts,
    build_game_facts,
)


def _view(scores, *, pacts=None, pact_breaches=None, betrayals=None) -> dict:
    return {
        "scores": scores,
        "your_pacts": pacts or [],
        "your_pact_breaches": pact_breaches or [],
        "your_betrayals": betrayals or [],
    }


# --- scores + rank -----------------------------------------------------------


def test_build_game_facts_scores_and_rank() -> None:
    view = _view({0: 10.0, 1: 5.0, 2: 20.0, 3: 8.0})
    gf = build_game_facts(ReciprocationMemory(), view, me=0, seed=7, game_index=1)
    assert gf.seed == 7
    assert gf.game_index == 1
    assert gf.my_seat == 0
    assert gf.n_players == 4
    assert gf.final_scores == {0: 10.0, 1: 5.0, 2: 20.0, 3: 8.0}
    # Only p2 (20) scores above me (10) -> rank 2.
    assert gf.my_rank == 2


def test_rank_is_one_when_top() -> None:
    view = _view({0: 30.0, 1: 5.0, 2: 20.0})
    gf = build_game_facts(ReciprocationMemory(), view, me=0, seed=0, game_index=0)
    assert gf.my_rank == 1


def test_rank_ties_do_not_demote() -> None:
    # A tie for the top does not push me below rank 1 (strictly-greater count).
    view = _view({0: 20.0, 1: 20.0, 2: 5.0})
    gf = build_game_facts(ReciprocationMemory(), view, me=0, seed=0, game_index=0)
    assert gf.my_rank == 1


# --- per-opponent facts from the within-game reciprocation memory ------------


def test_per_opponent_facts_from_recip_memory() -> None:
    mem = ReciprocationMemory()
    rec = mem.record(1)
    rec.turns_observed = 5
    rec.ally_toward_me = 3
    rec.turns_i_supported_them = 2
    rec.their_support_intent_toward_me = 1
    view = _view({0: 10.0, 1: 8.0})
    gf = build_game_facts(mem, view, me=0, seed=0, game_index=0)
    of = gf.per_opponent[1]
    assert of.turns_observed == 5
    assert of.ally_toward_me == 3
    assert of.my_supports_of_them == 2
    assert of.their_support_intent_toward_me == 1
    assert of.pact_with_me is False
    assert of.breach_involving_me is False


def test_opponent_with_no_recip_record_is_all_zero() -> None:
    # p1 was never observed (no record). It still appears (it's a seat) with
    # zeroed counts, and reading it must not mutate the memory.
    mem = ReciprocationMemory()
    view = _view({0: 10.0, 1: 8.0})
    gf = build_game_facts(mem, view, me=0, seed=0, game_index=0)
    assert gf.per_opponent[1].ally_toward_me == 0
    assert mem.opponents() == []


# --- pact / breach involvement (from the final fogged view) ------------------


def test_pact_and_breach_involvement() -> None:
    accepted = Pact(
        pact_id=1, proposer=0, counterparty=2,
        terms=(PactTerm(0, 9, Hold()),), status=PactStatus.ACCEPTED, proposed_turn=1,
    )
    breach = PactBreach(
        turn=2, pact_id=5, breacher=1, term=PactTerm(1, 4, Hold()),
        actual_order=Move(dest=3),
    )
    betrayal = BetrayalObservation(
        turn=3, betrayer=3, intent=Intent(4, Hold(), None), actual_order=Move(dest=2),
    )
    view = _view(
        {0: 10.0, 1: 8.0, 2: 12.0, 3: 6.0},
        pacts=[accepted], pact_breaches=[breach], betrayals=[betrayal],
    )
    gf = build_game_facts(ReciprocationMemory(), view, me=0, seed=0, game_index=0)
    assert gf.per_opponent[2].pact_with_me is True     # accepted pact partner
    assert gf.per_opponent[1].breach_involving_me is True   # broke a pact with me
    assert gf.per_opponent[3].breach_involving_me is True   # betrayed an intent to me
    assert gf.per_opponent[1].pact_with_me is False
    assert gf.per_opponent[3].pact_with_me is False


def test_proposed_but_unaccepted_pact_is_not_counted() -> None:
    proposed = Pact(
        pact_id=1, proposer=0, counterparty=2,
        terms=(PactTerm(0, 9, Hold()),), status=PactStatus.PROPOSED, proposed_turn=1,
    )
    view = _view({0: 10.0, 1: 8.0, 2: 12.0}, pacts=[proposed])
    gf = build_game_facts(ReciprocationMemory(), view, me=0, seed=0, game_index=0)
    assert gf.per_opponent[2].pact_with_me is False


# --- last-N cap --------------------------------------------------------------


def _facts(idx: int) -> GameFacts:
    return GameFacts(
        game_index=idx, seed=idx, my_seat=0, my_rank=1, n_players=2,
        final_scores={0: 1.0, 1: 0.0}, per_opponent={},
    )


def test_campaign_memory_len_and_all() -> None:
    cm = CampaignMemory()
    assert len(cm) == 0
    cm.append(GameRecord(_facts(0), "note0"))
    cm.append(GameRecord(_facts(1), "note1"))
    assert len(cm) == 2
    assert [r.self_note for r in cm.all()] == ["note0", "note1"]


def test_campaign_memory_recent_caps_and_orders_oldest_first() -> None:
    cm = CampaignMemory(cap=3)
    for i in range(5):
        cm.append(GameRecord(_facts(i), f"note{i}"))
    recent = cm.recent()
    # last 3, oldest-first
    assert [r.facts.game_index for r in recent] == [2, 3, 4]


def test_campaign_memory_recent_empty() -> None:
    assert CampaignMemory().recent() == []


# --- serialization round-trip (persistence + audit) --------------------------


def test_game_record_roundtrip_through_json() -> None:
    gf = GameFacts(
        game_index=2, seed=3, my_seat=1, my_rank=2, n_players=4,
        final_scores={0: 8.0, 1: 11.0, 2: 9.0, 3: 23.0},
        per_opponent={
            0: OpponentGameFacts(6, 2, 1, 0, True, False),
            2: OpponentGameFacts(6, 0, 0, 1, False, True),
            3: OpponentGameFacts(6, 5, 4, 0, False, False),
        },
    )
    rec = GameRecord(gf, self_note="p3 never reciprocates; coordinate early.")
    blob = json.dumps(rec.to_dict())
    back = GameRecord.from_dict(json.loads(blob))
    assert back == rec
    # int seat keys survive the JSON string-key round-trip
    assert back.facts.final_scores == gf.final_scores
    assert back.facts.per_opponent[2].breach_involving_me is True
    assert back.self_note == rec.self_note
