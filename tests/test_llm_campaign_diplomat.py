"""Campaign-mode wiring on LLMDiplomat: the persistent-instance behaviors that
cross-game memory needs.

  * toggle: OFF by default; on via constructor arg or FOEDUS_LLM_CAMPAIGN (arg
    wins). OFF -> byte-identical single-game behavior (no PRIOR GAMES section).
  * decoupling: campaign mode accumulates the reciprocation memory it needs to
    build the record WITHOUT rendering the within-game RECIPROCATION RECORD
    block (that block stays gated on recip_ledger).
  * reset_for_new_game: clears within-game caches / decision_log / reciprocation
    memory (turn numbering restarts each game -> stale caches would leak a prior
    game's decision) while KEEPING the cross-game memory.
  * finalize_game: builds the neutral record, makes ONE self-note LLM call
    (degrading to "" on failure), appends the GameRecord, and does NOT log that
    call into decision_log.
"""

from __future__ import annotations

import json

from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat

from tests.helpers import simple_two_player_state


def _negotiate_json(**overrides) -> str:
    body = {"press": {"stance": {}, "intents": []},
            "pacts": {"propose": [], "accept": []}}
    body.update(overrides)
    return json.dumps(body)


# --- toggle wiring -----------------------------------------------------------


def test_campaign_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_CAMPAIGN", raising=False)
    d = LLMDiplomat(client=StubLLMClient([_negotiate_json()]))
    assert d._campaign_memory is None
    d.choose_press(simple_two_player_state(), 0)
    assert "PRIOR GAMES" not in d.decision_log[0]["prompt"]["user"]


def test_campaign_on_via_constructor_arg(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_CAMPAIGN", raising=False)
    d = LLMDiplomat(client=StubLLMClient([_negotiate_json()]), campaign=True)
    assert d._campaign_memory is not None


def test_campaign_on_via_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_CAMPAIGN", "1")
    d = LLMDiplomat(client=StubLLMClient([_negotiate_json()]))
    assert d._campaign_memory is not None


def test_constructor_arg_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_CAMPAIGN", "1")
    d = LLMDiplomat(client=StubLLMClient([_negotiate_json()]), campaign=False)
    assert d._campaign_memory is None


# --- accumulation / rendering decoupling -------------------------------------


def test_campaign_accumulates_recip_without_rendering_block(monkeypatch) -> None:
    """Campaign mode (recip ledger OFF) must build a live reciprocation memory
    for the record, yet NOT render the within-game RECIPROCATION RECORD block."""
    monkeypatch.delenv("FOEDUS_LLM_CAMPAIGN", raising=False)
    monkeypatch.delenv("FOEDUS_LLM_RECIP_LEDGER", raising=False)
    d = LLMDiplomat(client=StubLLMClient([_negotiate_json()]), campaign=True)
    assert d._memory is not None  # accumulator exists
    d.choose_press(simple_two_player_state(), 0)
    user = d.decision_log[0]["prompt"]["user"]
    assert "RECIPROCATION RECORD" not in user   # not rendered
    # game 1 has no prior records, so no PRIOR GAMES section either
    assert "PRIOR GAMES" not in user


# --- reset_for_new_game ------------------------------------------------------


def test_reset_clears_within_game_state_keeps_campaign(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_CAMPAIGN", raising=False)
    state = simple_two_player_state()
    d = LLMDiplomat(
        client=StubLLMClient([_negotiate_json(), _negotiate_json()]),
        campaign=True,
    )
    d.choose_press(state, 0)
    assert len(d.decision_log) == 1
    assert d._negotiation_cache  # populated

    # Populate cross-game memory so we can prove reset keeps it.
    d.finalize_game(state, 0, seed=0, game_index=0)
    assert len(d._campaign_memory) == 1

    d.reset_for_new_game()
    assert d.decision_log == []
    assert d._negotiation_cache == {}
    assert d._orders_cache == {}
    assert len(d._campaign_memory) == 1  # cross-game memory survives

    # Cache was cleared: the same (turn, player) call re-invokes the client
    # (consumes the second scripted response instead of returning a stale one).
    d.choose_press(state, 0)
    assert len(d.decision_log) == 1


# --- finalize_game -----------------------------------------------------------


def test_finalize_game_appends_record_with_verbatim_self_note(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_CAMPAIGN", raising=False)
    note = "p1 declared ally every turn but never backed my units; ally early."
    d = LLMDiplomat(client=StubLLMClient([note]), campaign=True)
    d.finalize_game(simple_two_player_state(), 0, seed=3, game_index=1)
    assert len(d._campaign_memory) == 1
    rec = d._campaign_memory.all()[0]
    assert rec.self_note == note          # stored verbatim
    assert rec.facts.seed == 3
    assert rec.facts.game_index == 1
    # the self-note LLM call is NOT a game decision -> never logged
    assert d.decision_log == []


def test_finalize_game_self_note_failure_degrades_to_empty(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_CAMPAIGN", raising=False)
    # Empty stub -> complete() raises -> _complete catches -> note "".
    d = LLMDiplomat(client=StubLLMClient([]), campaign=True)
    d.finalize_game(simple_two_player_state(), 0, seed=0, game_index=0)
    assert len(d._campaign_memory) == 1
    assert d._campaign_memory.all()[0].self_note == ""


def test_finalize_game_noop_when_campaign_off(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_CAMPAIGN", raising=False)
    d = LLMDiplomat(client=StubLLMClient([_negotiate_json()]))
    # No campaign memory, no self-note call, no crash.
    d.finalize_game(simple_two_player_state(), 0, seed=0, game_index=0)
    assert d._campaign_memory is None
    assert d.decision_log == []


def test_prior_games_section_appears_after_finalize_and_reset(monkeypatch) -> None:
    """End-to-end: game 1 finalize records a note; after reset, game 2's
    negotiation prompt carries the PRIOR GAMES section with that note."""
    monkeypatch.delenv("FOEDUS_LLM_CAMPAIGN", raising=False)
    state = simple_two_player_state()
    note = "p1 is a steady partner; open with ally."
    d = LLMDiplomat(
        client=StubLLMClient([note, _negotiate_json()]), campaign=True
    )
    d.finalize_game(state, 0, seed=0, game_index=0)
    d.reset_for_new_game()
    d.choose_press(state, 0)
    user = d.decision_log[0]["prompt"]["user"]
    assert "PRIOR GAMES" in user
    assert note in user
