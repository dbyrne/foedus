"""Pure metric functions over sweep JSONL records.

Each function takes a list of records (dicts as emitted by
foedus_sim_sweep.py) and returns aggregated structures suitable for
inclusion in the depth-eval JSON artifact.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Iterable


Record = dict


def rankings_from_records(records: Iterable[Record]) -> list[dict]:
    """Mean score per agent across all appearances.

    Returns a list sorted descending by mean_score, each entry:
    {"agent": str, "mean_score": float, "n_appearances": int,
     "scores": list[float]}.
    """
    scores_by_agent: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        for name, score in zip(rec["agents"], rec["final_scores"]):
            scores_by_agent[name].append(float(score))
    rows = []
    for name, scores in scores_by_agent.items():
        rows.append({
            "agent": name,
            "mean_score": sum(scores) / len(scores) if scores else 0.0,
            "n_appearances": len(scores),
            "scores": scores,
        })
    rows.sort(key=lambda r: r["mean_score"], reverse=True)
    return rows


def engagement_from_records(records: Iterable[Record]) -> dict[str, float]:
    """Per-game means for the engagement counters."""
    records = list(records)
    n = len(records) or 1
    totals = {
        "dislodgements_per_game": sum(r.get("dislodgement_count", 0) for r in records),
        "aid_spends_per_game": sum(r.get("aid_spends_count", 0) for r in records),
        "alliance_bonuses_per_game": sum(r.get("alliance_bonuses_fired", 0) for r in records),
        "combat_rewards_per_game": sum(r.get("combat_rewards_fired", 0) for r in records),
        "supporter_rewards_per_game": sum(r.get("supporter_rewards_fired", 0) for r in records),
        "betrayals_per_game": sum(r.get("betrayals_observed", 0) for r in records),
        "detente_resets_per_game": sum(r.get("detente_streak_resets", 0) for r in records),
    }
    order_totals: dict[str, int] = defaultdict(int)
    total_orders = 0
    for r in records:
        for ot, c in r.get("order_type_counts", {}).items():
            order_totals[ot] += c
            total_orders += c
    out = {k: v / n for k, v in totals.items()}
    if total_orders:
        for ot in ("Hold", "Move", "SupportMove", "SupportHold"):
            out[f"{ot.lower()}_pct"] = order_totals.get(ot, 0) / total_orders
    return out


def pairwise_winrate_from_records(records: Iterable[Record]) -> dict:
    """Pairwise winrate matrix: winrate(A,B) = P(score[A] > score[B] | both in game).

    Ties contribute 0.5 to both directions.
    Returns {"row_agents": [...], "col_agents": [...], "matrix": [[...]]}
    with None on the diagonal and where no shared games exist.
    """
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for rec in records:
        agents = rec["agents"]
        scores = rec["final_scores"]
        for i, a in enumerate(agents):
            for j, b in enumerate(agents):
                if i == j:
                    continue
                key = (a, b)
                counts[key][2] += 1
                if scores[i] > scores[j]:
                    counts[key][0] += 1
                elif scores[i] == scores[j]:
                    counts[key][1] += 1
    all_agents = sorted({a for (a, _) in counts.keys()})
    matrix = []
    for a in all_agents:
        row = []
        for b in all_agents:
            if a == b:
                row.append(None)
                continue
            wins, ties, total = counts.get((a, b), (0, 0, 0))
            if total == 0:
                row.append(None)
            else:
                row.append((wins + 0.5 * ties) / total)
        matrix.append(row)
    return {"row_agents": all_agents, "col_agents": all_agents, "matrix": matrix}


def probe_score_diff(records: Iterable[Record], subject_index: int) -> float:
    """For a fixed-seat probe: mean of (subject - mean(others)) per game."""
    diffs = []
    for rec in records:
        scores = rec["final_scores"]
        subject = scores[subject_index]
        others = [s for i, s in enumerate(scores) if i != subject_index]
        diffs.append(subject - (sum(others) / len(others)))
    return sum(diffs) / len(diffs) if diffs else 0.0


def probe_per_game_diffs(records: Iterable[Record], subject_index: int) -> list[float]:
    """Same as probe_score_diff but returns the per-game list (for bootstrap)."""
    diffs = []
    for rec in records:
        scores = rec["final_scores"]
        subject = scores[subject_index]
        others = [s for i, s in enumerate(scores) if i != subject_index]
        diffs.append(subject - (sum(others) / len(others)))
    return diffs
