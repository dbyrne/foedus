"""GameSession — one in-progress game with a mix of human + agent seats.

Each player_id (seat) is either:
- "human": orders arrive via HTTP from a UI client (Godot, web, terminal)
- "agent": an in-process Python agent constructed by Python import path
- "remote": a `RemoteAgent` pointing at a foedus.remote AgentServer

The session tracks pending human submissions; on `advance()` it asks each
agent for their orders and resolves the turn. If any human seat hasn't
submitted yet, advance() raises and the caller asks the human to act first.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from foedus.agents.base import Agent
from foedus.core import (
    ChatDraft,
    GameState,
    Order,
    PlayerId,
    Press,
    UnitId,
)
from foedus.legal import legal_orders_for_unit
from foedus.resolve import resolve_turn
from foedus.press import (
    finalize_round,
    is_chat_phase_complete,
    is_round_complete,
    record_chat_message,
    signal_chat_done,
    signal_done,
    submit_press_tokens,
)


SeatType = str  # "human" | "agent" | "remote"


# Bundle 6: sentinel error message fragments. The server.py HTTP layer
# substring-matches on these to map ValueErrors to specific HTTP codes
# (409 Conflict for duplicate signals, 425 Too Early for chat-phase).
# Keep raise sites and matchers using these constants so the mapping
# survives message refactors.
ERR_ALREADY_CHAT_DONE = "already chat_done this round"
ERR_ALREADY_COMMITTED = "already committed this round"
ERR_CHAT_PHASE_NOT_COMPLETE = "chat phase not complete; cannot commit yet"


@dataclass
class SeatSpec:
    """Per-player seat specification, supplied at game creation."""

    type: SeatType
    name: str | None = None         # display name (humans + agents)
    kind: str | None = None         # "module.ClassName" for type=agent
    args: dict[str, Any] = field(default_factory=dict)  # kwargs for agent ctor
    url: str | None = None          # for type=remote

    def __post_init__(self) -> None:
        if self.type not in ("human", "agent", "remote"):
            raise ValueError(f"unknown seat type: {self.type!r}")
        if self.type == "agent" and not self.kind:
            raise ValueError("agent seat requires `kind` (import path)")
        if self.type == "remote" and not self.url:
            raise ValueError("remote seat requires `url`")


def build_agent(seat: SeatSpec) -> Agent:
    """Construct an Agent for a non-human seat. Raises on misconfiguration."""
    if seat.type == "agent":
        assert seat.kind is not None
        if "." not in seat.kind:
            raise ValueError(
                f"agent kind must be 'module.ClassName' (got {seat.kind!r})"
            )
        module_path, class_name = seat.kind.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ValueError(f"cannot import {module_path!r}: {e}") from e
        cls = getattr(module, class_name, None)
        if cls is None:
            raise ValueError(
                f"module {module_path!r} has no attribute {class_name!r}"
            )
        return cls(**(seat.args or {}))
    if seat.type == "remote":
        try:
            from foedus.remote import RemoteAgent
        except ImportError as e:
            raise ValueError(
                "remote seats require foedus[remote]"
            ) from e
        assert seat.url is not None
        return RemoteAgent(seat.url)
    raise ValueError(f"cannot construct agent for seat type {seat.type!r}")


@dataclass
class GameSession:
    """One active game. Pure data + a small amount of logic; the HTTP layer
    is in `server.py`.
    """

    game_id: str
    state: GameState
    seats: dict[PlayerId, SeatSpec]
    agents: dict[PlayerId, Agent]                       # non-human seats only
    pending_orders: dict[PlayerId, dict[UnitId, Order]] = field(default_factory=dict)
    # Snapshots for replay — index 0 is the initial state, index N is the
    # state after `advance()` was called N times. The history grows
    # monotonically; nothing in here is mutated retroactively.
    history: list[GameState] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.history:
            self.history.append(self.state)
        # Bundle 6: pre-compute agent press+orders for round 0.
        if self.agents:
            self.init_round()

    # --- query helpers -----------------------------------------------------

    def is_human(self, player: PlayerId) -> bool:
        return self.seats[player].type == "human"

    def is_active(self, player: PlayerId) -> bool:
        return player not in self.state.eliminated

    def has_submitted(self, player: PlayerId) -> bool:
        return player in self.pending_orders

    def awaiting_humans(self) -> list[PlayerId]:
        """Active human seats that haven't submitted orders yet."""
        return sorted(
            p for p in range(self.state.config.num_players)
            if self.is_active(p)
            and self.is_human(p)
            and not self.has_submitted(p)
        )

    def can_resolve(self) -> bool:
        return not self.awaiting_humans()

    # --- order I/O ---------------------------------------------------------

    # --- press flow (Bundle 6) ---------------------------------------------

    def init_round(self) -> None:
        """Pre-compute press + orders for agent seats and mark them as
        chat_done / round_done so they don't block sync points.

        Called once at session creation (after __post_init__ snapshots
        the initial state) AND after each finalize_round in
        submit_press_commit.

        KNOWN LIMITATION: agent seats compute their press + orders BEFORE
        any human chat or press tokens are written to state for the round.
        For HeuristicAgent (which ignores chat/press) this is fine. For a
        hypothetical agent that reads same-round chat or inbound intents
        in choose_orders / choose_press, this would mean the agent acts on
        stale information. If that becomes a real use case, defer agent
        order computation to after `is_chat_phase_complete` returns True
        (the same trigger point where finalize_round currently fires) —
        an architectural change worth its own design pass.
        """
        for player, agent in self.agents.items():
            if not self.is_active(player):
                continue
            # Press: choose, submit, mark chat_done.
            press = (agent.choose_press(self.state, player)
                     if hasattr(agent, "choose_press")
                     else Press(stance={}, intents=[]))
            self.state = submit_press_tokens(self.state, player, press)
            self.state = signal_chat_done(self.state, player)
            # Orders: pre-compute and buffer for finalize.
            self.pending_orders[player] = agent.choose_orders(
                self.state, player
            )
            self.state = signal_done(self.state, player)

    def submit_press_chat(self, player: PlayerId,
                          draft: dict | None) -> dict:
        """Record a chat draft (or skip) for `player` and mark them
        chat_done. Returns engine drop info if the message was rejected.

        `draft` is None or `{}` to skip. Otherwise must have `body` and
        optional `recipients`.
        """
        if not self.is_human(player):
            raise ValueError(f"seat {player} is not human (LLM seat)")
        if not self.is_active(player):
            raise ValueError(f"player {player} is eliminated")
        if player in self.state.chat_done:
            raise ValueError(
                f"player {player} {ERR_ALREADY_CHAT_DONE}"
            )
        message_dropped = False
        drop_reason = None
        if draft:
            recipients_raw = draft.get("recipients")
            if recipients_raw is None:
                recipients = None
            else:
                recipients = frozenset(int(r) for r in recipients_raw)
            chat_draft = ChatDraft(
                recipients=recipients,
                body=str(draft.get("body", "")),
            )
            new_state = record_chat_message(
                self.state, player, chat_draft
            )
            if (new_state is self.state
                    or len(new_state.round_chat) ==
                        len(self.state.round_chat)):
                message_dropped = True
                drop_reason = (
                    f"engine dropped (len={len(chat_draft.body)}, "
                    f"cap={self.state.config.chat_char_cap})"
                )
            else:
                self.state = new_state
        self.state = signal_chat_done(self.state, player)
        return {
            "ok": True,
            "chat_phase_complete": is_chat_phase_complete(self.state),
            "message_dropped": message_dropped,
            "drop_reason": drop_reason,
        }

    def submit_press_commit(self, player: PlayerId,
                            press: "Press",
                            orders: dict[UnitId, Order],
                            aid_spends: list | None = None) -> dict:
        """Submit press tokens + (optional) aid spends + orders + implicit
        signal_done for `player`. If this commit completes the round, runs
        finalize_round and re-initializes for the next round.

        Returns whether the round was advanced and the resulting turn.
        """
        if not self.is_human(player):
            raise ValueError(f"seat {player} is not human (LLM seat)")
        if not self.is_active(player):
            raise ValueError(f"player {player} is eliminated")
        if not is_chat_phase_complete(self.state):
            raise ValueError(
                ERR_CHAT_PHASE_NOT_COMPLETE
            )
        if player in self.state.round_done:
            raise ValueError(
                f"player {player} {ERR_ALREADY_COMMITTED}"
            )
        self.state = submit_press_tokens(self.state, player, press)
        if aid_spends:
            from foedus.press import submit_aid_spends
            self.state = submit_aid_spends(self.state, player, aid_spends)
        self.pending_orders[player] = dict(orders)
        self.state = signal_done(self.state, player)
        round_advanced = False
        if is_round_complete(self.state):
            self.state = finalize_round(
                self.state, dict(self.pending_orders)
            )
            self.history.append(self.state)
            self.pending_orders.clear()
            round_advanced = True
            if not self.state.is_terminal():
                self.init_round()
        return {
            "ok": True,
            "round_advanced": round_advanced,
            "is_terminal": self.state.is_terminal(),
            "new_turn": self.state.turn,
        }

    def apply_press_update(self, player: PlayerId,
                           press_raw: dict,
                           aid_spends_raw: list) -> None:
        """Submit press tokens + aid spends WITHOUT signaling done.

        Allows revisable submissions during the chat phase. The engine emits
        IntentRevised events on every change and auto-clears signal_done for
        any dependent player whose committed plans referenced the revised
        (player, unit). Callers must guard against duplicate commits
        (409) before calling.
        """
        from foedus.core import Press, Stance
        from foedus.press import submit_aid_spends
        from foedus.remote.wire import deserialize_aid_spend, deserialize_intent

        # Parse stance.
        stance: dict[int, Stance] = {}
        for k, v in (press_raw.get("stance") or {}).items():
            stance[int(k)] = Stance(v)

        # Parse intents.
        intents = []
        for it_raw in (press_raw.get("intents") or []):
            intents.append(deserialize_intent(it_raw))

        press = Press(stance=stance, intents=intents)
        self.state = submit_press_tokens(self.state, player, press)

        # Parse + apply aid spends.
        if aid_spends_raw:
            spends = [deserialize_aid_spend(sp) for sp in aid_spends_raw]
            self.state = submit_aid_spends(self.state, player, spends)

    def submit_human_orders(self, player: PlayerId,
                            orders: dict[UnitId, Order]) -> None:
        if not self.is_human(player):
            raise ValueError(f"seat {player} is not human")
        if not self.is_active(player):
            raise ValueError(f"player {player} is eliminated")
        self.pending_orders[player] = dict(orders)

    def collect_all_orders(self) -> dict[PlayerId, dict[UnitId, Order]]:
        """Build the complete orders dict by combining pending humans + agents."""
        if not self.can_resolve():
            raise RuntimeError(
                f"cannot resolve: awaiting humans {self.awaiting_humans()}"
            )
        all_orders: dict[PlayerId, dict[UnitId, Order]] = {}
        for player in range(self.state.config.num_players):
            if not self.is_active(player):
                continue
            if self.is_human(player):
                all_orders[player] = self.pending_orders.get(player, {})
            else:
                agent = self.agents[player]
                all_orders[player] = agent.choose_orders(self.state, player)
        return all_orders

    # --- advancement -------------------------------------------------------

    def advance(self) -> None:
        """Collect orders, resolve one turn, clear human submissions."""
        all_orders = self.collect_all_orders()
        self.state = resolve_turn(self.state, all_orders)
        self.history.append(self.state)
        self.pending_orders.clear()

    def auto_advance(self, max_turns: int = 1000) -> int:
        """Advance turns automatically as long as no humans are blocking.

        Useful for "agent-only" games and to skip ahead through turns where
        every active human has already submitted. Returns the number of
        turns advanced.
        """
        n = 0
        while not self.state.is_terminal() and self.can_resolve() and n < max_turns:
            self.advance()
            n += 1
        return n

    # --- views -------------------------------------------------------------

    def view_for(self, player: PlayerId) -> dict[str, Any]:
        """Bundle of everything a UI client needs to render a turn for `player`.

        Includes the full state (UIs may want to honor fog visually but the
        engine still applies fog at resolve time), legal orders per owned
        unit, current score, who else is being awaited, and game-end signals.
        """
        return self._build_view(self.state, player, is_replay=False)

    def view_at_turn(self, turn: int, player: PlayerId) -> dict[str, Any]:
        """Replay view: state at snapshot index `turn`. Read-only; no
        legal_orders since you can't act in the past.
        """
        if not 0 <= turn < len(self.history):
            raise IndexError(
                f"turn {turn} out of range; available 0..{len(self.history) - 1}"
            )
        return self._build_view(self.history[turn], player, is_replay=True)

    def history_summary(self) -> dict[str, Any]:
        return {
            "current_turn": self.state.turn,
            "snapshots": list(range(len(self.history))),
        }

    # --- internal helpers -------------------------------------------------

    def _build_view(self, state: GameState, player: PlayerId,
                    *, is_replay: bool) -> dict[str, Any]:
        from foedus.remote.wire import (
            serialize_aid_spend,
            serialize_order,
            serialize_state,
        )
        my_units = [u for u in state.units.values() if u.owner == player]
        legal: dict[str, list[dict[str, Any]]] = {}
        if not is_replay:
            for u in my_units:
                legal[str(u.id)] = [
                    serialize_order(o)
                    for o in legal_orders_for_unit(state, u.id)
                ]

        # Bundle 4: surface the player's own tokens, the public trust ledger,
        # their committed aid spends this round (for revisability display),
        # and the betrayal observations they've received this game.
        my_betrayals = [
            {
                "turn": b.turn,
                "betrayer": b.betrayer,
                "intent": {
                    "unit_id": b.intent.unit_id,
                    "declared_order": serialize_order(b.intent.declared_order),
                    "visible_to": (None if b.intent.visible_to is None
                                   else sorted(b.intent.visible_to)),
                },
                "actual_order": serialize_order(b.actual_order),
            }
            for b in state.betrayals.get(player, [])
        ]
        # Last turn's locked press (so the client can render previous-round
        # stance / public intents from other players for context).
        last_press = state.press_history[-1] if state.press_history else {}
        last_press_serialized = {
            str(p): {
                "stance": {str(q): s.value for q, s in pr.stance.items()},
                "intents": [
                    {
                        "unit_id": i.unit_id,
                        "declared_order": serialize_order(i.declared_order),
                        "visible_to": (None if i.visible_to is None
                                       else sorted(i.visible_to)),
                    }
                    for i in pr.intents
                    # Filter private intents not addressed to `player`.
                    if i.visible_to is None or player in i.visible_to
                ],
            }
            for p, pr in last_press.items()
        }

        return {
            "game_id": self.game_id,
            "you": player,
            "turn": state.turn,
            "max_turns": state.config.max_turns,
            "state": serialize_state(state),
            "your_aid_tokens": state.aid_tokens.get(player, 0),
            "your_aid_pending": [
                serialize_aid_spend(s)
                for s in state.round_aid_pending.get(player, [])
            ],
            "your_betrayals": my_betrayals,
            "last_press": last_press_serialized,
            "your_units": [
                {"id": u.id, "owner": u.owner, "location": u.location}
                for u in my_units
            ],
            "legal_orders": legal,
            "awaiting_humans": [] if is_replay else self.awaiting_humans(),
            "submitted": False if is_replay else self.has_submitted(player),
            "is_terminal": state.is_terminal(),
            "detente_reached": state.detente_reached,
            "winner": state.winner,
            "winners": state.winners(),
            "scores": dict(state.scores),
            "eliminated": sorted(state.eliminated),
            "seats": {
                str(p): {
                    "type": s.type,
                    "name": s.name,
                    "kind": s.kind,
                    "url": s.url,
                }
                for p, s in self.seats.items()
            },
            "is_replay": is_replay,
            "current_turn": self.state.turn,
            "snapshot_count": len(self.history),
        }
