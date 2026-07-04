"""View 1: the live campaign dashboard data model.

Pure function of a run-dir's on-disk files (no network, no LLM calls, no
system calls) -- see readers.py for the tolerant-of-missing-files loaders
this composes. In-flight process/system checks (e.g. counting live `claude
-p` subprocesses) are deliberately kept OUT of this module and live in the
server layer instead, so this stays a plain, fixture-testable function.
"""

from __future__ import annotations

from pathlib import Path

from foedus.spectate.board import build_turn_frames
from foedus.spectate.readers import (
    load_campaign_plan,
    load_decisions,
    load_self_notes,
    load_seed_manifest,
    load_sweep,
    load_telemetry,
    load_timing,
)


def _mean(xs: list[float]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def _seating_for(plan: dict | None, game_index: int) -> dict:
    for seating in (plan or {}).get("seatings") or []:
        if seating.get("game_index") == game_index:
            return seating
    return {}


def build_dashboard(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    plan = load_campaign_plan(run_dir)
    manifest = load_seed_manifest(run_dir)
    sweep = load_sweep(run_dir)
    timing = load_timing(run_dir)
    self_notes = load_self_notes(run_dir)

    entrants: list[str] = (plan or {}).get("entrant_identities") or []
    standings: dict[str, dict] = {
        h: {"cumulative_score": 0.0, "wins": 0} for h in entrants
    }

    games = []
    for i, sw in enumerate(sweep):
        game_index = sw.get("game_index", i)
        seating = _seating_for(plan, game_index)
        identity_by_seat = (
            seating.get("identity_by_seat") or sw.get("identity_by_seat") or []
        )
        freerider_seats = seating.get("freerider_seats") or sw.get("freerider_seats") or []
        llm_seats = seating.get("llm_seats") or sw.get("llm_seats") or []
        final_scores = sw.get("final_scores") or []
        winners = set(sw.get("winners") or [])

        by_handle_scores: dict[str, float] = {}
        for seat, score in enumerate(final_scores):
            handle = identity_by_seat[seat] if seat < len(identity_by_seat) else f"seat{seat}"
            by_handle_scores[handle] = score
            standings.setdefault(handle, {"cumulative_score": 0.0, "wins": 0})
            standings[handle]["cumulative_score"] += score
            if seat in winners:
                standings[handle]["wins"] += 1

        freerider_score = _mean([final_scores[s] for s in freerider_seats if s < len(final_scores)])
        llm_mean_score = _mean([final_scores[s] for s in llm_seats if s < len(final_scores)])
        margin = (
            freerider_score - llm_mean_score
            if freerider_score is not None and llm_mean_score is not None
            else None
        )

        decisions = load_decisions(run_dir, sw.get("game_id", game_index), llm_seats)
        frames = build_turn_frames(decisions, freerider_seats, llm_seats)
        subsidy = sum(f["subsidy"] for f in frames)
        llm_llm_supports = sum(f["llm_llm_supports"] for f in frames)

        games.append({
            "game_index": game_index,
            "game_id": sw.get("game_id", game_index),
            "by_handle_scores": by_handle_scores,
            "winners_handles": [
                identity_by_seat[s] for s in sorted(winners) if s < len(identity_by_seat)
            ],
            "freerider_score": freerider_score,
            "llm_mean_score": llm_mean_score,
            "margin": margin,
            "subsidy": subsidy,
            "llm_llm_supports": llm_llm_supports,
            "total_turns": sw.get("total_turns"),
            "detente_reached": sw.get("detente_reached"),
        })

    return {
        "match_id": (plan or {}).get("match_id"),
        "entrants": entrants,
        "num_games": (plan or {}).get("num_games", len(sweep)),
        "board": (plan or {}).get("board") or {},
        "freerider_handles": (plan or {}).get("freerider_handles") or [],
        "seed_commitment": (manifest or {}).get("commit"),
        "started_at": timing["started_at"],
        "ended_at": timing["ended_at"],
        "games_complete": len(sweep),
        "games": games,
        "standings": standings,
        "self_notes": self_notes,
    }
