"""Ruleset-v1 empirical-design harness — pure helpers.

Turns sim-sweep game records into the discrimination and
rating-convergence evidence that backs the standard competition format
(docs/design/2026-07-04-ruleset-v1.md).

Design notes
------------
* **Distinct-seat sampling.** A real arena match seats *distinct*
  entrants, so every seat in a game carries a unique rating identity.
  The stock sweep draws seats i.i.d. *with replacement* (two seats can
  be the same heuristic), which produces duplicate identities within a
  game — the exact case the parallel rating-identity fix owns. We sample
  *without* replacement here so downstream OpenSkill updates never see a
  duplicate identity, matching the format we are actually designing.

* **The skill ladder.** Six heuristics spanning weak -> strong, chosen
  from a 4000-game calibration at the base format so the rungs are
  monotonic in both OpenSkill mu and mean placement, with graduated gaps
  (two wide, three tight) that make format discrimination measurable.
  DishonestCooperator is the required freerider probe. The tied top
  cluster (Bandwagon / GreedyHold / TitForTat all play GreedyHold orders)
  is represented by DishonestCooperator alone so no two rungs are a
  statistical tie.

None of these helpers import foedus.rating or foedus.resolve at module
load beyond the rating API already exposed by foedus.rating.RatingSystem,
and none of them mutate engine code.
"""

from __future__ import annotations

import math
import random
from typing import Hashable, Sequence

# Weak -> strong. See module docstring for the calibration rationale.
LADDER: list[str] = [
    "Defensive",            # floor          (mu ~8.2,  win 0.0%)
    "Random",               # weak           (mu ~20.3, win 8.2%)
    "Sycophant",            # mid-low        (mu ~23.1, win 15.3%)
    "Greedy",               # mid            (mu ~25.2, win 14.4%)
    "Aggressive",           # mid-high       (mu ~29.4, win 29.5%)
    "DishonestCooperator",  # strong (req'd) (mu ~36.0, win 52.7%)
]

# The competitive band: the ladder minus its trivially-separable floor and
# ceiling. The full discrimination index is dominated by the two extremes
# (every format tells Defensive from DishonestCooperator), so measuring
# discrimination over the middle rungs is what reveals whether a format
# separates *close* skill. See doc §6.3.
MID_LADDER: list[str] = LADDER[1:-1]


# --- seat assignment ------------------------------------------------------

def distinct_seats(roster: Sequence[str], num_players: int,
                   rng: random.Random) -> list[str]:
    """Sample `num_players` *distinct* heuristics from `roster`.

    Models a real match (unique entrant per seat). The returned order is
    the seat assignment, so repeated calls with fresh draws also rotate
    which heuristic sits in which position.
    """
    if num_players < 2:
        raise ValueError(f"num_players must be >= 2, got {num_players}")
    if num_players > len(roster):
        raise ValueError(
            f"cannot seat {num_players} distinct players from a roster of "
            f"{len(roster)}"
        )
    return rng.sample(list(roster), num_players)


# --- rank extraction ------------------------------------------------------

def ranks_from_record(rec: dict) -> dict[int, int]:
    """Competition ("1,2,2,4") ranks from a sweep record's final scores.

    Survivors are ranked by descending final score with ties sharing a
    rank; eliminated seats share the worst rank (n_survivors + 1). Mirrors
    `foedus.scoring.compute_match_result` without importing/mutating it.
    """
    final_scores = rec["final_scores"]
    eliminated = set(rec.get("eliminated", []))
    n = len(final_scores)
    survivors = [i for i in range(n) if i not in eliminated]
    survivors_sorted = sorted(survivors, key=lambda i: -final_scores[i])

    rank: dict[int, int] = {}
    cur_rank = 1
    last_score: float | None = None
    seen = 0
    for seat in survivors_sorted:
        seen += 1
        score = final_scores[seat]
        if last_score is None or score < last_score:
            cur_rank = seen
            last_score = score
        rank[seat] = cur_rank

    worst = seen + 1 if seen else 1
    for seat in eliminated:
        rank[seat] = worst
    return rank


# --- ordering agreement ---------------------------------------------------

def kendall_tau(order_a: Sequence[Hashable],
                order_b: Sequence[Hashable]) -> float:
    """Kendall tau correlation between two orderings of the same items.

    Both arguments are best->worst orderings that are permutations of the
    same set. Returns +1 for identical orders, -1 for reversed, and
    (concordant - discordant) / n_pairs in between. n < 2 -> 1.0.
    """
    items = list(order_a)
    if sorted(map(str, items)) != sorted(map(str, order_b)):
        raise ValueError("orderings must be permutations of the same items")
    pos_b = {item: i for i, item in enumerate(order_b)}
    n = len(items)
    if n < 2:
        return 1.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            # In order_a, items[i] ranks ahead of items[j] by construction.
            if pos_b[items[i]] < pos_b[items[j]]:
                concordant += 1
            else:
                discordant += 1
    total = n * (n - 1) / 2
    return (concordant - discordant) / total


# --- discrimination -------------------------------------------------------

def discrimination_index(ratings: dict[Hashable, tuple[float, float]]) -> float:
    """Signal-to-noise skill separation: stdev(mu) / mean(sigma).

    `ratings` maps identity -> (mu, sigma). Higher means the rungs are
    spread wide relative to the residual rating uncertainty, i.e. the
    format discriminates skill well. Population stdev; 0.0 when flat.
    """
    if not ratings:
        return 0.0
    mus = [mu for mu, _ in ratings.values()]
    sigmas = [sigma for _, sigma in ratings.values()]
    mean_mu = sum(mus) / len(mus)
    var = sum((mu - mean_mu) ** 2 for mu in mus) / len(mus)
    spread = math.sqrt(var)
    mean_sigma = sum(sigmas) / len(sigmas)
    if mean_sigma == 0:
        return 0.0
    return spread / mean_sigma


