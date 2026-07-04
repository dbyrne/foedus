"""Agent-side reciprocation memory for LLMDiplomat.

A seat accumulates, across the turns it has played, a compact factual record of
what it has *observed* about each opponent — how often they declared ALLY toward
it, and how often it has spent an action supporting their units — plus its own
prior declared stances toward them. This is the "memory" the base LLMDiplomat
lacks: every turn it otherwise re-derives its read from a single fogged view,
which shows only the *last* round's stances and none of its own order history.

Fog-safety is structural: the memory ingests only a seat's own fogged view
(`public_stance_matrix`, `your_outbound_press`) and its own submitted orders. It
never touches another player's private information, and it only ever records a
stance that was declared *toward this seat* (never a relationship between two
other players).

There is deliberately NO "they supported my units" count here: the engine
records no pairwise support attribution (`SupportRound` is set-valued) and the
fog view exposes no executed-order data, so a directed executed-support count is
not fog-legally observable without an engine change (out of scope). The public
reciprocation standing already on the board (given/received) carries the
aggregate side of that.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from foedus.core import Order, PlayerId, Stance, Support, UnitId


@dataclass
class OpponentRecord:
    """Per-opponent counts, accumulated from this seat's own observations."""

    turns_observed: int = 0
    ally_toward_me: int = 0
    neutral_toward_me: int = 0
    hostile_toward_me: int = 0
    turns_i_supported_them: int = 0
    # Turns this opponent declared a Support *intent* toward one of my units,
    # visible to me. This is the fog-legal proxy for "they supported my units":
    # executed support attribution is NOT fog-observable (SupportRound is
    # set-valued; the view exposes no executed-order data), so we count the
    # declared, visible intent instead. Never surfaced in the within-game
    # RECIPROCATION RECORD block; used only by the cross-game record.
    their_support_intent_toward_me: int = 0
    # This seat's own declared stance toward this opponent, one entry per prior
    # turn (chronological); an undeclared turn reads as the game default,
    # "neutral". Rebuilt from `your_outbound_press` each turn.
    my_prior_stances: list[str] = field(default_factory=list)


class ReciprocationMemory:
    """Accumulates per-opponent `OpponentRecord`s for a single seat/game."""

    def __init__(self) -> None:
        self._records: dict[PlayerId, OpponentRecord] = {}
        self._stance_turns_seen: set[int] = set()
        self._order_turns_seen: set[int] = set()

    def record(self, pid: PlayerId) -> OpponentRecord:
        return self._records.setdefault(pid, OpponentRecord())

    def get(self, pid: PlayerId) -> OpponentRecord:
        """Non-mutating read: an unseen opponent returns a fresh default record
        WITHOUT registering it, so `opponents()` stays honest when the
        cross-game snapshot probes every seat."""
        return self._records.get(pid, OpponentRecord())

    def opponents(self) -> list[PlayerId]:
        return sorted(self._records)

    def observe_view(self, view: dict, me: PlayerId, turn: int) -> None:
        """Record, from a fogged view, each opponent's declared stance toward me
        and rebuild my own prior-stance history. Idempotent per `turn`.

        Skips entirely when there is no completed prior press yet (turn 0's
        stance matrix is all-default and carries no real declaration), keeping
        the ally-declaration denominator honest.
        """
        outbound = view.get("your_outbound_press") or []
        if not outbound:
            return
        if turn in self._stance_turns_seen:
            return
        self._stance_turns_seen.add(turn)

        matrix = view.get("public_stance_matrix") or {}
        for sender, stances in matrix.items():
            if sender == me:
                continue
            st = stances.get(me)
            if st is None:
                continue
            rec = self.record(sender)
            rec.turns_observed += 1
            if st == Stance.ALLY.value:
                rec.ally_toward_me += 1
            elif st == Stance.HOSTILE.value:
                rec.hostile_toward_me += 1
            else:
                rec.neutral_toward_me += 1

        # Their declared Support intents toward my units, visible to me
        # (fog.visible_state_for already filtered your_inbound_intents to intents
        # whose visible_to includes me). One increment per sender per turn,
        # regardless of how many of my units they pledged to back.
        #
        # Gated on `sender in matrix` (i.e. a still-live opponent, already
        # registered by the stance loop above): a seat eliminated on its final
        # turn is absent from the matrix but its last press can still carry an
        # intent, and registering it here from the intent ALONE would add a stray
        # opponent to opponents() -> an extra zero-count line in the recip block,
        # diverging from baseline. All live opponents are always in the matrix,
        # so this only drops a dead seat's final-turn intent (negligible).
        inbound = view.get("your_inbound_intents") or {}
        my_unit_ids = {
            u["id"] for u in (view.get("visible_units") or []) if u["owner"] == me
        }
        for sender, intents in inbound.items():
            if sender == me or sender not in matrix:
                continue
            if any(
                isinstance(it.declared_order, Support)
                and it.declared_order.target in my_unit_ids
                for it in intents
            ):
                self.record(sender).their_support_intent_toward_me += 1

        # Rebuild my own prior declared stances toward every opponent I have a
        # relationship with (either direction), one entry per completed round.
        relevant: set[PlayerId] = {
            s for s in matrix if s != me
        } | {
            t for press in outbound for t in press.stance if t != me
        }
        for p in relevant:
            rec = self.record(p)
            rec.my_prior_stances = [
                press.stance.get(p, Stance.NEUTRAL).value for press in outbound
            ]

    def observe_orders(
        self,
        orders: dict[UnitId, Order],
        unit_owner: dict[UnitId, PlayerId],
        me: PlayerId,
        turn: int,
    ) -> None:
        """Record, from this seat's own submitted orders, which opponents it
        supported this turn (one increment per opponent per turn, regardless of
        how many of their units it backed). Idempotent per `turn`."""
        if turn in self._order_turns_seen:
            return
        self._order_turns_seen.add(turn)

        supported: set[PlayerId] = set()
        for order in orders.values():
            if isinstance(order, Support):
                owner = unit_owner.get(order.target)
                if owner is not None and owner != me:
                    supported.add(owner)
        for p in supported:
            self.record(p).turns_i_supported_them += 1
