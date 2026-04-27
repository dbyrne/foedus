"""Rating system backed by OpenSkill (Plackett-Luce model).

OpenSkill is a multi-player rating system in the TrueSkill family — designed
for ranked outcomes with multiple players, supports ties, tracks per-player
uncertainty (sigma) so a rating's confidence is queryable.

This module is an optional extra. Install with:
    pip install foedus[rating]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

try:
    from openskill.models import PlackettLuce
except ImportError as e:  # pragma: no cover - import-error path
    raise ImportError(
        "openskill is required for rating support. "
        "Install with: pip install foedus[rating]"
    ) from e

from foedus.scoring import MatchResult


@dataclass
class Rating:
    """OpenSkill rating: mean skill (`mu`) and uncertainty (`sigma`)."""

    mu: float
    sigma: float

    @property
    def conservative(self) -> float:
        """Conservative skill estimate (mu - 3·sigma).

        Use this for leaderboards: it's the lower bound of the 99.7%
        confidence interval, so newly rated players don't temporarily
        leapfrog established ones on a lucky win.
        """
        return self.mu - 3 * self.sigma


class RatingSystem:
    """Tracks player ratings across many matches.

    Player identities are arbitrary hashables (strings, agent names, integers).
    The same identity across multiple `update()` calls accumulates rating
    history; new identities start with a default rating.

    Example:
        from foedus import play_game, GameConfig, RandomAgent
        from foedus.scoring import compute_match_result
        from foedus.rating import RatingSystem

        ratings = RatingSystem()
        for _ in range(1000):
            cfg = GameConfig(num_players=4)
            agents = {0: RandomAgent(), 1: RandomAgent(),
                      2: RandomAgent(), 3: RandomAgent()}
            final = play_game(agents, config=cfg)
            ratings.update(
                compute_match_result(final),
                identities=["alice", "bob", "carol", "dave"],
            )
        print(ratings["alice"].conservative)
    """

    def __init__(self) -> None:
        self._model = PlackettLuce()
        self._ratings: dict[Hashable, tuple[float, float]] = {}

    def __getitem__(self, identity: Hashable) -> Rating:
        return self.get(identity)

    def __contains__(self, identity: Hashable) -> bool:
        return identity in self._ratings

    def get(self, identity: Hashable) -> Rating:
        """Return current rating, creating a default one on first access."""
        if identity not in self._ratings:
            r = self._model.rating()
            self._ratings[identity] = (r.mu, r.sigma)
        mu, sigma = self._ratings[identity]
        return Rating(mu=mu, sigma=sigma)

    def update(self, match: MatchResult, identities: list[Hashable]) -> None:
        """Update ratings from one match.

        `identities[i]` is the identity of the player in seat `i`. The list
        must have one entry per seat in the game.
        """
        n = len(identities)
        if n != len(match.rank):
            raise ValueError(
                f"identities length ({n}) must equal player count ({len(match.rank)})"
            )

        teams = []
        for i in range(n):
            current = self.get(identities[i])
            teams.append([self._model.rating(mu=current.mu, sigma=current.sigma)])

        ranks = [match.rank[i] for i in range(n)]
        new_teams = self._model.rate(teams, ranks=ranks)

        for i, team in enumerate(new_teams):
            self._ratings[identities[i]] = (team[0].mu, team[0].sigma)

    def all_ratings(self) -> dict[Hashable, Rating]:
        """Snapshot of every tracked player's current rating."""
        return {ident: Rating(mu=mu, sigma=sigma)
                for ident, (mu, sigma) in self._ratings.items()}

    def leaderboard(self) -> list[tuple[Hashable, Rating]]:
        """All tracked players, sorted by conservative rating (descending)."""
        return sorted(
            self.all_ratings().items(),
            key=lambda kv: -kv[1].conservative,
        )
