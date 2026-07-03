"""Tests for the cross-game ("PRIOR GAMES") prompt section and the self-note
prompt.

Two hard requirements mirror the within-game ledger:
  * TOGGLE / BACK-COMPAT: with no campaign memory, the negotiation prompt is
    byte-identical (the section never appears).
  * NEUTRALITY: the HARNESS-computed facts pass the leading-words denylist. The
    self-authored note is EXEMPT (model output) but must render VERBATIM — the
    render layer never edits or annotates it.
"""

from __future__ import annotations

from foedus.fog import visible_state_for
from foedus.agents.llm.campaign_memory import (
    CampaignMemory, GameFacts, GameRecord, OpponentGameFacts,
)
from foedus.agents.llm.render import (
    render_campaign_record,
    render_game_facts,
    render_negotiation_prompt,
    render_self_note_prompt,
)

from tests.helpers import simple_two_player_state

# Same neutrality bar as the within-game reciprocation ledger.
LEADING_WORDS = [
    "exploit", "beware", "punish", "freerid", "betray", "cheat", "distrust",
    "suspicious", "loyal", "enemy", "deserve", "retaliat", "backstab", "liar",
    "untrustworthy", "consider", "recommend", "advise", "warn", "reward",
    "trust", "danger", "should", "must ", "ought", "coalition", "gang",
]


def _facts(idx: int = 0, seed: int = 0) -> GameFacts:
    return GameFacts(
        game_index=idx, seed=seed, my_seat=0, my_rank=2, n_players=4,
        final_scores={0: 12.0, 1: 15.0, 2: 9.0, 3: 23.0},
        per_opponent={
            1: OpponentGameFacts(6, 3, 2, 1, True, False),
            2: OpponentGameFacts(6, 0, 0, 0, False, True),
            3: OpponentGameFacts(6, 5, 4, 0, False, False),
        },
    )


# --- neutral facts -----------------------------------------------------------


def test_render_game_facts_is_neutral() -> None:
    text = "\n".join(render_game_facts(_facts(), 0)).lower()
    for word in LEADING_WORDS:
        assert word not in text, f"leading/judgemental word leaked: {word!r}"


def test_render_game_facts_contains_counts_and_rank() -> None:
    text = "\n".join(render_game_facts(_facts(seed=5), 0))
    assert "seed 5" in text
    assert "rank 2 of 4" in text
    # per-opponent counts surfaced
    assert "3 of 6" in text            # ally-toward-you / observed turns for p1
    assert "on 2 turns" in text        # my supports of p1


# --- toggle / back-compat ----------------------------------------------------


def test_campaign_section_absent_by_default() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_negotiation_prompt(state, view, 0)
    assert "PRIOR GAMES" not in user


def test_campaign_none_equals_default_omission() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, a = render_negotiation_prompt(state, view, 0)
    _, b = render_negotiation_prompt(state, view, 0, campaign_memory=None)
    assert a == b


def test_empty_campaign_memory_renders_no_section() -> None:
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_negotiation_prompt(state, view, 0, campaign_memory=CampaignMemory())
    assert "PRIOR GAMES" not in user


def test_campaign_section_appears_with_records() -> None:
    cm = CampaignMemory()
    cm.append(GameRecord(_facts(0, seed=0), "note zero"))
    state = simple_two_player_state()
    view = visible_state_for(state, 0)
    _, user = render_negotiation_prompt(state, view, 0, campaign_memory=cm)
    assert "PRIOR GAMES" in user
    assert "note zero" in user


# --- last-3 cap --------------------------------------------------------------


def test_campaign_section_caps_at_last_three() -> None:
    cm = CampaignMemory(cap=3)
    for i in range(5):
        cm.append(GameRecord(_facts(i, seed=i), f"note{i}"))
    lines = "\n".join(render_campaign_record(cm, 0))
    # Only the last three games (seeds 2,3,4) render; the oldest two drop out.
    assert "seed 4" in lines and "seed 3" in lines and "seed 2" in lines
    assert "note0" not in lines and "note1" not in lines


# --- self-note is verbatim + exempt ------------------------------------------


def test_self_note_rendered_verbatim_even_with_loaded_words() -> None:
    # A note is the agent's OWN words — exempt from the neutrality denylist and
    # rendered EXACTLY, no editing/annotation by the harness.
    loaded = "p3 never reciprocates; punish and exploit them, coordinate early."
    cm = CampaignMemory()
    cm.append(GameRecord(_facts(0), loaded))
    lines = "\n".join(render_campaign_record(cm, 0))
    assert loaded in lines


def test_empty_self_note_renders_placeholder_not_crash() -> None:
    cm = CampaignMemory()
    cm.append(GameRecord(_facts(0), ""))
    lines = render_campaign_record(cm, 0)
    assert any("PRIOR GAMES" in ln for ln in lines)


# --- self-note prompt --------------------------------------------------------


def test_render_self_note_prompt_includes_facts_and_ask() -> None:
    system, user = render_self_note_prompt(_facts(seed=3), 0)
    assert isinstance(system, str) and isinstance(user, str)
    # The neutral facts are handed to the model...
    assert "seed 3" in user
    # ...and it is asked for a short note to its future self.
    combined = (system + user).lower()
    assert "note" in combined
    assert "80" in combined  # the word-cap instruction
