"""End-of-game match payouts and rankings.

Takes a terminal GameState and produces a MatchResult that rating systems
(ELO, OpenSkill, Glicko, etc.) and leaderboards can consume directly.

Payout formula:
- Solo winner (last player standing): takes the entire pot (1.0).
- Détente: payouts are linearly proportional to in-game score among
  survivors. If all surviving scores are 0, equal split.
- Otherwise (max-turns reached): 20% flat survival bonus among survivors,
  80% distributed by sum-of-squares of in-game scores. Sum-of-squares
  rewards margin-of-victory (winning by 20 pays much more than winning
  by 2), the survival bonus prevents zero payouts for surviving 4th-place
  players which would remove their incentive to keep playing.

Eliminated players always receive 0.

Ranks: 1 = best, ties share a rank, eliminated players share the worst rank.
"""

from __future__ import annotations

from dataclasses import dataclass

from foedus.core import GameState, PlayerId

SURVIVAL_BONUS_FRACTION = 0.20
SCORE_POOL_FRACTION = 1.0 - SURVIVAL_BONUS_FRACTION  # 0.80


@dataclass
class MatchResult:
    """End-of-game result, ready for rating-system consumption."""

    rank: dict[PlayerId, int]
    """Per-player placement. 1 = best. Ties share a rank. Eliminated players
    share the worst rank (one greater than the lowest survivor rank)."""

    payout: dict[PlayerId, float]
    """Per-player normalized payout. Sums to 1.0 (within float tolerance).
    Eliminated players receive 0."""

    final_scores: dict[PlayerId, float]
    """Raw in-game cumulative scores."""

    detente: bool
    """True iff the game ended via the peaceful collective-victory condition."""

    solo_winner: PlayerId | None
    """Set when one player is the last one standing; None otherwise (including
    score-victory and détente)."""


def compute_match_result(state: GameState) -> MatchResult:
    """Convert a terminal `GameState` into a `MatchResult`.

    Raises `ValueError` if the state is not yet terminal.
    """
    if not state.is_terminal():
        raise ValueError("compute_match_result requires a terminal GameState")

    n = state.config.num_players
    eliminated = state.eliminated
    scores = dict(state.scores)
    survivors = [p for p in range(n) if p not in eliminated]

    solo_winner = survivors[0] if len(survivors) == 1 else None
    ranks = _compute_ranks(scores, survivors, n)

    if solo_winner is not None:
        payout = {p: 0.0 for p in range(n)}
        payout[solo_winner] = 1.0
    elif state.detente_reached:
        payout = _detente_payout(scores, survivors, n)
    else:
        payout = _score_payout(scores, survivors, n)

    return MatchResult(
        rank=ranks,
        payout=payout,
        final_scores=scores,
        detente=state.detente_reached,
        solo_winner=solo_winner,
    )


def _compute_ranks(scores: dict[PlayerId, float],
                   survivors: list[PlayerId],
                   n: int) -> dict[PlayerId, int]:
    """Standard competition ranking ("1224" style): ties share a rank,
    next rank skipped equal to the tie size. Eliminated all share the
    rank one below the lowest survivor.
    """
    ranks: dict[PlayerId, int] = {}
    sorted_survivors = sorted(survivors, key=lambda p: -scores[p])
    last_score: float | None = None
    current_rank = 1
    for i, p in enumerate(sorted_survivors):
        if last_score is not None and scores[p] != last_score:
            current_rank = i + 1
        ranks[p] = current_rank
        last_score = scores[p]

    elim_rank = len(survivors) + 1
    for p in range(n):
        if p not in ranks:
            ranks[p] = elim_rank
    return ranks


def _score_payout(scores: dict[PlayerId, float],
                  survivors: list[PlayerId],
                  n: int) -> dict[PlayerId, float]:
    """Non-détente payout: 20% flat survival bonus + 80% sum-of-squares share."""
    payout = {p: 0.0 for p in range(n)}
    if not survivors:
        return {p: 1.0 / n for p in range(n)}  # pathological no-survivors

    flat_share = SURVIVAL_BONUS_FRACTION / len(survivors)
    sq = {p: max(0.0, scores[p]) ** 2 for p in survivors}
    sq_total = sum(sq.values())

    if sq_total == 0:
        equal_score_share = SCORE_POOL_FRACTION / len(survivors)
        for p in survivors:
            payout[p] = flat_share + equal_score_share
    else:
        for p in survivors:
            payout[p] = flat_share + SCORE_POOL_FRACTION * sq[p] / sq_total

    return payout


def _detente_payout(scores: dict[PlayerId, float],
                    survivors: list[PlayerId],
                    n: int) -> dict[PlayerId, float]:
    """Détente payout: linearly proportional to in-game score among survivors.

    Less steep than non-détente sum-of-squares — the leader gets less of
    the pot when peace is achieved, which preserves the strategic value of
    détente as a viable path for losing-but-not-yet-lost players.
    """
    payout = {p: 0.0 for p in range(n)}
    if not survivors:
        return {p: 1.0 / n for p in range(n)}

    sc = {p: max(0.0, scores[p]) for p in survivors}
    total = sum(sc.values())
    if total == 0:
        for p in survivors:
            payout[p] = 1.0 / len(survivors)
    else:
        for p in survivors:
            payout[p] = sc[p] / total
    return payout
