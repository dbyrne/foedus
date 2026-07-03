"""Tests for the reciprocation-record prompt section (render toggle +
neutrality + back-compat).

Two hard requirements from the experiment brief are pinned here:
  * TOGGLE / BACK-COMPAT: with no memory passed, the negotiation prompt is
    unchanged (the section never appears) — both experiment arms are the same
    code, one toggle apart.
  * NEUTRALITY (experiment integrity): the section is factual bookkeeping only.
    It must not contain advice, judgement, or leading language — we are testing
    whether the MODEL acts on information, not whether a prompt can smuggle in
    the conclusion.
"""

from __future__ import annotations

from foedus.core import Press, Stance
from foedus.fog import visible_state_for
from foedus.agents.llm.memory import ReciprocationMemory
from foedus.agents.llm.render import (
    render_negotiation_prompt,
    render_reciprocation_record,
)

from tests.helpers import simple_two_player_state

# Leading / judgemental / advisory language the neutral ledger must never emit.
# (`ally`/`neutral`/`hostile` are the game's own stance vocabulary and are fine.)
LEADING_WORDS = [
    "exploit", "beware", "punish", "freerid", "betray", "cheat", "distrust",
    "suspicious", "loyal", "enemy", "deserve", "retaliat", "backstab", "liar",
    "untrustworthy", "consider", "recommend", "advise", "warn", "reward",
    "trust", "danger", "should", "must ", "ought", "coalition", "gang",
]


def _populated_memory() -> ReciprocationMemory:
    """A memory where opponent p1 declared ALLY toward me on 3 of 3 turns and
    I declared HOSTILE toward them each turn (never supported them)."""
    mem = ReciprocationMemory()
    for turn in (1, 2, 3):
        outbound = [Press(stance={1: Stance.HOSTILE}, intents=[])
                    for _ in range(turn)]
        view = {"public_stance_matrix": {1: {0: "ally"}},
                "your_outbound_press": outbound}
        mem.observe_view(view, me=0, turn=turn)
    return mem


def test_ledger_off_by_default_section_absent() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_negotiation_prompt(state, view, 0)
    assert "RECIPROCATION RECORD" not in user


def test_ledger_none_equals_default_omission() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, a = render_negotiation_prompt(state, view, 0)
    _, b = render_negotiation_prompt(state, view, 0, recip_memory=None)
    assert a == b


def test_ledger_on_appends_section_with_counts() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    mem = _populated_memory()
    _, user = render_negotiation_prompt(state, view, 0, recip_memory=mem)
    assert "RECIPROCATION RECORD" in user
    # all three stance counts are surfaced (symmetric, no single-lens emphasis).
    assert "ally 3, neutral 0, hostile 0" in user
    assert "you gave Support to their units on 0 turns" in user


def test_ledger_section_is_neutral_factual_bookkeeping() -> None:
    mem = _populated_memory()
    text = "\n".join(render_reciprocation_record(mem, 0)).lower()
    for word in LEADING_WORDS:
        assert word not in text, f"leading/judgemental word leaked: {word!r}"


def test_ledger_section_reports_my_own_prior_stances() -> None:
    mem = _populated_memory()
    text = "\n".join(render_reciprocation_record(mem, 0))
    # own prior-stance recall: I declared hostile toward them every prior turn.
    assert "prior stances toward them" in text
    assert "hostile" in text


def test_ledger_empty_memory_renders_neutral_placeholder() -> None:
    mem = ReciprocationMemory()
    lines = render_reciprocation_record(mem, 0)
    text = "\n".join(lines).lower()
    assert "reciprocation record" in text
    for word in LEADING_WORDS:
        assert word not in text
