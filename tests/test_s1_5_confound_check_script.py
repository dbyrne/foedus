"""Integration test for scripts/foedus_s1_5_confound_check.py's file-reading
glue (M-foedus-s1-5-confound-check).

The deep logic (replay correctness, legality classification, counterfactual
re-resolution, clean-call filtering) is unit-tested in
tests/test_resolution_replay.py and tests/test_clean_call_subset.py against
synthetic fixtures; this covers only what the script adds: reading a
campaign_plan.json + sweep.jsonl + per-seat decision-log out-dir (the same
shape scripts/foedus_s1_autopsy.py consumes) end-to-end into `build_report`.

The out-dir fixture here is built from a REAL tiny live game (driven once
through play_game with a deterministic scripted client, exactly like
test_resolution_replay.py's equivalence test) rather than hand-written JSON
snippets, since `build_report` actually replays every turn through the real
engine and would raise on a decision log that doesn't cover a turn the
replayed game reaches.
"""

from __future__ import annotations

import json
import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import pytest

import foedus_s1_5_confound_check as confound_check  # noqa: E402
from foedus.eval._coverage import CoverageError  # noqa: E402

from foedus.agents.heuristics import ROSTER
from foedus.agents.llm.diplomat import LLMDiplomat
from foedus.agents.llm.render import NEGOTIATION_SYSTEM_PROMPT
from foedus.core import Archetype, GameConfig
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def _write_synthetic_run(tmp_path):
    seed = 909
    num_players = 3
    max_turns = 2
    archetype = Archetype.CONTINENTAL_SWEEP
    map_radius = 2
    llm_seats = [0, 1]
    freerider_seat = 2

    cfg = GameConfig(num_players=num_players, max_turns=max_turns, seed=seed,
                     archetype=archetype, map_radius=map_radius)
    m = generate_map(num_players, seed=seed, archetype=archetype, map_radius=map_radius)
    state = initial_state(cfg, m)

    class ScriptedClient:
        def __init__(self, player, state_box):
            self.player = player
            self._state_box = state_box

        def complete(self, system, user):
            if system == NEGOTIATION_SYSTEM_PROMPT:
                return json.dumps({"press": {"stance": {}, "intents": []},
                                   "pacts": {"propose": [], "accept": []}})
            st = self._state_box["state"]
            own = sorted(u.id for u in st.units.values() if u.owner == self.player)
            if not own:
                return json.dumps({"orders": {}})
            first = own[0]
            nbrs = sorted(st.map.neighbors(st.units[first].location))
            body = {"orders": {str(first): {"type": "Move", "dest": nbrs[0]}}} \
                if nbrs else {"orders": {}}
            return json.dumps(body)

    state_box = {"state": state}
    agents = {
        0: LLMDiplomat(client=ScriptedClient(0, state_box)),
        1: LLMDiplomat(client=ScriptedClient(1, state_box)),
        freerider_seat: ROSTER["DishonestCooperator"](),
    }

    def on_turn(prev_state, orders_by_player, new_state):
        state_box["state"] = new_state

    final_state = play_game(agents, state=state, on_turn_resolved=on_turn)

    out = tmp_path / "run"
    out.mkdir()
    (out / "campaign_plan.json").write_text(json.dumps({
        "freerider_handles": ["Golf"],
        "freerider_class": "DishonestCooperator",
        "board": {"num_players": num_players, "max_turns": max_turns,
                  "map_radius": map_radius, "archetype": archetype.value},
    }))
    sweep_row = {
        "game_id": 0, "seed": seed, "agents": ["Delta", "Echo", "Golf"],
        "llm_seats": llm_seats, "freerider_seats": [freerider_seat],
        "total_turns": final_state.turn,
        "final_scores": [final_state.scores.get(p, 0.0) for p in range(num_players)],
        "eliminated": sorted(final_state.eliminated),
    }
    (out / "sweep.jsonl").write_text(json.dumps(sweep_row) + "\n")
    for seat in llm_seats:
        with (out / f"decisions_game0_seat{seat}.jsonl").open("w") as f:
            for rec in agents[seat].decision_log:
                f.write(json.dumps(rec, default=str) + "\n")
    return out


def test_build_report_end_to_end_on_a_tiny_real_game(tmp_path):
    out = _write_synthetic_run(tmp_path)
    rep = confound_check.build_report(str(out))

    assert len(rep["per_game"]) == 1
    g0 = rep["per_game"][0]
    assert g0["integrity"]["final_scores_match"] is True
    assert g0["integrity"]["total_turns_match"] is True
    assert g0["integrity"]["fidelity_mismatch_count"] == 0
    assert g0["fidelity_mismatches"] == []

    assert rep["replay_integrity"]["all_games_score_turn_elimination_match"] is True
    assert rep["replay_integrity"]["total_fidelity_mismatches"] == 0
    assert "check1_legality_and_outcome" in rep
    assert "check2_clean_call_subset" in rep
    # Structural sanity: broad-clean can only be <= the full executed count.
    c2 = rep["check2_clean_call_subset"]
    assert c2["clean_broad"]["executed_count"] <= c2["full"]["executed_count"]
    assert c2["clean_strict"]["executed_count"] <= c2["full"]["executed_count"]


def test_build_report_raises_on_zero_records_read(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "campaign_plan.json").write_text(json.dumps({
        "freerider_handles": ["Golf"], "freerider_class": "DishonestCooperator",
        "board": {"num_players": 3, "max_turns": 2,
                  "map_radius": 2, "archetype": "continental_sweep"},
    }))
    sweep_row = {
        "game_id": 0, "seed": 909, "agents": ["Delta", "Echo", "Golf"],
        "llm_seats": [0, 1], "freerider_seats": [2],
        "total_turns": 2, "final_scores": [0.0, 0.0, 0.0], "eliminated": [],
    }
    (out / "sweep.jsonl").write_text(json.dumps(sweep_row) + "\n")
    for seat in (0, 1):
        (out / f"decisions_game0_seat{seat}.jsonl").write_text("")

    with pytest.raises(CoverageError, match="0 records read"):
        confound_check.build_report(str(out))
