"""Toggle wiring + end-to-end accumulation for the reciprocation ledger on
LLMDiplomat.

The ledger is OFF by default (back-compat); it turns on via a constructor arg
or the FOEDUS_LLM_RECIP_LEDGER env var (arg wins). When ON, the memory
accumulates across turns from the seat's own fogged views and its own orders,
and later-turn negotiation prompts carry the running counts — proven here by
driving a real game through play_game with a deterministic StubLLMClient.
"""

from __future__ import annotations

import json

from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat
from foedus.core import GameConfig
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import initial_state

from tests.helpers import simple_two_player_state


def _negotiate_json(**overrides) -> str:
    body = {"press": {"stance": {}, "intents": []},
            "pacts": {"propose": [], "accept": []}}
    body.update(overrides)
    return json.dumps(body)


def _orders_json(orders: dict) -> str:
    return json.dumps({"orders": orders})


# --- toggle wiring -----------------------------------------------------------


def test_ledger_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_RECIP_LEDGER", raising=False)
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=StubLLMClient([_negotiate_json()]))
    diplomat.choose_press(state, 0)
    user = diplomat.decision_log[0]["prompt"]["user"]
    assert "RECIPROCATION RECORD" not in user


def test_ledger_on_via_constructor_arg(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_RECIP_LEDGER", raising=False)
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=StubLLMClient([_negotiate_json()]),
                           recip_ledger=True)
    diplomat.choose_press(state, 0)
    user = diplomat.decision_log[0]["prompt"]["user"]
    assert "RECIPROCATION RECORD" in user


def test_ledger_on_via_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_RECIP_LEDGER", "1")
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=StubLLMClient([_negotiate_json()]))
    diplomat.choose_press(state, 0)
    user = diplomat.decision_log[0]["prompt"]["user"]
    assert "RECIPROCATION RECORD" in user


def test_constructor_arg_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_RECIP_LEDGER", "1")
    state = simple_two_player_state()
    diplomat = LLMDiplomat(client=StubLLMClient([_negotiate_json()]),
                           recip_ledger=False)
    diplomat.choose_press(state, 0)
    user = diplomat.decision_log[0]["prompt"]["user"]
    assert "RECIPROCATION RECORD" not in user


# --- end-to-end accumulation through play_game -------------------------------


def _two_turn_two_player_state() -> "object":
    cfg = GameConfig(num_players=2, seed=7, max_turns=2, map_radius=2,
                     build_period=999, detente_threshold=0)
    m = generate_map(2, seed=7, archetype=cfg.archetype, map_radius=cfg.map_radius)
    return initial_state(cfg, m)


def test_accumulated_counts_appear_in_later_turn_prompt(monkeypatch) -> None:
    """Over two turns: p1 declares ALLY toward p0 each turn; p0 declares
    HOSTILE toward p1 on turn 0. At p0's turn-1 negotiation, the ledger the
    seat sees carries the running counts observed from turn 0."""
    monkeypatch.delenv("FOEDUS_LLM_RECIP_LEDGER", raising=False)
    state = _two_turn_two_player_state()

    p0_turn0_neg = _negotiate_json(press={"stance": {"1": "hostile"}, "intents": []})
    p0_other_neg = _negotiate_json()
    p1_neg = _negotiate_json(press={"stance": {"0": "ally"}, "intents": []})
    hold = _orders_json({})

    p0 = LLMDiplomat(client=StubLLMClient([p0_turn0_neg, hold, p0_other_neg, hold]),
                     recip_ledger=True)
    p1 = LLMDiplomat(client=StubLLMClient([p1_neg, hold, p1_neg, hold]))

    final = play_game({0: p0, 1: p1}, state=state)
    assert final.is_terminal()

    turn1_neg = next(
        r for r in p0.decision_log
        if r["phase"] == "negotiate" and r["turn"] == 1
    )
    user = turn1_neg["prompt"]["user"]
    assert "RECIPROCATION RECORD" in user
    # observed turn-0's ally declaration from p1 toward me:
    assert "declared ALLY toward you on 1 of 1" in user
    # own prior-stance recall: I declared hostile toward p1 on turn 0:
    assert "prior stances toward them" in user
    assert "hostile" in user


def test_off_arm_prompt_has_no_section_across_the_game(monkeypatch) -> None:
    """The OFF arm never emits the section on any turn (back-compat guard for
    the paired comparison)."""
    monkeypatch.delenv("FOEDUS_LLM_RECIP_LEDGER", raising=False)
    state = _two_turn_two_player_state()
    hold = _orders_json({})
    p0 = LLMDiplomat(client=StubLLMClient([_negotiate_json(), hold,
                                           _negotiate_json(), hold]))
    p1 = LLMDiplomat(client=StubLLMClient([_negotiate_json(), hold,
                                           _negotiate_json(), hold]))
    play_game({0: p0, 1: p1}, state=state)
    for r in p0.decision_log:
        assert "RECIPROCATION RECORD" not in r["prompt"]["user"]
