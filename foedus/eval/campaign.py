"""Match-protocol helpers for a canonical ruleset-v1 campaign.

Pure, engine-independent glue that the campaign orchestrator
(``scripts/foedus_canonical_campaign.py``) composes *around* the pure engine.
Implements the two protocol pieces from ``docs/design/2026-07-04-ruleset-v1.md``
that are layered on top of ``GameConfig`` rather than being fields on it:

* **§7.4 cyclic seat rotation** — over any ``n`` consecutive games each entrant
  occupies each of the ``n`` seat positions exactly once (a cyclic Latin
  square). Game ``k``: entrant ``i`` sits in seat ``(i + k) mod n``. An 8-game
  match at 4 seats is two full cycles: perfectly seat-balanced.
* **§7.5 commit-reveal seed manifest** — draw the per-game seed list from a
  CSPRNG, publish a SHA-256 *commitment* to it before any game is played, and
  reveal the seeds + nonce afterwards so anyone can confirm the operator did
  not re-roll a disliked board. Seeds are just the engine's existing
  ``GameConfig.seed`` — no engine change.

No engine mutation and no I/O beyond JSON (de)serialization of the manifest.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass

#: Domain-separation tag baked into every commitment (design §7.5). Binds a
#: commit to this ruleset so a hash from one protocol can't be replayed in
#: another.
DOMAIN = "foedus-ruleset-v1"


# --- §7.4 cyclic seat rotation -------------------------------------------

def _check_rotation_args(index: int, game: int, num_seats: int, *,
                         name: str) -> None:
    if num_seats <= 0:
        raise ValueError(f"num_seats must be positive, got {num_seats}")
    if game < 0:
        raise ValueError(f"game must be non-negative, got {game}")
    if not (0 <= index < num_seats):
        raise ValueError(
            f"{name} {index} out of range for num_seats={num_seats}"
        )


def seat_of_entrant(entrant: int, game: int, num_seats: int) -> int:
    """Seat that ``entrant`` (0-based) occupies in game ``game`` (0-based).

    ``(entrant + game) mod num_seats`` — the cyclic Latin square of §7.4.
    """
    _check_rotation_args(entrant, game, num_seats, name="entrant")
    return (entrant + game) % num_seats


def entrant_at_seat(seat: int, game: int, num_seats: int) -> int:
    """Inverse of :func:`seat_of_entrant`: which entrant sits at ``seat``."""
    _check_rotation_args(seat, game, num_seats, name="seat")
    return (seat - game) % num_seats


def seat_assignment(game: int, num_seats: int) -> dict[int, int]:
    """Map ``seat -> entrant`` for one game (a permutation of ``range(n)``)."""
    return {s: entrant_at_seat(s, game, num_seats) for s in range(num_seats)}


@dataclass(frozen=True)
class GameSeating:
    """The concrete seat layout of one campaign game.

    Composes the §7.4 rotation with the fixed roster so the orchestrator can
    place persistent per-entrant agents into this game's seats. ``entrant``
    indices are stable across the whole campaign (0-based roster position);
    seats rotate under ``rotate=True``.
    """

    game_index: int
    seat_to_entrant: dict[int, int]
    entrant_to_seat: dict[int, int]
    llm_seats: list[int]          # sorted seats occupied by non-freerider entrants
    freerider_seats: list[int]    # sorted seats occupied by freerider entrants
    identity_by_seat: list[str]   # seat -> stable entrant identity handle


def plan_seating(game_index: int, entrant_identities: list[str],
                 freerider_entrants: set[int], *, rotate: bool = True) -> GameSeating:
    """Plan one game's seating from the campaign roster.

    ``entrant_identities[e]`` is entrant ``e``'s stable arena handle (identity
    for rating + persistent memory). ``freerider_entrants`` are the roster
    positions that are scripted freerider seats (heuristic, not LLM). With
    ``rotate=True`` entrant ``e`` sits in seat ``(e + game_index) mod n`` (§7.4);
    with ``rotate=False`` entrant ``e`` is pinned to seat ``e``.
    """
    n = len(entrant_identities)
    if n <= 0:
        raise ValueError("entrant_identities must be non-empty")
    if any(not (0 <= e < n) for e in freerider_entrants):
        raise ValueError(
            f"freerider_entrants {sorted(freerider_entrants)} out of range for "
            f"{n} entrants"
        )
    if rotate:
        seat_to_entrant = seat_assignment(game_index, n)
    else:
        if game_index < 0:
            raise ValueError(f"game_index must be non-negative, got {game_index}")
        seat_to_entrant = {s: s for s in range(n)}
    entrant_to_seat = {e: s for s, e in seat_to_entrant.items()}
    llm_seats = sorted(s for s, e in seat_to_entrant.items()
                       if e not in freerider_entrants)
    freerider_seats = sorted(s for s, e in seat_to_entrant.items()
                             if e in freerider_entrants)
    identity_by_seat = [entrant_identities[seat_to_entrant[s]] for s in range(n)]
    return GameSeating(
        game_index=game_index,
        seat_to_entrant=seat_to_entrant,
        entrant_to_seat=entrant_to_seat,
        llm_seats=llm_seats,
        freerider_seats=freerider_seats,
        identity_by_seat=identity_by_seat,
    )


# --- §7.5 commit-reveal seed manifest ------------------------------------

def canonical_seed_json(seeds: list[int]) -> str:
    """Canonical, order-preserving, whitespace-free JSON for the seed list.

    The exact byte string that goes into the commitment; both operator and
    verifier must produce it identically, so it is compact and never re-sorts.
    """
    return json.dumps(list(seeds), separators=(",", ":"))


def seed_commitment(match_id: str, seeds: list[int], nonce: str) -> str:
    """SHA-256 hex commitment: ``DOMAIN|match_id|json(seeds)|nonce`` (§7.5)."""
    payload = f"{DOMAIN}|{match_id}|{canonical_seed_json(seeds)}|{nonce}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def draw_seeds(num_games: int, *, rng=None, bits: int = 63) -> list[int]:
    """Draw ``num_games`` independent non-negative integer game seeds.

    Uses a CSPRNG (:mod:`secrets`) by default; pass ``rng`` (any object with a
    ``getrandbits`` method, e.g. ``random.Random(seed)``) for reproducible
    tests. ``GameConfig.seed`` is an arbitrary int, so any width is legal;
    63 bits gives ample entropy while staying positive.
    """
    if num_games <= 0:
        raise ValueError(f"num_games must be positive, got {num_games}")
    getbits = rng.getrandbits if rng is not None else secrets.randbits
    return [getbits(bits) for _ in range(num_games)]


def new_nonce(*, rng=None, nbytes: int = 16) -> str:
    """A random hex nonce (blocks brute-forcing the seed list from the hash)."""
    if rng is None:
        return secrets.token_hex(nbytes)
    return "".join(f"{rng.getrandbits(8):02x}" for _ in range(nbytes))


@dataclass
class SeedManifest:
    """A commit-reveal seed manifest.

    Before the match: publish the *sealed* form (``commit`` set, ``seeds`` and
    ``nonce`` ``None``). After the match: :func:`revealed_manifest` attaches the
    seeds + nonce so :func:`verify` can recompute and confirm the commitment.
    """

    match_id: str
    num_games: int
    domain: str
    commit: str
    seeds: list[int] | None = None
    nonce: str | None = None

    @property
    def revealed(self) -> bool:
        return self.seeds is not None and self.nonce is not None

    def to_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "num_games": self.num_games,
            "domain": self.domain,
            "commit": self.commit,
            "seeds": list(self.seeds) if self.seeds is not None else None,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SeedManifest":
        seeds = d.get("seeds")
        return cls(
            match_id=d["match_id"],
            num_games=d["num_games"],
            domain=d.get("domain", DOMAIN),
            commit=d["commit"],
            seeds=list(seeds) if seeds is not None else None,
            nonce=d.get("nonce"),
        )


def seal(match_id: str, num_games: int, *, rng=None) -> tuple[SeedManifest, list[int], str]:
    """Draw seeds + nonce and return ``(sealed_manifest, seeds, nonce)``.

    The returned manifest is the publish-before-the-match commitment (no seeds
    or nonce inside it); the caller keeps ``seeds`` and ``nonce`` secret until
    the match is over, then calls :func:`revealed_manifest`.
    """
    seeds = draw_seeds(num_games, rng=rng)
    nonce = new_nonce(rng=rng)
    commit = seed_commitment(match_id, seeds, nonce)
    sealed = SeedManifest(match_id=match_id, num_games=num_games,
                          domain=DOMAIN, commit=commit)
    return sealed, seeds, nonce


def revealed_manifest(sealed: SeedManifest, seeds: list[int], nonce: str) -> SeedManifest:
    """Return a copy of ``sealed`` with the seeds + nonce attached (the reveal)."""
    return SeedManifest(
        match_id=sealed.match_id,
        num_games=sealed.num_games,
        domain=sealed.domain,
        commit=sealed.commit,
        seeds=list(seeds),
        nonce=nonce,
    )


def verify(manifest: SeedManifest) -> bool:
    """True iff a *revealed* manifest's seeds+nonce hash to its commitment.

    Recomputes ``DOMAIN|match_id|json(seeds)|nonce`` and compares to the stored
    ``commit`` (constant-time), and checks ``num_games == len(seeds)``. A sealed
    (unrevealed) manifest returns ``False`` — there is nothing to check.
    """
    if not manifest.revealed:
        return False
    if manifest.num_games != len(manifest.seeds):
        return False
    recomputed = seed_commitment(manifest.match_id, manifest.seeds, manifest.nonce)
    return secrets.compare_digest(recomputed, manifest.commit)