def separated_adjacent_pairs(
    order: Sequence[Hashable],
    ratings: dict[Hashable, tuple[float, float]],
) -> int:
    """Count adjacent rungs whose mu gap exceeds their combined sigma.

    `order` is best->worst; two neighbours are "separated" (confidently
    distinguishable) when mu_better - mu_worse > sigma_better + sigma_worse.
    """
    count = 0
    for a, b in zip(order, order[1:]):
        mu_a, sig_a = ratings[a]
        mu_b, sig_b = ratings[b]
        if (mu_a - mu_b) > (sig_a + sig_b):
            count += 1
    return count


def min_adjacent_separation(
    order: Sequence[Hashable],
    ratings: dict[Hashable, tuple[float, float]],
) -> float:
    """Tightest adjacent-rung gap, in combined-sigma units.

    `order` is best->worst; returns min over neighbours of
    (mu_better - mu_worse) / (sigma_better + sigma_worse). A single number
    for "how hard is the *hardest* pair to tell apart" — the bottleneck a
    tail-dominated spread metric hides. inf for < 2 rungs.
    """
    gaps = []
    for a, b in zip(order, order[1:]):
        mu_a, sig_a = ratings[a]
        mu_b, sig_b = ratings[b]
        denom = sig_a + sig_b
        gaps.append((mu_a - mu_b) / denom if denom else float("inf"))
    return min(gaps) if gaps else float("inf")


# --- game-level aggregates ------------------------------------------------

def detente_rate(records: Sequence[dict]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.get("detente_reached")) / len(records)


def elimination_rate(records: Sequence[dict]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.get("eliminated")) / len(records)


def mean_turns(records: Sequence[dict]) -> float:
    if not records:
        return 0.0
    return sum(r["total_turns"] for r in records) / len(records)


# --- rating ---------------------------------------------------------------

def rate_records(records: Sequence[dict]):
    """Replay records through OpenSkill; return the RatingSystem.

    Each record's `agents` list is used verbatim as the per-seat rating
    identities (distinct-seat records => unique identities per game).
    """
    from foedus.rating import RatingSystem
    from foedus.scoring import MatchResult

    # NOTE: RatingSystem.update consumes ONLY match.rank — payout,
    # final_scores, detente and solo_winner are ignored by OpenSkill. They are
    # populated for fidelity to the MatchResult shape, not because they move
    # ratings (rating is press-independent; see doc §7.8).
    rs = RatingSystem()
    for rec in records:
        agents = rec["agents"]
        rank = ranks_from_record(rec)
        n = len(agents)
        survivors_n = sum(
            1 for i in range(n) if i not in set(rec.get("eliminated", []))
        )
        solo = (
            next(i for i in range(n) if i not in set(rec.get("eliminated", [])))
            if survivors_n == 1 else None
        )
        match = MatchResult(
            rank=rank, payout={},
            final_scores={i: float(rec["final_scores"][i]) for i in range(n)},
            detente=bool(rec.get("detente_reached", False)),
            solo_winner=solo,
        )
        rs.update(match, identities=list(agents))
    return rs


# --- convergence ----------------------------------------------------------

def convergence_curve(
    records: Sequence[dict],
    reference: Sequence[Hashable],
    game_counts: Sequence[int],
    shuffles: int = 200,
    tau_threshold: float = 0.9,
    seed: int = 0,
) -> dict[int, dict[str, float]]:
    """How reliably prefix-of-g games recover `reference` ordering.

    For each g in `game_counts`, shuffle the game order `shuffles` times,
    rate the first g games, order the tracked identities by conservative
    rating, and compare to `reference` via Kendall tau. Returns, per g:
    `mean_tau`, `frac_correct` (fraction of replicas with tau >=
    tau_threshold), and `mean_sigma` (mean per-identity uncertainty).

    Models a match's campaign: how many games until the standings sort the
    entrants correctly with high consistency.
    """
    reference = list(reference)
    ref_set = set(reference)
    rng = random.Random(seed)
    out: dict[int, dict[str, float]] = {}
    records = list(records)

    for g in game_counts:
        taus: list[float] = []
        correct = 0
        sigmas: list[float] = []
        for _ in range(shuffles):
            order = records[:]
            rng.shuffle(order)
            rs = rate_records(order[:g])
            rated = rs.all_ratings()
            # Only compare identities present in the reference; a
            # never-seen identity keeps its default rating. Break rating ties
            # deterministically on the name so the ordering (and thus tau) is
            # reproducible if the helper is ever reused with roster > seats.
            observed = sorted(
                ref_set,
                key=lambda name: (-rs.get(name).conservative, str(name)),
            )
            tau = kendall_tau(reference, observed)
            taus.append(tau)
            if tau >= tau_threshold:
                correct += 1
            sigmas.append(
                sum(rated[name].sigma for name in ref_set if name in rated)
                / max(1, sum(1 for name in ref_set if name in rated))
            )
        out[g] = {
            "mean_tau": sum(taus) / len(taus),
            "frac_correct": correct / shuffles,
            "mean_sigma": sum(sigmas) / len(sigmas),
        }
    return out
