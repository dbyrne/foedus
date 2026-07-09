"""Integration test for scripts/foedus_s1_autopsy.py's file-reading glue
(M-foedus-s1-corpus-autopsy).

The classification rules themselves are unit-tested in
tests/test_punishment_metrics.py; this covers only what the script adds: a
tiny synthetic 2-game out-dir (campaign_plan.json + sweep.jsonl +
per-seat decisions), read end-to-end into `build_report`.
"""

from __future__ import annotations

import json
import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import foedus_s1_autopsy as autopsy  # noqa: E402


def _negotiate(turn, raw, prompt_user=""):
    return {"turn": turn, "phase": "negotiate", "prompt": {"user": prompt_user},
            "raw_response": raw, "fell_back": False}


def _orders(turn, raw, prompt_user=""):
    return {"turn": turn, "phase": "orders", "prompt": {"user": prompt_user},
            "raw_response": raw, "fell_back": False}


def _write_run(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "campaign_plan.json").write_text(json.dumps({
        "freerider_handles": ["Golf"],
    }))
    sweep_rows = [
        {"game_id": 0, "agents": ["Delta", "Echo", "Foxtrot", "Golf"],
         "llm_seats": [0, 1, 2]},
        {"game_id": 1, "agents": ["Golf", "Delta", "Echo", "Foxtrot"],
         "llm_seats": [1, 2, 3]},
    ]
    with (out / "sweep.jsonl").open("w") as f:
        for row in sweep_rows:
            f.write(json.dumps(row) + "\n")

    # game 0: freerider is seat 3; seat 0 sees + attacks its unit at node 11.
    vis = "VISIBLE UNITS:\n  u1 at node 7 (YOURS)\n  u5 at node 11 (p3)\n"
    decisions0 = [
        _negotiate(1, json.dumps({
            "press": {"stance": {"3": "hostile"}, "intents": [
                {"unit_id": 1, "declared_order": {"type": "Move", "dest": 11},
                 "visible_to": None},
            ]}, "pacts": {"propose": [], "accept": []},
        }), prompt_user=vis + "Scores: {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0}\n"),
        _orders(1, json.dumps({"orders": {"1": {"type": "Move", "dest": 11}}}),
                prompt_user=vis),
    ]
    with (out / "decisions_game0_seat0.jsonl").open("w") as f:
        for rec in decisions0:
            f.write(json.dumps(rec) + "\n")
    for seat in (1, 2):
        (out / f"decisions_game0_seat{seat}.jsonl").write_text("")

    # game 1: freerider is seat 0; no LLM decisions reference it at all.
    for seat in (1, 2, 3):
        (out / f"decisions_game1_seat{seat}.jsonl").write_text("")

    return out


def test_build_report_aggregates_across_games(tmp_path):
    out = _write_run(tmp_path)
    rep = autopsy.build_report(str(out))
    assert rep["freerider_handles"] == ["Golf"]
    assert len(rep["per_game"]) == 2

    g0 = next(g for g in rep["per_game"] if g["game_id"] == 0)
    assert g0["freerider_seat"] == 3
    assert g0["proposed_count"] == 1
    assert g0["executed_count"] == 1

    g1 = next(g for g in rep["per_game"] if g["game_id"] == 1)
    assert g1["freerider_seat"] == 0
    assert g1["proposed_count"] == 0
    assert g1["executed_count"] == 0

    assert rep["totals"]["proposed_count"] == 1
    assert rep["totals"]["executed_count"] == 1


def test_build_report_structural_subsidy_test_uses_scorecard(tmp_path):
    out = _write_run(tmp_path)
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({
        "trajectory": [
            {"game_id": 0, "llm_llm_supports": 5, "margin": -1.0, "subsidy": 2,
             "stance_hostility_frac": 0.5},
            {"game_id": 1, "llm_llm_supports": 10, "margin": 3.0, "subsidy": 0,
             "stance_hostility_frac": 0.1},
        ],
    }))
    rep = autopsy.build_report(str(out), str(scorecard))
    ss = rep["structural_subsidy_test"]
    assert ss["n_games"] == 2
    assert ss["coalition_per_game"] == [5, 10]
    assert ss["resistance_per_game"] == [1, 0]
    # every correlation the doc cites is reproducible from this one report,
    # not hand-derived out-of-band
    assert set(ss["correlations"]) == {
        "coalition_vs_resistance", "coalition_vs_margin", "coalition_vs_subsidy",
        "hostility_vs_executed", "hostility_vs_proposed",
    }
    assert ss["correlations"]["coalition_vs_resistance"] == ss["pearson_r"]


def test_build_report_omits_structural_subsidy_test_without_scorecard(tmp_path):
    out = _write_run(tmp_path)
    rep = autopsy.build_report(str(out))
    assert rep["structural_subsidy_test"] is None
