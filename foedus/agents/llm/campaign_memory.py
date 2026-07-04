"""Cross-game ("campaign") memory for a persistent LLMDiplomat.

The reciprocation ledger (`memory.ReciprocationMemory`) remembers WITHIN a game;
this remembers ACROSS the games of a campaign, where the same agent instance
plays the same seat against recurring opponents (the leaderboard-arena setting).
Between games each agent gains one compact `GameRecord`:

  * `GameFacts` — harness-computed NEUTRAL facts (counts only, no advice), built
    entirely from the seat's own fogged view + its within-game reciprocation
    memory, so the record is fog-legal by construction. Passes the same
    leading-words neutrality bar as the within-game ledger (enforced in render).
  * `self_note` — the agent's OWN post-game note (≤80 words), stored VERBATIM.
    It is model output, so it is exempt from the neutrality denylist; the render
    layer must never edit or annotate it.

`CampaignMemory` holds the ordered list and caps how many past games render into
a subsequent prompt (bounding prompt growth). Everything is JSON-serializable so
the run harness can persist it per game for audit ("what did it tell itself, and
did behavior follow?").

Fog note: "they supported MY units" is NOT fog-observable as an executed order
(SupportRound is set-valued; the fog view carries no executed-order data). The
fog-legal proxy — their declared Support *intents* toward my units, visible to
me — is carried on `OpponentGameFacts.their_support_intent_toward_me` and always
labeled as a declared intent, never as executed support.
"""

from __future__ import annotations

from dataclasses import dataclass

from foedus.agents.llm.memory import OpponentRecord, ReciprocationMemory
from foedus.core import PactStatus, PlayerId


@dataclass
class OpponentGameFacts:
    """Per-opponent neutral facts from one completed game (this seat's view)."""

    turns_observed: int
    ally_toward_me: int
    my_supports_of_them: int
    their_support_intent_toward_me: int
    pact_with_me: bool
    breach_involving_me: bool

    def to_dict(self) -> dict:
        return {
            "turns_observed": self.turns_observed,
            "ally_toward_me": self.ally_toward_me,
            "my_supports_of_them": self.my_supports_of_them,
            "their_support_intent_toward_me": self.their_support_intent_toward_me,
            "pact_with_me": self.pact_with_me,
            "breach_involving_me": self.breach_involving_me,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OpponentGameFacts":
        return cls(
            turns_observed=d["turns_observed"],
            ally_toward_me=d["ally_toward_me"],
            my_supports_of_them=d["my_supports_of_them"],
            their_support_intent_toward_me=d["their_support_intent_toward_me"],
            pact_with_me=d["pact_with_me"],
            breach_involving_me=d["breach_involving_me"],
        )


@dataclass
class GameFacts:
    """One completed game's neutral record for a seat."""

    game_index: int              # 0-based order within the campaign
    seed: int
    my_seat: PlayerId
    my_rank: int                 # 1 = highest score (strictly-greater count + 1)
    n_players: int
    final_scores: dict[PlayerId, float]   # seat -> final score (public)
    per_opponent: dict[PlayerId, OpponentGameFacts]

    def to_dict(self) -> dict:
        return {
            "game_index": self.game_index,
            "seed": self.seed,
            "my_seat": self.my_seat,
            "my_rank": self.my_rank,
            "n_players": self.n_players,
            "final_scores": {str(k): v for k, v in self.final_scores.items()},
            "per_opponent": {
                str(k): v.to_dict() for k, v in self.per_opponent.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameFacts":
        return cls(
            game_index=d["game_index"],
            seed=d["seed"],
            my_seat=d["my_seat"],
            my_rank=d["my_rank"],
            n_players=d["n_players"],
            final_scores={int(k): v for k, v in d["final_scores"].items()},
            per_opponent={
                int(k): OpponentGameFacts.from_dict(v)
                for k, v in d["per_opponent"].items()
            },
        )


@dataclass
class GameRecord:
    """A game's neutral facts plus this seat's own verbatim post-game note."""

    facts: GameFacts
    self_note: str = ""

    def to_dict(self) -> dict:
        return {"facts": self.facts.to_dict(), "self_note": self.self_note}

    @classmethod
    def from_dict(cls, d: dict) -> "GameRecord":
        return cls(facts=GameFacts.from_dict(d["facts"]),
                   self_note=d.get("self_note", ""))


class CampaignMemory:
    """Ordered per-game records a seat carries across a campaign.

    `cap` bounds how many of the most recent games `recent()` returns (and thus
    how many render into a subsequent prompt); the full history is retained for
    persistence via `all()`.
    """

    def __init__(self, cap: int = 3) -> None:
        self._records: list[GameRecord] = []
        self._cap = cap

    def append(self, record: GameRecord) -> None:
        self._records.append(record)

    def all(self) -> list[GameRecord]:
        return list(self._records)

    def recent(self, n: int | None = None) -> list[GameRecord]:
        """The last `n` records (default `cap`), oldest-first."""
        k = self._cap if n is None else n
        if k <= 0:
            return []
        return list(self._records[-k:])

    def __len__(self) -> int:
        return len(self._records)


def build_game_facts(
    recip_memory: ReciprocationMemory | None,
    view: dict,
    me: PlayerId,
    *,
    seed: int,
    game_index: int,
) -> GameFacts:
    """Assemble the neutral per-game record for seat `me` from its final fogged
    `view` and its within-game `recip_memory`. Fog-legal by construction: reads
    only public `scores` and observer-gated pact/breach/betrayal lists, plus the
    seat's own reciprocation counts.
    """
    scores: dict[PlayerId, float] = dict(view.get("scores") or {})
    my_score = scores.get(me, 0.0)
    my_rank = 1 + sum(1 for s in scores.values() if s > my_score)

    # Opponents I was in an ACCEPTED (binding) pact with, and opponents who
    # broke a commitment to me — both from observer-gated view lists.
    pact_partners: set[PlayerId] = set()
    for pact in view.get("your_pacts") or []:
        if getattr(pact, "status", None) != PactStatus.ACCEPTED:
            continue
        other = pact.counterparty if pact.proposer == me else pact.proposer
        pact_partners.add(other)
    breach_partners: set[PlayerId] = set()
    for b in view.get("your_pact_breaches") or []:
        breach_partners.add(b.breacher)
    for obs in view.get("your_betrayals") or []:
        breach_partners.add(obs.betrayer)

    per_opponent: dict[PlayerId, OpponentGameFacts] = {}
    for p in sorted(k for k in scores if k != me):
        rec: OpponentRecord = recip_memory.get(p) if recip_memory else OpponentRecord()
        per_opponent[p] = OpponentGameFacts(
            turns_observed=rec.turns_observed,
            ally_toward_me=rec.ally_toward_me,
            my_supports_of_them=rec.turns_i_supported_them,
            their_support_intent_toward_me=rec.their_support_intent_toward_me,
            pact_with_me=(p in pact_partners),
            breach_involving_me=(p in breach_partners),
        )

    return GameFacts(
        game_index=game_index,
        seed=seed,
        my_seat=me,
        my_rank=my_rank,
        n_players=len(scores),
        final_scores=scores,
        per_opponent=per_opponent,
    )
