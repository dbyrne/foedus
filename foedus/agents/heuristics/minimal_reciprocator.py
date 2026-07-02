"""MinimalReciprocator — free-rides but gives the bare minimum to game the gate.

Red-team probe for the reciprocity-gated alliance bonus (Primitive B). It looks
exactly like DishonestCooperator (declares ALLY, publishes truthful GreedyHold
Move-intents, so genuine cooperators support its attacks) but, instead of NEVER
reciprocating, it issues exactly ONE cross-player ally-Support per
reciprocation window — the cheapest attempt to clear the mover-side gate while
free-riding the rest of the time.

The point is to BOUND how much of the free-rider exploit survives the gate:
with a ratio floor above 1/W, one support per window keeps recip below the
floor, so this heuristic should land BELOW genuine Reciprocator/Cooperator.
If it climbs to the top, the gate is being cheaply gamed (a falsifier).

Strategy:
  Press: ALLY toward all + truthful GreedyHold Move-intents (== DishonestCooperator).
  Orders: on turns where turn % reciprocation_window == 0, give ONE reachable
    ally-Support (the token payment); every other turn, pure GreedyHold.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Intent, Move, Order, PlayerId, Press, Stance, Support, UnitId,
)


class MinimalReciprocator:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    def _token_support(self, state: GameState,
                       player: PlayerId) -> tuple[UnitId, UnitId] | None:
        """Find one (my_unit, ally_unit) pair where my_unit can back a
        non-hostile ally's declared Move. Returns None if none available."""
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid in state.eliminated:
                continue
            if press.stance.get(player, Stance.NEUTRAL) == Stance.HOSTILE:
                continue
            for intent in press.intents:
                order = intent.declared_order
                if not isinstance(order, Move):
                    continue
                ally_unit = state.units.get(intent.unit_id)
                if ally_unit is None or ally_unit.owner != other_pid:
                    continue
                for u in my_units:
                    if m.is_adjacent(u.location, order.dest) \
                            and u.location != order.dest:
                        return u.id, intent.unit_id
        return None

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        orders = self._inner.choose_orders(state, player)
        window = max(1, state.config.reciprocation_window)
        # One token support per window; free-ride (pure GreedyHold) otherwise.
        if state.turn % window == 0:
            pair = self._token_support(state, player)
            if pair is not None:
                my_uid, ally_uid = pair
                orders[my_uid] = Support(target=ally_uid)
        return orders

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        planned = self._inner.choose_orders(state, player)
        intents = [
            Intent(unit_id=uid, declared_order=order, visible_to=None)
            for uid, order in planned.items()
            if isinstance(order, Move)
        ]
        return Press(stance=opponents, intents=intents)

    def chat_drafts(self, state, player):
        return []
