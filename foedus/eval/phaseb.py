"""Pure helpers for the G1 Phase B seed-paired eval (trained vs base).

Phase B answers two questions from ONE seed-paired game set (see
``docs/research/2026-07-10-gym-g1/phase-b/prereg.md``):

* **B1** — does the distilled entrant beat its own untrained base model?
* **B2** — does a table containing the trained entrant contain the scripted
  freerider (Golf) better than the same table with the base model?

The table is 4 seats: ``[MODEL, Golf-freerider, anchorA, anchorB]``. For each
sealed seed the game is run **twice** — once with ``MODEL=trained`` and once
with ``MODEL=base`` — under byte-identical conditions (same board, same seat
layout, same scripted opponents); the only variable is the model weights in
the MODEL seat. The MODEL seat rotates across seeds to control for position.

This module holds only the *pure* pieces (no I/O, no LLM, no engine mutation)
so they are unit-testable in isolation:

* :func:`plan_paired_seating` — deterministic seat -> role layout for a seed.
* :func:`board_fingerprint` — a canonical hash of an initial board, so the two
  arms of a pair can be **asserted** byte-identical (the load-bearing
  seed-pairing fairness check).
* :func:`competition_ranks` — placement from final scores + eliminations,
  mirroring ``foedus.scoring._compute_ranks`` (1 = best, ties share, eliminated
  share the worst rank).
* :func:`two_sided_sign_test` — exact binomial paired sign test over per-seed
  deltas (the pre-registered verdict statistic).

The freerider is served under the neutral arena handle ``Golf`` — nothing in
the seat layout or agent-visible state hints at its scripted nature.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from math import comb

MODEL_ROLE = "MODEL"
GOLF_ROLE = "Golf"  # neutral handle for the DishonestCooperator freerider


@dataclass(frozen=True)
class PairedSeating:
    """The seat -> role layout for one seed's paired pair of games.

    Both arms (trained + base) of a seed use this identical layout; only the
    weights behind the MODEL seat differ.
    """

    seed_index: int
    num_seats: int
    model_seat: int
    golf_seat: int
    anchor_seats: list[int]           # sorted, aligned to ``anchor_classes``
    anchor_classes: list[str]
    freerider_class: str
    #: Heuristic class names in the order ``run_one_llm_game`` consumes them —
    #: i.e. filling the non-MODEL seats in ascending index order.
    heuristic_names: list[str]
    role_by_seat: list[str]           # seat -> role tag (MODEL / Golf / anchor class)


def plan_paired_seating(
    seed_index: int,
    *,
    freerider_class: str,
    anchor_classes: list[str],
    num_seats: int | None = None,
) -> PairedSeating:
    """Plan one seed's seat layout.

    The MODEL seat rotates by seed: ``model_seat = seed_index % num_seats``
    (§ pre-registration seat-rotation scheme). The remaining seats are filled,
    in ascending index order, by ``[freerider_class, *anchor_classes]`` — so
    Golf takes the lowest-index non-MODEL seat and the anchors follow. This
    exactly matches how :func:`scripts.foedus_llm_diplomat_run.run_one_llm_game`
    places ``heuristic_names`` into the non-LLM seats, so the returned
    ``heuristic_names`` can be passed straight through.

    Rotating the MODEL seat over all ``num_seats`` positions (with N a multiple
    of ``num_seats``) makes MODEL perfectly seat-balanced; Golf's absolute seat
    then co-varies, but every B2 comparison is *paired within a seed* (Golf sits
    in the SAME seat in both arms of a pair), so the paired delta is unaffected.
    """
    if num_seats is None:
        num_seats = 1 + 1 + len(anchor_classes)  # MODEL + freerider + anchors
    if num_seats != 2 + len(anchor_classes):
        raise ValueError(
            f"num_seats={num_seats} inconsistent with 1 MODEL + 1 freerider + "
            f"{len(anchor_classes)} anchors")
    if seed_index < 0:
        raise ValueError(f"seed_index must be non-negative, got {seed_index}")

    model_seat = seed_index % num_seats
    non_model = [s for s in range(num_seats) if s != model_seat]  # ascending
    fill_classes = [freerider_class, *anchor_classes]
    if len(fill_classes) != len(non_model):
        raise ValueError("fill classes do not match non-MODEL seat count")

    golf_seat = non_model[0]
    anchor_seats = non_model[1:]

    role_by_seat: list[str] = [""] * num_seats
    role_by_seat[model_seat] = MODEL_ROLE
    role_by_seat[golf_seat] = GOLF_ROLE
    for seat, cls in zip(anchor_seats, anchor_classes):
        role_by_seat[seat] = cls

    return PairedSeating(
        seed_index=seed_index,
        num_seats=num_seats,
        model_seat=model_seat,
        golf_seat=golf_seat,
        anchor_seats=list(anchor_seats),
        anchor_classes=list(anchor_classes),
        freerider_class=freerider_class,
        heuristic_names=fill_classes,
        role_by_seat=role_by_seat,
    )


def board_fingerprint(state) -> str:
    """SHA-256 over a canonical serialization of an *initial* board.

    Captures everything that defines the starting conditions both arms of a
    pair must share: the config (num_players / max_turns / archetype / map_radius
    / seed), the full map graph (coords, edges, node types, home assignments,
    supply values) and the initial units + ownership + scores. Because the board
    is a pure function of ``(cfg, seed)``, the two arms of a seed produce an
    identical fingerprint by construction — asserting equality makes that
    guarantee load-bearing and catches any accidental drift (a changed preset, a
    mis-passed seed) that would otherwise silently break the pairing.
    """
    m = state.map
    payload = {
        "config": {
            "num_players": state.config.num_players,
            "max_turns": state.config.max_turns,
            "archetype": state.config.archetype.value,
            "map_radius": state.config.map_radius,
            "seed": state.config.seed,
        },
        "map": {
            "coords": {str(n): list(c) for n, c in sorted(m.coords.items())},
            "edges": {str(n): sorted(m.edges.get(n, frozenset()))
                      for n in sorted(m.coords)},
            "node_types": {str(n): m.node_types[n].value
                           for n in sorted(m.node_types)},
            "home_assignments": {str(n): m.home_assignments[n]
                                 for n in sorted(m.home_assignments)},
            "supply_values": {str(n): m.supply_values[n]
                              for n in sorted(m.supply_values)},
        },
        "units": sorted([u.id, u.owner, u.location] for u in state.units.values()),
        "ownership": {str(n): state.ownership[n] for n in sorted(state.ownership)},
        "scores": {str(p): state.scores[p] for p in sorted(state.scores)},
        "turn": state.turn,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def competition_ranks(final_scores: list[float], eliminated: list[int]) -> list[int]:
    """Seat -> placement (1 = best) from final scores + eliminations.

    Mirrors ``foedus.scoring._compute_ranks`` exactly (standard "1224"
    competition ranking): survivors are ranked by descending score, ties share
    a rank, and every eliminated seat shares the single worst rank
    (``#survivors + 1``). Kept as a standalone reimplementation so the analysis
    can rank straight from a sweep row without rebuilding a terminal GameState.
    """
    n = len(final_scores)
    elim = set(eliminated)
    survivors = [p for p in range(n) if p not in elim]
    sorted_survivors = sorted(survivors, key=lambda p: -final_scores[p])

    ranks: dict[int, int] = {}
    last_score: float | None = None
    current_rank = 1
    for i, p in enumerate(sorted_survivors):
        if last_score is not None and final_scores[p] != last_score:
            current_rank = i + 1
        ranks[p] = current_rank
        last_score = final_scores[p]

    elim_rank = len(survivors) + 1
    for p in range(n):
        ranks.setdefault(p, elim_rank)
    return [ranks[p] for p in range(n)]


@dataclass
class SignTestResult:
    n_pairs: int          # total pairs (incl. ties)
    n_nonzero: int        # pairs with a non-zero delta (the test's effective n)
    n_positive: int
    n_negative: int
    n_zero: int
    p_value: float        # exact two-sided binomial p over the non-zero pairs
    favorable: int        # = n_positive (convention: "trained better" -> positive)

    def to_dict(self) -> dict:
        return {
            "n_pairs": self.n_pairs,
            "n_nonzero": self.n_nonzero,
            "n_positive": self.n_positive,
            "n_negative": self.n_negative,
            "n_zero": self.n_zero,
            "p_value_two_sided": self.p_value,
            "favorable_positive": self.favorable,
        }


def two_sided_sign_test(deltas: list[float]) -> SignTestResult:
    """Exact two-sided binomial sign test over paired deltas.

    ``delta > 0`` counts as a "positive" (by convention: the trained arm did
    better on that seed), ``delta < 0`` a "negative", ``delta == 0`` a tie
    (dropped from the test, per the standard sign-test treatment). The p-value
    is the exact two-sided binomial tail under H0: P(+) = P(-) = 1/2.
    """
    pos = sum(1 for d in deltas if d > 0)
    neg = sum(1 for d in deltas if d < 0)
    zero = sum(1 for d in deltas if d == 0)
    n = pos + neg
    if n == 0:
        p = 1.0
    else:
        k = min(pos, neg)
        tail = sum(comb(n, i) for i in range(0, k + 1)) * (0.5 ** n)
        p = min(1.0, 2.0 * tail)
    return SignTestResult(
        n_pairs=len(deltas), n_nonzero=n, n_positive=pos, n_negative=neg,
        n_zero=zero, p_value=p, favorable=pos,
    )


def summary_stats(values: list[float]) -> dict:
    """Mean / min / max / n for a list of numbers (denominated, empty-safe)."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "min": None, "max": None}
    return {
        "n": n,
        "mean": sum(values) / n,
        "min": min(values),
        "max": max(values),
    }
