"""LLMDiplomat — an in-process Foedus Agent driven by a pluggable LLM
backend. Plays the full current press schema (stance, intents, binding
pacts) and reads the public reputation ledger. No-arg constructor; all
config comes from env (mirrors janus_agent.py's JANUS_CHECKPOINT
pattern) -- an optional `client` param exists purely for tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from foedus.agents.llm.campaign_memory import (
    CampaignMemory, GameRecord, IdentityContext, build_game_facts,
)
from foedus.agents.llm.client import LLMClient, make_client_from_env
from foedus.agents.llm.memory import ReciprocationMemory
from foedus.agents.llm.parse import (
    NegotiationDecision,
    parse_negotiation_response,
    parse_orders_response,
)
from foedus.agents.llm.render import (
    render_negotiation_prompt, render_orders_prompt, render_self_note_prompt,
)
from foedus.core import (
    ChatDraft, GameState, Hold, Order, PactProposal, PlayerId, Press, UnitId,
)
from foedus.fog import visible_state_for


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _clean_self_note(raw: str) -> str:
    """Normalize a self-note for storage: strip surrounding whitespace only. The
    agent's own words are stored VERBATIM (no truncation, no content filtering) —
    this is the neutrality-exempt part, and the persisted record is the audit
    artifact, so it must be faithful. Total prompt growth is instead bounded by
    the last-N-games render cap (CampaignMemory.recent) plus the model's own
    ≤80-word instruction; a single note is never truncated."""
    return raw.strip()


class LLMDiplomat:
    """No-arg-constructed Agent backed by an LLMClient (see client.py).

    One instance is expected to play exactly one seat: the negotiate/
    orders caches below are keyed by (turn, player), which protects a
    single instance handed to multiple seats from cross-seat cache
    collisions, but the decision log and any FOEDUS_LLM_LOG_DIR file
    are still per-instance -- construct one LLMDiplomat per seat.

    Makes two LLM calls per round:

    - A "negotiate" call (triggered by whichever of choose_press /
      choose_pacts / accept_pacts the driver calls first each round,
      cached per (turn, player)) that decides press.stance,
      press.intents, and pact propose/accept together -- they all see
      the same fogged view at negotiate time, so one call answers all
      three. Because this call happens before this round's OTHER
      players' pact proposals exist, `accept_pacts` can only accept
      pacts proposed in a PRIOR round -- a same-round accept is a real
      information gap, not a bug (Pact terms are documented to allow
      "same or next round" acceptance, and next-round is always
      available).
    - An "orders" call, made once negotiation closes for the round.
      It is shown the intents this same instance already declared, so
      it can choose to honor or knowingly break them -- keeping any
      resulting BetrayalObservation a genuine model choice rather than
      an artifact of splitting negotiate/orders into two calls.

    Backend/transport failures (network error, timeout, API error) from
    `LLMClient.complete()` degrade to the same safe fallback as a parse
    failure -- Hold orders / neutral press, logged and flagged -- rather
    than raising through `play_game` and aborting the game.
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        recip_ledger: bool | None = None,
        campaign: bool | None = None,
    ) -> None:
        self._client: LLMClient = client if client is not None else make_client_from_env()
        self.decision_log: list[dict] = []
        self._negotiation_cache: dict[tuple[int, PlayerId], NegotiationDecision] = {}
        self._orders_cache: dict[tuple[int, PlayerId], dict[UnitId, Order]] = {}
        log_dir = os.environ.get("FOEDUS_LLM_LOG_DIR")
        self._log_dir = Path(log_dir) if log_dir else None
        # Reciprocation-memory arm (experiment toggle) and campaign (cross-game)
        # mode. Both default OFF; the constructor arg wins over the env var so
        # arms are the same code, one toggle apart.
        if recip_ledger is None:
            recip_ledger = _env_flag("FOEDUS_LLM_RECIP_LEDGER")
        if campaign is None:
            campaign = _env_flag("FOEDUS_LLM_CAMPAIGN")
        self._recip_ledger = recip_ledger
        # A within-game reciprocation accumulator is needed to RENDER the recip
        # block (recip arm) AND to BUILD the cross-game record (campaign mode) --
        # accumulation and rendering are decoupled: campaign mode accumulates
        # without rendering the block (that stays gated on _recip_ledger).
        self._memory: ReciprocationMemory | None = (
            ReciprocationMemory() if (recip_ledger or campaign) else None
        )
        # Cross-game memory: prior games' records + verbatim self-notes. Persists
        # across the games of a campaign (the instance is reused); None = the
        # single-game arms (prompt byte-identical, PRIOR GAMES never appears).
        self._campaign_memory: CampaignMemory | None = (
            CampaignMemory() if campaign else None
        )
        # Ruleset v1.1 identity context (stable handles for this game). None =>
        # seat-keyed rendering (single-game / pre-v1.1 arms unchanged). Set per
        # game by the campaign orchestrator via set_identity_context().
        self._identity: IdentityContext | None = None

    #: Opt-in marker read by foedus.loop.play_game: this agent is safe to
    #: pre-compute concurrently from a read-only snapshot. The per-(turn,
    #: player) negotiate/orders caches make prewarm_phase idempotent, so
    #: warming the cache off-thread and then letting play_game's sequential
    #: pass hit it is byte-identical to computing it inline. Heuristic agents
    #: do NOT set this, so play_game never pre-warms them (their invocation
    #: order -- and any RNG they draw -- stays exactly as today).
    supports_parallel_prewarm = True

    # --- Agent protocol -----------------------------------------------

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        return self._negotiate(state, player).press

    def choose_pacts(self, state: GameState, player: PlayerId) -> list[PactProposal]:
        return self._negotiate(state, player).proposals

    def accept_pacts(self, state: GameState, player: PlayerId) -> list[int]:
        return self._negotiate(state, player).accept_ids

    def choose_orders(self, state: GameState, player: PlayerId) -> dict[UnitId, Order]:
        key = (state.turn, player)
        cached = self._orders_cache.get(key)
        if cached is not None:
            return cached
        view = visible_state_for(state, player)
        prior = self._negotiation_cache.get(key)
        own_intents = prior.press.intents if prior is not None else []
        system, user = render_orders_prompt(state, view, player, own_intents,
                                            identity=self._identity)

        raw, error = self._complete(system, user)
        if error is not None:
            orders = {
                u.id: Hold() for u in state.units.values() if u.owner == player
            }
            self._log("orders", state, player, system, user,
                      f"<client error: {error}>", orders, True, 0)
        else:
            orders, fell_back, n_coerced = parse_orders_response(raw, state, player)
            self._log("orders", state, player, system, user, raw, orders,
                      fell_back, n_coerced)
        if self._memory is not None:
            # Ownership must come from the seat's OWN fogged view, not the
            # omniscient state: a Support can be legal against a unit outside
            # fog (2-hop move-support), and crediting its true owner would leak
            # information the seat never observed. An out-of-fog target maps to
            # owner=None and is simply not attributed (fog-legal by
            # construction; matches memory_metrics.parse_visible_owners).
            unit_owner = {u["id"]: u["owner"] for u in view["visible_units"]}
            self._memory.observe_orders(orders, unit_owner, player, state.turn)
        self._orders_cache[key] = orders
        return orders

    def chat_drafts(self, state: GameState, player: PlayerId) -> list[ChatDraft]:
        """v0 locked decision: structured press (stance + intents), no
        free-text chat -- see the First Light design doc, §2."""
        return []

    # --- parallel-seat pre-warm (opt-in; see supports_parallel_prewarm) ---

    def prewarm_phase(self, state: GameState, player: PlayerId, phase: str) -> None:
        """Populate this seat's decision cache for `phase` ("negotiate" or
        "orders") from `state`, off play_game's critical path.

        Idempotent by construction: it runs exactly the cached compute the
        matching choose_* call would run, so the sequential pass that follows
        returns the warmed value -- no second LLM call, no duplicate
        decision-log entry, no repeated reciprocation-memory observation.
        The "negotiate" cache also backs choose_pacts / accept_pacts.
        """
        if phase == "negotiate":
            self._negotiate(state, player)
        elif phase == "orders":
            self.choose_orders(state, player)
        else:
            raise ValueError(f"unknown prewarm phase: {phase!r}")

    # --- campaign (cross-game) lifecycle --------------------------------

    def set_identity_context(self, identity: "IdentityContext | None") -> None:
        """Set this game's stable-handle context (Ruleset v1.1). The campaign
        orchestrator calls this once per game (after `reset_for_new_game`) with
        the seat->handle map for the current rotation, so prompts show opponents
        by handle + a seat legend and cross-game facts key on the handle. Pass
        None to fall back to seat-keyed rendering."""
        self._identity = identity

    def reset_for_new_game(self) -> None:
        """Clear all WITHIN-game state so a reused instance starts the next
        campaign game clean, while KEEPING the cross-game memory.

        Critical for correctness: the per-(turn, player) negotiate/orders caches
        would otherwise return a PRIOR game's decision, since turn numbering
        restarts at 0 each game. Also resets the within-game reciprocation
        accumulator so counts don't bleed across games, and clears decision_log
        (the harness has already persisted the finished game's log by now)."""
        self._negotiation_cache = {}
        self._orders_cache = {}
        self.decision_log = []
        if self._memory is not None:
            self._memory = ReciprocationMemory()

    def finalize_game(
        self, final_state: GameState, player: PlayerId, *, seed: int, game_index: int
    ) -> None:
        """Record this game's compact cross-game entry: neutral facts (built
        fog-legally from the seat's own final view + within-game memory) plus the
        seat's OWN ≤80-word note. No-op when campaign mode is off.

        Makes ONE extra LLM call (the self-note); that call is deliberately NOT
        written to decision_log -- it is not a game decision and must not pollute
        the parse-fail counts. A failed call degrades to an empty note."""
        if self._campaign_memory is None:
            return
        view = visible_state_for(final_state, player)
        facts = build_game_facts(
            self._memory, view, player, seed=seed, game_index=game_index,
            identity=self._identity,
        )
        note = self._write_self_note(facts, player)
        self._campaign_memory.append(GameRecord(facts=facts, self_note=note))

    def _write_self_note(self, facts, player: PlayerId) -> str:
        system, user = render_self_note_prompt(facts, player)
        raw, error = self._complete(system, user)
        if error is not None or raw is None:
            return ""
        return _clean_self_note(raw)

    def campaign_records(self) -> list[GameRecord]:
        """All cross-game records recorded so far (empty when campaign mode is
        off). The harness serializes these per game for audit."""
        if self._campaign_memory is None:
            return []
        return self._campaign_memory.all()

    def load_campaign_records(self, records: list[GameRecord]) -> None:
        """Restore cross-game memory from persisted records (crash resume).

        A campaign runs in one process, so cross-game memory is normally in-RAM;
        if that process dies mid-match, the per-game `campaign_memory_*.json`
        files are the durable copy. This replays them onto a fresh reused agent
        so a resumed match continues with the same accumulated memory. No-op when
        campaign mode is off."""
        if self._campaign_memory is None:
            return
        for r in records:
            self._campaign_memory.append(r)

    # --- internals ------------------------------------------------------

    def _negotiate(self, state: GameState, player: PlayerId) -> NegotiationDecision:
        key = (state.turn, player)
        cached = self._negotiation_cache.get(key)
        if cached is not None:
            return cached
        view = visible_state_for(state, player)
        if self._memory is not None:
            self._memory.observe_view(view, player, state.turn)
        # Render the within-game RECIPROCATION RECORD block only in the recip
        # arm; campaign mode accumulates the same memory but does not render it.
        recip_for_prompt = self._memory if self._recip_ledger else None
        system, user = render_negotiation_prompt(
            state, view, player,
            recip_memory=recip_for_prompt,
            campaign_memory=self._campaign_memory,
            identity=self._identity,
        )

        raw, error = self._complete(system, user)
        if error is not None:
            decision = NegotiationDecision(Press(stance={}, intents=[]), fell_back=True)
            self._log("negotiate", state, player, system, user,
                      f"<client error: {error}>", decision, True, 0)
        else:
            decision = parse_negotiation_response(raw, state, player)
            self._log("negotiate", state, player, system, user, raw, decision,
                      decision.fell_back, decision.n_coerced)
        self._negotiation_cache[key] = decision
        return decision

    def _complete(self, system: str, user: str) -> tuple[str | None, str | None]:
        """Call the LLM client, isolating transport/backend failures
        (connection errors, timeouts, non-2xx responses, API errors)
        from parse failures -- both degrade the same way, but a
        transport error never reaches the parser. Returns
        (raw_response, error_repr); exactly one is None.
        """
        try:
            return self._client.complete(system, user), None
        except Exception as e:  # noqa: BLE001 - deliberate LLM-call safety boundary
            return None, repr(e)

    def _log(self, phase: str, state: GameState, player: PlayerId,
             system: str, user: str, raw: str, parsed: object,
             fell_back: bool, n_coerced: int) -> None:
        record = {
            "turn": state.turn,
            "phase": phase,
            "player": player,
            "prompt": {"system": system, "user": user},
            "raw_response": raw,
            "parsed": parsed,
            "fell_back": fell_back,
            "n_coerced": n_coerced,
        }
        self.decision_log.append(record)
        if self._log_dir is not None:
            # Under parallel_seats every seat's thread may hit this shared
            # FOEDUS_LLM_LOG_DIR concurrently; the mkdir is race-safe
            # (exist_ok=True) and each seat writes a DISTINCT player{p}.jsonl,
            # so this is the one shared-filesystem op on the concurrent path and
            # is intentionally concurrency-safe (no cross-seat file collision).
            self._log_dir.mkdir(parents=True, exist_ok=True)
            path = self._log_dir / f"player{player}.jsonl"
            with path.open("a") as f:
                f.write(json.dumps(record, default=str) + "\n")
