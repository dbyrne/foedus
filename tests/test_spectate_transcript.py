"""Tests for foedus/spectate/transcript.py -- parsing transcript_game{g}.md
(as written by scripts/foedus_llm_diplomat_run.py::render_transcript) into
per-turn stance/intent structures for the replay theater (View 2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from foedus.spectate.transcript import parse_transcript

FIXTURE = """\
# Foedus LLM Diplomat transcript — LLM seats 0, 1

Final scores: {0: 4.0, 1: 3.0, 2: 3.0, 3: 2.0}
Eliminated: [3]
Winners: [0]
Détente reached: False

## Turn 1
- p0 stance: p1=ally, p2=neutral, p3=hostile
  - declared u0 -> Move(dest=9) (visible_to=public)
  - declared u1 -> Support(target=u5) (visible_to=[1, 2])
- p1 stance: p0=ally
- p2 stance: (none)

## Turn 2
- p0 stance: p1=ally
  - declared u0 -> Hold (visible_to=public)
- p1 stance: (none)

## Betrayals observed
- turn 2: p1 declared u3 -> Move(dest=9), actually Hold

## Pact breaches observed
- turn 2: p2 broke pact #1 (pledged u4 -> Support(target=u2, require_dest=9), actually Hold)

## Final reputation (public)
- p0: 0 intent / 0 pact / 0 total
- p1: 1 intent / 0 pact / 1 total
- p2: 0 intent / 1 pact / 1 total
"""

FIXTURE_NO_EVENTS = """\
# Foedus LLM Diplomat transcript — LLM seat 0

Final scores: {0: 2.0, 1: 2.0}
Eliminated: []
Winners: [0, 1]
Détente reached: True

## Turn 1
- p0 stance: (none)
- p1 stance: (none)

## Betrayals observed
(none)

## Pact breaches observed
(none)

## Final reputation (public)
- p0: 0 intent / 0 pact / 0 total
- p1: 0 intent / 0 pact / 0 total
"""


def test_parse_transcript_header_fields() -> None:
    parsed = parse_transcript(FIXTURE)
    assert parsed["final_scores"] == {0: 4.0, 1: 3.0, 2: 3.0, 3: 2.0}
    assert parsed["eliminated"] == [3]
    assert parsed["winners"] == [0]
    assert parsed["detente_reached"] is False


def test_parse_transcript_turns_and_stances() -> None:
    parsed = parse_transcript(FIXTURE)
    assert [t["turn"] for t in parsed["turns"]] == [1, 2]
    turn1 = parsed["turns"][0]
    assert turn1["declarations"][0]["stance"] == {1: "ally", 2: "neutral", 3: "hostile"}
    assert turn1["declarations"][1]["stance"] == {0: "ally"}
    assert turn1["declarations"][2]["stance"] == {}


def test_parse_transcript_intents_with_orders_and_visibility() -> None:
    parsed = parse_transcript(FIXTURE)
    turn1 = parsed["turns"][0]
    intents = turn1["declarations"][0]["intents"]
    assert intents[0] == {
        "unit_id": 0,
        "order": {"type": "Move", "dest": 9},
        "visible_to": None,
    }
    assert intents[1] == {
        "unit_id": 1,
        "order": {"type": "Support", "target": 5, "require_dest": None},
        "visible_to": [1, 2],
    }


def test_parse_transcript_hold_order() -> None:
    parsed = parse_transcript(FIXTURE)
    turn2 = parsed["turns"][1]
    assert turn2["declarations"][0]["intents"][0]["order"] == {"type": "Hold"}


def test_parse_transcript_support_with_require_dest() -> None:
    parsed = parse_transcript(FIXTURE)
    breach = parsed["pact_breaches"][0]
    assert breach["pledged_order"] == {
        "type": "Support", "target": 2, "require_dest": 9,
    }
    assert breach["actual_order"] == {"type": "Hold"}


def test_parse_transcript_betrayals() -> None:
    parsed = parse_transcript(FIXTURE)
    assert parsed["betrayals"] == [
        {
            "turn": 2,
            "betrayer": 1,
            "unit_id": 3,
            "declared_order": {"type": "Move", "dest": 9},
            "actual_order": {"type": "Hold"},
        }
    ]


def test_parse_transcript_pact_breaches() -> None:
    parsed = parse_transcript(FIXTURE)
    assert parsed["pact_breaches"] == [
        {
            "turn": 2,
            "breacher": 2,
            "pact_id": 1,
            "pledged_unit": 4,
            "pledged_order": {"type": "Support", "target": 2, "require_dest": 9},
            "actual_order": {"type": "Hold"},
        }
    ]


def test_parse_transcript_reputation() -> None:
    parsed = parse_transcript(FIXTURE)
    assert parsed["reputation"] == {
        0: {"intent_breaches": 0, "pact_breaches": 0, "total": 0},
        1: {"intent_breaches": 1, "pact_breaches": 0, "total": 1},
        2: {"intent_breaches": 0, "pact_breaches": 1, "total": 1},
    }


def test_parse_transcript_no_events_sections_are_empty_lists() -> None:
    parsed = parse_transcript(FIXTURE_NO_EVENTS)
    assert parsed["betrayals"] == []
    assert parsed["pact_breaches"] == []
    assert parsed["detente_reached"] is True
    assert parsed["winners"] == [0, 1]


def test_parse_transcript_roundtrips_a_real_generated_transcript() -> None:
    """Sanity check against the actual render_transcript output (not just a
    hand-authored fixture matching the documented format)."""
    import json

    from foedus.agents.llm.client import StubLLMClient
    from foedus.agents.llm.diplomat import LLMDiplomat

    import foedus_llm_diplomat_run as harness

    def factory():
        responses = [
            json.dumps({"press": {"stance": {1: "ally"}, "intents": []},
                        "pacts": {"propose": [], "accept": []}}),
            json.dumps({"orders": {}}),
        ] * 3
        return LLMDiplomat(client=StubLLMClient(responses))

    _sweep, _telemetry, final_state, _agent = harness.run_one_llm_game(
        game_id=0, seed=1, llm_seat=0,
        heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
        max_turns=3,
        llm_agent_factory=factory,
    )
    text = harness.render_transcript(final_state, llm_seat=0)
    parsed = parse_transcript(text)
    assert parsed["final_scores"] == dict(final_state.final_scores())
    assert parsed["eliminated"] == sorted(final_state.eliminated)
    assert len(parsed["turns"]) == len(final_state.press_history)
    assert parsed["turns"][0]["declarations"][0]["stance"] == {1: "ally"}
