"""Campaign mode in scripts/foedus_llm_diplomat_run.py: play the N games of a
run SEQUENTIALLY with the SAME persistent LLMDiplomat instances (recurring
opponents), so cross-game memory carries between games.

Pinned here:
  * run_one_llm_game accepts pre-constructed agents (agents_by_seat) and reuses
    them instead of calling the factory; key mismatch is a clean error.
  * --campaign reuses instances across games, persists each seat's cross-game
    memory per game, and the accumulated records prove reuse (game 1 sees game
    0's record + self-note in its PRIOR GAMES prompt section).
  * OFF by default: no campaign files, fresh agents per game (byte-identical
    single-game behavior).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat

import foedus_llm_diplomat_run as harness


def _neg() -> str:
    return json.dumps({"press": {"stance": {}, "intents": []},
                       "pacts": {"propose": [], "accept": []}})


def _orders() -> str:
    return json.dumps({"orders": {}})


def _campaign_factory(n_games: int, max_turns: int):
    """Fresh campaign-enabled agent per factory() call, scripted for the whole
    campaign: per game `max_turns` (negotiate, orders) pairs then ONE self-note
    string. Campaign mode comes from FOEDUS_LLM_CAMPAIGN, which main() sets."""
    def factory():
        responses: list[str] = []
        for gi in range(n_games):
            responses += [_neg(), _orders()] * max_turns
            responses += [f"note-game{gi}"]
        return LLMDiplomat(client=StubLLMClient(responses))
    return factory


# --- run_one_llm_game: pre-constructed agents --------------------------------


def test_run_one_llm_game_uses_provided_agents_not_factory() -> None:
    seats = [0, 1]
    provided = {
        s: LLMDiplomat(client=StubLLMClient([_neg(), _orders()])) for s in seats
    }

    def factory():
        raise AssertionError("factory must not be called when agents provided")

    _sweep, _tel, final, result = harness.run_one_llm_game(
        game_id=0, seed=1, llm_seats=seats,
        heuristic_names=["DishonestCooperator"], max_turns=1,
        llm_agent_factory=factory, agents_by_seat=provided,
    )
    assert final.is_terminal()
    assert result[0] is provided[0] and result[1] is provided[1]


def test_run_one_llm_game_rejects_agents_by_seat_key_mismatch() -> None:
    with pytest.raises(ValueError, match="agents_by_seat"):
        harness.run_one_llm_game(
            game_id=0, seed=1, llm_seats=[0, 1],
            heuristic_names=["DishonestCooperator"], max_turns=1,
            agents_by_seat={0: LLMDiplomat(client=StubLLMClient([]))},
        )


# --- CLI --campaign ----------------------------------------------------------


def test_cli_campaign_persists_records_and_reuses_agents(tmp_path) -> None:
    out_dir = tmp_path / "out"
    rc = harness.main([
        "--num-games", "2", "--max-turns", "1",
        "--llm-seats", "0,1", "--heuristics", "DishonestCooperator",
        "--campaign", "--out-dir", str(out_dir),
    ], llm_agent_factory=_campaign_factory(n_games=2, max_turns=1))
    assert rc == 0

    # cross-game memory persisted per game per seat
    g0 = json.loads((out_dir / "campaign_memory_game0_seat0.json").read_text())
    g1 = json.loads((out_dir / "campaign_memory_game1_seat0.json").read_text())
    # Same agent reused: after game 0 -> 1 record; after game 1 -> 2 records.
    assert len(g0["records"]) == 1
    assert len(g1["records"]) == 2
    assert g0["records"][0]["self_note"] == "note-game0"

    # Game 1's negotiation prompt carries the PRIOR GAMES section with game 0's
    # neutral facts + verbatim note -> reset + cross-game render both work.
    recs = [
        json.loads(x)
        for x in (out_dir / "decisions_game1_seat0.jsonl").read_text().splitlines()
    ]
    neg = next(r for r in recs if r["phase"] == "negotiate")
    assert "PRIOR GAMES" in neg["prompt"]["user"]
    assert "note-game0" in neg["prompt"]["user"]


def test_cli_campaign_first_game_has_no_prior_section(tmp_path) -> None:
    out_dir = tmp_path / "out"
    harness.main([
        "--num-games", "2", "--max-turns", "1",
        "--llm-seats", "0,1", "--heuristics", "DishonestCooperator",
        "--campaign", "--out-dir", str(out_dir),
    ], llm_agent_factory=_campaign_factory(n_games=2, max_turns=1))
    recs = [
        json.loads(x)
        for x in (out_dir / "decisions_game0_seat0.jsonl").read_text().splitlines()
    ]
    neg = next(r for r in recs if r["phase"] == "negotiate")
    assert "PRIOR GAMES" not in neg["prompt"]["user"]


def test_cli_no_campaign_files_or_reuse_without_flag(tmp_path) -> None:
    out_dir = tmp_path / "out"
    rc = harness.main([
        "--num-games", "2", "--max-turns", "1",
        "--llm-seats", "0,1", "--heuristics", "DishonestCooperator",
        "--out-dir", str(out_dir),
    ], llm_agent_factory=_campaign_factory(n_games=2, max_turns=1))
    assert rc == 0
    assert not list(out_dir.glob("campaign_memory_*.json"))
    # No cross-game carry: game 1 starts blank (no PRIOR GAMES section).
    recs = [
        json.loads(x)
        for x in (out_dir / "decisions_game1_seat0.jsonl").read_text().splitlines()
    ]
    neg = next(r for r in recs if r["phase"] == "negotiate")
    assert "PRIOR GAMES" not in neg["prompt"]["user"]
