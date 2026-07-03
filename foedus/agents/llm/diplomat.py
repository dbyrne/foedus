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

from foedus.agents.llm.client import LLMClient, make_client_from_env
from foedus.agents.llm.memory import ReciprocationMemory
from foedus.agents.llm.parse import (
    NegotiationDecision,
    parse_negotiation_response,
    parse_orders_response,
)
from foedus.agents.llm.render import render_negotiation_prompt, render_orders_prompt
from foedus.core import (
    ChatDraft, GameState, Hold, Order, PactProposal, PlayerId, Press, UnitId,
)
from foedus.fog import visible_state_for


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


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
    ) -> None:
        self._client: LLMClient = client if client is not None else make_client_from_env()
        self.decision_log: list[dict] = []
        self._negotiation_cache: dict[tuple[int, PlayerId], NegotiationDecision] = {}
        self._orders_cache: dict[tuple[int, PlayerId], dict[UnitId, Order]] = {}
        log_dir = os.environ.get("FOEDUS_LLM_LOG_DIR")
        self._log_dir = Path(log_dir) if log_dir else None
        # Reciprocation-memory arm (experiment toggle). Default OFF; the
        # constructor arg wins over FOEDUS_LLM_RECIP_LEDGER so the two arms are
        # the same code, one toggle apart. A live memory means the negotiation
        # prompt carries the RECIPROCATION RECORD block; None means it doesn't.
        if recip_ledger is None:
            recip_ledger = _env_flag("FOEDUS_LLM_RECIP_LEDGER")
        self._memory: ReciprocationMemory | None = (
            ReciprocationMemory() if recip_ledger else None
        )

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
        system, user = render_orders_prompt(state, view, player, own_intents)

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
            unit_owner = {uid: u.owner for uid, u in state.units.items()}
            self._memory.observe_orders(orders, unit_owner, player, state.turn)
        self._orders_cache[key] = orders
        return orders

    def chat_drafts(self, state: GameState, player: PlayerId) -> list[ChatDraft]:
        """v0 locked decision: structured press (stance + intents), no
        free-text chat -- see the First Light design doc, §2."""
        return []

    # --- internals ------------------------------------------------------

    def _negotiate(self, state: GameState, player: PlayerId) -> NegotiationDecision:
        key = (state.turn, player)
        cached = self._negotiation_cache.get(key)
        if cached is not None:
            return cached
        view = visible_state_for(state, player)
        if self._memory is not None:
            self._memory.observe_view(view, player, state.turn)
        system, user = render_negotiation_prompt(
            state, view, player, recip_memory=self._memory
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
            self._log_dir.mkdir(parents=True, exist_ok=True)
            path = self._log_dir / f"player{player}.jsonl"
            with path.open("a") as f:
                f.write(json.dumps(record, default=str) + "\n")
