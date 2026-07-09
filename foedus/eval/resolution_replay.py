"""Deterministic resolution-truth replay harness (M-foedus-s1-5-confound-check).

The S1 corpus autopsy (docs/research/2026-07-04-canonical-campaign-v1/autopsy-s1.md
section 4) flags that "executed" (a Move/Support submitted to the engine) is
NOT the same as "the engine actually dislodged the target" -- the sealed
corpus retains no per-combat resolution log by design (see CLAUDE.md's
wire-protocol note). This module answers that question WITHOUT playing any
new games or calling any LLM: since a foedus match is deterministic given
(seed, every seat's actual decisions), and every decision is logged
verbatim (`decisions_game{g}_seat{s}.jsonl`), the whole game can be
REPLAYED through the real engine (`foedus.loop.play_game` +
`foedus.resolve._resolve_orders_detailed`) by substituting a `ReplayAgent`
(replays a logged decision) for the live LLM call.

Faithfulness is the whole point of this module, so it deliberately reuses
production code rather than reimplementing resolution logic:
  - `ReplayAgent` calls the SAME parse functions
    (`parse_negotiation_response` / `parse_orders_response`) the original
    `LLMDiplomat` used, against the REPLAYED (not original) state -- since
    both are pure functions of (raw_response, state, player), a faithful
    replay reproduces the original run's decisions bit-for-bit, INCLUDING
    whatever the original run's own legality gate already did (an
    illegal order was already coerced to Hold there; replaying preserves
    that rather than second-guessing it).
  - `replay_game` drives the SAME canonical loop (`foedus.loop.play_game`)
    the original harness used, with the freerider re-instantiated as a
    fresh stateless heuristic (`foedus.agents.heuristics`, deterministic
    given the game seed -- see `_tiebreak.shuffled_neighbors`).
  - Per-turn combat truth (`ResolutionDetail`: canon orders, per-unit
    outcome, dislodge attribution, cut supports) comes straight from
    `foedus.resolve._resolve_orders_detailed`, called with the EXACT
    `(prev_state, orders_by_player)` pair `finalize_round` itself used that
    turn (via `play_game`'s `on_turn_resolved` hook) -- not re-derived by
    diffing before/after state.

`verify_replay_fidelity` is the harness's own self-check: for every LLM
seat's logged orders-phase decision, the ORIGINAL run's `parsed` field
(what it actually submitted, after ITS OWN legality gate) is compared
against what the replay independently reconstructed for that
(turn, unit) -- any mismatch means the replay has diverged from the real
game and its results should not be trusted.

`geometric_legality` and `counterfactual_reinstate_order` exist to answer a
sharper question the S1 autopsy's confound #3 raised: some declared Support
orders use the `require_dest` ("pin") variant, which `foedus.legal`'s
candidate enumeration never offers (see `legal_orders_for_unit`'s
docstring) -- so `parse_orders_response`'s legality gate rejects EVERY
`require_dest` Support unconditionally, regardless of whether the order
would actually have been valid. `geometric_legality` distinguishes that
parser/prompt-schema gap ("illegal_parser_gap": `foedus.resolve`'s own
normalization would have accepted it) from genuine geometric illegality
("illegal_geometric": the map doesn't support it either way).
`counterfactual_reinstate_order` re-resolves a turn with one order swapped
in, to check whether reinstating a parser-gap-dropped order would actually
have changed the outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from foedus.agents.heuristics import ROSTER
from foedus.agents.llm.parse import (
    NegotiationDecision,
    parse_negotiation_response,
    parse_orders_response,
)
from foedus.core import (
    Archetype,
    ChatDraft,
    GameConfig,
    GameState,
    Hold,
    Order,
    PactProposal,
    PlayerId,
    Press,
    Support,
    UnitId,
)
from foedus.legal import legal_orders_for_unit
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import (
    ResolutionDetail,
    _normalize_with_reason,
    _resolve_orders_detailed,
    initial_state,
)


class MissingDecisionError(LookupError):
    """A replayed seat has no logged decision for a (turn, phase) the replay
    actually reached.

    This is a corpus/harness mismatch, not a normal replay path -- raised
    rather than silently defaulting to an empty decision, so a data problem
    surfaces loudly (a wrong replay result would otherwise look identical to
    a correct one).
    """


class ReplayAgent:
    """Agent-protocol adapter that reproduces one seat's LOGGED decisions
    (`decisions_game{g}_seat{s}.jsonl` rows) instead of calling an LLM.

    Deterministic given a faithfully-replayed `GameState`: `parse_*_response`
    are pure functions of (raw_response, state, player), so replaying the
    recorded `raw_response` against the SAME state the original decision saw
    reproduces the SAME Press / orders -- see the module docstring.

    Caches are keyed by turn only (not `(turn, player)`, unlike
    `LLMDiplomat`'s cache) -- correct because `replay_game` always
    constructs one `ReplayAgent` per seat, never shares an instance across
    seats. Would need `(turn, player)` keys if ever reused for a multi-seat
    instance the way `LLMDiplomat` supports.
    """

    def __init__(self, decisions: list[dict]) -> None:
        self._by_turn_phase: dict[tuple[int, str], dict] = {
            (rec["turn"], rec["phase"]): rec for rec in decisions
        }
        self._negotiation_cache: dict[int, NegotiationDecision] = {}
        self._orders_cache: dict[int, dict[UnitId, Order]] = {}

    def _record(self, turn: int, phase: str) -> dict:
        rec = self._by_turn_phase.get((turn, phase))
        if rec is None:
            raise MissingDecisionError(
                f"no logged {phase!r} decision for turn {turn} -- the replay "
                "reached a turn/phase the source decision log never recorded"
            )
        return rec

    def _negotiate(self, state: GameState, player: PlayerId) -> NegotiationDecision:
        cached = self._negotiation_cache.get(state.turn)
        if cached is not None:
            return cached
        rec = self._record(state.turn, "negotiate")
        decision = parse_negotiation_response(rec["raw_response"], state, player)
        self._negotiation_cache[state.turn] = decision
        return decision

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        return self._negotiate(state, player).press

    def choose_pacts(self, state: GameState, player: PlayerId) -> list[PactProposal]:
        return self._negotiate(state, player).proposals

    def accept_pacts(self, state: GameState, player: PlayerId) -> list[int]:
        return self._negotiate(state, player).accept_ids

    def choose_orders(self, state: GameState, player: PlayerId) -> dict[UnitId, Order]:
        cached = self._orders_cache.get(state.turn)
        if cached is not None:
            return cached
        rec = self._record(state.turn, "orders")
        orders, _fell_back, _n_coerced = parse_orders_response(
            rec["raw_response"], state, player
        )
        self._orders_cache[state.turn] = orders
        return orders

    def chat_drafts(self, state: GameState, player: PlayerId) -> list[ChatDraft]:
        # v0 locked decision: structured press only, no free-text chat --
        # matches LLMDiplomat.chat_drafts exactly (nothing to replay).
        return []


@dataclass
class TurnResolution:
    """One turn's replayed combat truth: the state entering the turn, the
    EXACT orders_by_player fed to the engine that turn, the resulting state,
    and the resolver's own attribution (`ResolutionDetail`: canon orders,
    per-unit outcome, dislodge attribution, cut supports)."""

    turn: int
    prev_state: GameState
    orders_by_player: dict[PlayerId, dict[UnitId, Order]]
    new_state: GameState
    detail: ResolutionDetail


def replay_game(
    *,
    seed: int,
    num_players: int,
    max_turns: int,
    archetype: Archetype,
    map_radius: int,
    llm_seats: list[int],
    freerider_seats: dict[int, str],
    decisions_by_seat: dict[int, list[dict]],
) -> tuple[GameState, list[TurnResolution]]:
    """Replay one sealed game from its seed + every seat's logged decisions.

    Builds the same `GameConfig` shape the canonical-campaign harness did
    (`scripts/foedus_llm_diplomat_run.py::run_one_llm_game`): a plain
    `GameConfig` (no preset -- the campaign runner doesn't apply
    `foedus.presets.ruleset_v1` to the per-game config either, only to derive
    the board params it passes through) + `generate_map` from the same seed,
    over the 5 fields the campaign always threads through explicitly. Fields
    the campaign never overrode (e.g. `detente_threshold`, which defaults to
    `4 + num_players` on both sides) are left at `GameConfig`'s own class
    default on both the original run and here, so they agree by
    construction -- not verified independently. `verify_replay_fidelity`
    plus each game's final-score/turn/elimination match against the sealed
    `sweep.jsonl` (see `scripts/foedus_s1_5_confound_check.py`) is the actual
    end-to-end faithfulness guarantee; a future campaign run that passes
    `config_overrides` to `run_one_llm_game` would silently desync from this
    reconstruction, and only that check would catch it.

    `agents` is built in strict seat order (0..num_players-1), matching
    `run_one_llm_game`'s own `agents[i] = ... for i, name in
    enumerate(agent_names)` -- `play_game` iterates `agents.items()` within
    each phase, so this keeps per-phase call order identical to the original
    run rather than relying on the engine's per-player resolution being
    order-invariant (which it is, but this removes the need to rely on it).

    `freerider_seats` maps seat -> heuristic CLASS name (e.g.
    `{3: "DishonestCooperator"}`); a fresh instance is built per seat, exactly
    as the original harness did (the freerider is stateless, so this is
    faithful, not an approximation).
    """
    cfg = GameConfig(
        num_players=num_players, max_turns=max_turns, seed=seed,
        archetype=archetype, map_radius=map_radius,
    )
    m = generate_map(num_players, seed=seed, archetype=cfg.archetype,
                     map_radius=cfg.map_radius)
    state = initial_state(cfg, m)

    llm_seat_set = set(llm_seats)
    agents: dict[PlayerId, object] = {}
    for seat in range(num_players):
        if seat in llm_seat_set:
            agents[seat] = ReplayAgent(decisions_by_seat[seat])
        elif seat in freerider_seats:
            agents[seat] = ROSTER[freerider_seats[seat]]()

    resolutions: list[TurnResolution] = []

    def on_turn_resolved(prev_state, orders_by_player, new_state):
        # Recomputes the same resolution finalize_round already ran (see
        # press.py's own `_resolve_orders_detailed(state, orders_by_player)`
        # call) to recover its ResolutionDetail, rather than threading a
        # capture hook through press.py. Safe only because
        # _resolve_orders_detailed is a pure function of its two arguments
        # (no RNG, no I/O) -- confirmed by reading resolve.py in full -- so
        # this call is guaranteed to reproduce the exact detail finalize_round
        # used, not just a plausible-looking recomputation.
        _s_after, detail = _resolve_orders_detailed(prev_state, orders_by_player)
        resolutions.append(TurnResolution(
            turn=prev_state.turn, prev_state=prev_state,
            orders_by_player=orders_by_player, new_state=new_state, detail=detail,
        ))

    final_state = play_game(agents, state=state, on_turn_resolved=on_turn_resolved)
    return final_state, resolutions


@dataclass
class Mismatch:
    """One (seat, turn, unit) where the replay's actually-submitted order
    diverges from what the ORIGINAL run's decision log says it submitted."""

    seat: int
    turn: int
    unit_id: int
    logged_parsed: str
    replayed_order: str


def verify_replay_fidelity(
    decisions_by_seat: dict[int, list[dict]],
    resolutions: list[TurnResolution],
) -> list[Mismatch]:
    """Cross-check the replay against the sealed corpus's own record of what
    was submitted: the original run's `parsed` field (post-ITS-OWN legality
    gate) versus this replay's `orders_by_player` for the same (seat, turn,
    unit). An empty return is the harness's evidence that it faithfully
    reproduced the real game -- not just that final scores happened to match.
    """
    by_turn = {r.turn: r for r in resolutions}
    mismatches: list[Mismatch] = []
    for seat, records in decisions_by_seat.items():
        for rec in records:
            if rec.get("phase") != "orders":
                continue
            turn = rec["turn"]
            res = by_turn.get(turn)
            if res is None:
                continue
            replayed = res.orders_by_player.get(seat, {})
            parsed = rec.get("parsed") or {}
            for uid_key, logged_repr in parsed.items():
                uid = int(uid_key)
                replayed_order = replayed.get(uid, Hold())
                replayed_repr = repr(replayed_order)
                if replayed_repr != logged_repr:
                    mismatches.append(Mismatch(
                        seat=seat, turn=turn, unit_id=uid,
                        logged_parsed=logged_repr, replayed_order=replayed_repr,
                    ))
    return mismatches


def counterfactual_reinstate_order(
    prev_state: GameState,
    orders_by_player: dict[PlayerId, dict[UnitId, Order]],
    *,
    player: PlayerId,
    unit_id: UnitId,
    order: Order,
) -> tuple[GameState, ResolutionDetail]:
    """Re-resolve `prev_state` with `unit_id`'s order overridden to `order`,
    holding every other unit's ACTUAL submitted order fixed.

    Answers "what would the real engine have done if THIS ONE order had been
    accepted as declared" -- e.g. to test whether a parser-gap-dropped
    `require_dest` Support would actually have changed the outcome. This is
    explicitly a counterfactual, not a replay: it is never what the sealed
    game actually did.
    """
    modified = {p: dict(orders) for p, orders in orders_by_player.items()}
    modified.setdefault(player, {})[unit_id] = order
    return _resolve_orders_detailed(prev_state, modified)


def geometric_legality(
    state: GameState,
    unit_id: UnitId,
    order: Order,
    all_orders: dict[UnitId, Order],
) -> str:
    """Classify `order`'s legality for `unit_id` at `state`, distinguishing
    genuine geometric illegality from the `require_dest` parser/prompt-schema
    gap (see module docstring):

    - "legal": `order` is a member of `legal_orders_for_unit(state, unit_id)`
      (the same candidate list `parse_orders_response`'s gate checks).
    - "illegal_parser_gap": `order` is a `Support` with `require_dest` set
      (so `legal_orders_for_unit` never offers it as a candidate, by
      construction -- pin variants are deliberately excluded from candidate
      generation) AND `foedus.resolve`'s own normalization
      (`_normalize_with_reason`, the SAME check `_resolve_orders_detailed`
      applies at resolution time) would have accepted it given `all_orders`
      (the turn's actual submitted orders). The order was valid; only the
      candidate-list gate that guards submission rejected it.
    - "illegal_geometric": neither the candidate list NOR `foedus.resolve`'s
      own normalization would accept it -- a genuine geometry/target
      mismatch, independent of the require_dest gap.
    """
    legal = legal_orders_for_unit(state, unit_id)
    if order in legal:
        return "legal"
    if isinstance(order, Support) and order.require_dest is not None:
        canon, _reason = _normalize_with_reason(state, unit_id, order, all_orders)
        if isinstance(canon, Support):
            return "illegal_parser_gap"
    return "illegal_geometric"
