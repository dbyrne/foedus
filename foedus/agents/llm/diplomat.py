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
from foedus.agents.llm.parse import (
    NegotiationDecision,
    parse_negotiation_response,
    parse_orders_response,
)
from foedus.agents.llm.render import render_negotiation_prompt, render_orders_prompt
from foedus.core import ChatDraft, GameState, Order, PactProposal, PlayerId, Press, UnitId
from foedus.fog import visible_state_for


class LLMDiplomat:
    """No-arg-constructed Agent backed by an LLMClient (see client.py).

    Makes two LLM calls per round:

    - A "negotiate" call (triggered by whichever of choose_press /
      choose_pacts / accept_pacts the driver calls first each round,
      cached by turn) that decides press.stance, press.intents, and
      pact propose/accept together -- they all see the same fogged
      view at negotiate time, so one call answers all three. Because
      this call happens before this round's OTHER players' pact
      proposals exist, `accept_pacts` can only accept pacts proposed
      in a PRIOR round -- a same-round accept is a real information
      gap, not a bug (Pact terms are documented to allow "same or next
      round" acceptance, and next-round is always available).
    - An "orders" call, made once negotiation closes for the round.
      It is shown the intents this same instance already declared, so
      it can choose to honor or knowingly break them -- keeping any
      resulting BetrayalObservation a genuine model choice rather than
      an artifact of splitting negotiate/orders into two calls.
    """

    def __init__(self, client: LLMClient | None = None) -> None:
        self._client: LLMClient = client if client is not None else make_client_from_env()
        self.decision_log: list[dict] = []
        self._negotiation_cache: dict[int, NegotiationDecision] = {}
        self._orders_cache: dict[int, dict[UnitId, Order]] = {}
        log_dir = os.environ.get("FOEDUS_LLM_LOG_DIR")
        self._log_dir = Path(log_dir) if log_dir else None

    # --- Agent protocol -----------------------------------------------

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
        view = visible_state_for(state, player)
        prior = self._negotiation_cache.get(state.turn)
        own_intents = prior.press.intents if prior is not None else []
        system, user = render_orders_prompt(state, view, player, own_intents)
        raw = self._client.complete(system, user)
        orders, fell_back, n_coerced = parse_orders_response(raw, state, player)
        self._log("orders", state, player, system, user, raw, orders,
                  fell_back, n_coerced)
        self._orders_cache[state.turn] = orders
        return orders

    def chat_drafts(self, state: GameState, player: PlayerId) -> list[ChatDraft]:
        """v0 locked decision: structured press (stance + intents), no
        free-text chat -- see the First Light design doc, §2."""
        return []

    # --- internals ------------------------------------------------------

    def _negotiate(self, state: GameState, player: PlayerId) -> NegotiationDecision:
        cached = self._negotiation_cache.get(state.turn)
        if cached is not None:
            return cached
        view = visible_state_for(state, player)
        system, user = render_negotiation_prompt(state, view, player)
        raw = self._client.complete(system, user)
        decision = parse_negotiation_response(raw, state, player)
        self._log("negotiate", state, player, system, user, raw, decision,
                  decision.fell_back, decision.n_coerced)
        self._negotiation_cache[state.turn] = decision
        return decision

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
