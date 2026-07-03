"""Tests for foedus.eval.memory_metrics — the reciprocation-experiment
scorecard extractor.

All inputs here are scripted (no model, no files needed for the unit-level
functions), so the metrics are pinned against known supports/stances. The
extractor reads only self-contained JSON already emitted by the run harness:
decision-log raw_response (the model's own JSON, parsed with the diplomat's
own extractor) plus the decision's prompt for unit ownership, and the
sweep/telemetry records for outcomes and parse-fail.
"""

from __future__ import annotations

import json

from foedus.eval.memory_metrics import (
    aggregate_scorecard,
    game_scorecard,
    parse_visible_owners,
    stance_toward_targets,
    supports_targeting_freerider,
)


def _orders_prompt(units: list[tuple[int, int, int]]) -> str:
    """Render a VISIBLE UNITS block. `units` = [(unit_id, owner, me_seat)]."""
    lines = ["VISIBLE UNITS:"]
    for uid, owner, me in units:
        marker = "(YOURS)" if owner == me else f"(player {owner})"
        lines.append(f"  u{uid} at node 3 {marker}")
    return "\n".join(lines)


# --- ownership parsing -------------------------------------------------------


def test_parse_visible_owners_reads_yours_and_players() -> None:
    prompt = _orders_prompt([(5, 3, 0), (2, 0, 0), (8, 1, 0)])
    owners = parse_visible_owners(prompt, me_seat=0)
    assert owners == {5: 3, 2: 0, 8: 1}


# --- subsidy: LLM supports whose target is a freerider unit -------------------


def test_supports_targeting_freerider_counts_only_freerider_targets() -> None:
    owners = {5: 3, 6: 1, 7: 0}
    raw = json.dumps({"orders": {
        "10": {"type": "Support", "target": 5},   # -> p3 (freerider): counts
        "11": {"type": "Support", "target": 6},   # -> p1: not freerider
        "12": {"type": "Support", "target": 7},   # -> p0 (me): not freerider
    }})
    assert supports_targeting_freerider(raw, owners, {3}) == 1


def test_supports_ignores_non_support_orders() -> None:
    owners = {5: 3}
    raw = json.dumps({"orders": {
        "10": {"type": "Hold"},
        "11": {"type": "Move", "dest": 5},
    }})
    assert supports_targeting_freerider(raw, owners, {3}) == 0


def test_supports_unknown_target_owner_skipped() -> None:
    owners = {5: 3}
    raw = json.dumps({"orders": {"10": {"type": "Support", "target": 99}}})
    assert supports_targeting_freerider(raw, owners, {3}) == 0


def test_supports_unparseable_raw_is_zero() -> None:
    assert supports_targeting_freerider("<client error: boom>", {5: 3}, {3}) == 0


# --- stance toward the freerider ---------------------------------------------


def test_stance_toward_targets_reads_explicit_stances() -> None:
    raw = json.dumps({"press": {"stance": {"3": "hostile", "1": "ally"}}})
    assert stance_toward_targets(raw, {3}) == {3: "hostile"}


def test_stance_toward_targets_missing_is_omitted() -> None:
    raw = json.dumps({"press": {"stance": {"1": "ally"}}})
    assert stance_toward_targets(raw, {3}) == {}


# --- per-game scorecard ------------------------------------------------------


def _neg_record(seat: int, turn: int, stance: dict) -> dict:
    return {
        "turn": turn, "phase": "negotiate", "player": seat,
        "prompt": {"system": "", "user": ""},
        "raw_response": json.dumps({"press": {"stance": stance}}),
        "fell_back": False,
    }


def _orders_record(seat: int, turn: int, prompt_units, orders) -> dict:
    return {
        "turn": turn, "phase": "orders", "player": seat,
        "prompt": {"system": "", "user": _orders_prompt(prompt_units)},
        "raw_response": json.dumps({"orders": orders}),
        "fell_back": False,
    }


def test_game_scorecard_margin_and_winner() -> None:
    # seats 0,1 = LLM; seat 2 = DishonestCooperator (freerider).
    sweep = {
        "game_id": 0, "seed": 0,
        "agents": ["LLMDiplomat", "LLMDiplomat", "DishonestCooperator"],
        "llm_seats": [0, 1],
        "final_scores": [7.0, 9.0, 20.0],
        "winners": [2],
    }
    telemetry = {"per_seat": {"0": {"n_decisions": 4, "parse_fail_count": 1},
                              "1": {"n_decisions": 4, "parse_fail_count": 0}}}
    sc = game_scorecard(sweep, telemetry, {0: [], 1: []},
                        freerider_names={"DishonestCooperator"})
    assert sc["freerider_seats"] == [2]
    assert sc["llm_seats"] == [0, 1]
    assert sc["freerider_score"] == 20.0
    assert sc["llm_mean_score"] == 8.0
    assert sc["margin"] == 12.0
    assert sc["freerider_won"] is True


def test_game_scorecard_subsidy_and_stance_trajectory() -> None:
    sweep = {
        "game_id": 0, "seed": 0,
        "agents": ["LLMDiplomat", "LLMDiplomat", "DishonestCooperator"],
        "llm_seats": [0, 1],
        "final_scores": [7.0, 9.0, 20.0],
        "winners": [2],
    }
    telemetry = {"per_seat": {"0": {"n_decisions": 4, "parse_fail_count": 0},
                              "1": {"n_decisions": 4, "parse_fail_count": 0}}}
    # Unit 5 is owned by the freerider (seat 2). Seat 0 supports it on turn 1.
    decisions = {
        0: [
            _neg_record(0, 0, {"2": "hostile"}),
            _neg_record(0, 1, {"2": "ally"}),
            _orders_record(0, 1, [(5, 2, 0), (9, 0, 0)],
                           {"9": {"type": "Support", "target": 5}}),
        ],
        1: [
            _neg_record(1, 0, {"2": "hostile"}),
            _neg_record(1, 1, {"2": "neutral"}),
        ],
    }
    sc = game_scorecard(sweep, telemetry, decisions,
                        freerider_names={"DishonestCooperator"})
    assert sc["subsidy"] == 1
    traj = {t["turn"]: t for t in sc["stance_trajectory"]}
    # turn 0: both LLM seats declared the freerider hostile.
    assert traj[0]["hostile"] == 2
    assert traj[0]["ally"] == 0
    # turn 1: one flipped to ally, one to neutral.
    assert traj[1]["ally"] == 1
    assert traj[1]["neutral"] == 1
    assert traj[1]["hostile"] == 0


# --- aggregate across games --------------------------------------------------


def test_aggregate_scorecard_win_rate_and_mean_margin() -> None:
    g0 = {"freerider_won": True, "margin": 12.0, "subsidy": 3,
          "freerider_seats": [2], "llm_seats": [0, 1]}
    g1 = {"freerider_won": False, "margin": -2.0, "subsidy": 1,
          "freerider_seats": [2], "llm_seats": [0, 1]}
    agg = aggregate_scorecard([g0, g1])
    assert agg["n_games"] == 2
    assert agg["freerider_win_rate"] == 0.5
    assert agg["mean_margin"] == 5.0
    assert agg["total_subsidy"] == 4
