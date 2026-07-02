"""Shunner — a ledger-reading punisher of free-riders.

Ported from the 2026-07-02 freerider design pass (a throwaway press-probe that
was never committed; reconstructed here from its spec). Shunner reads the
public reciprocation ledger (Primitive B) and treats a player as a FREE-RIDER
iff it has taken ally support this window (received > 0) while its reciprocation
standing is below the floor (given/received < reciprocation_floor). This is the
`DishonestCooperator`/`MinimalReciprocator` signature: takes support, gives
little or none.

Against a detected free-rider Shunner:
  - declares HOSTILE (withdrawing the ALLY label),
  - refuses to Support it (denying the tempo bait), and
  - attacks its units that sit on supplies (withdrawing board immunity),
    coordinating a second adjacent unit as Support when available so the
    attack can actually dislodge.
Against everyone else it behaves like `Reciprocator`: declares ALLY and backs
non-hostile allies' declared Moves.

Detection keys on the same threshold the engine's alliance-bonus gate uses
(`reciprocation_floor`), and requires received > 0, so an honest cooperator
(which reciprocates, keeping standing >= floor) is never flagged. At no-retreat
lethality a lone Shunner is viable but cannot outrun the free-rider (punishing
is tempo-negative — single str-1 attacks bounce); the retreats mechanic is the
lever that is meant to make its punishment finally bite.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Intent, Move, Order, PlayerId, Press, Stance, Support, UnitId,
)


class Shunner:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    def _freeriders(self, state: GameState, player: PlayerId) -> set[PlayerId]:
        """Players (other than me, still active) that have taken ally support
        without reciprocating: received > 0 AND standing < floor."""
        floor = state.config.reciprocation_floor
        out: set[PlayerId] = set()
        for p in range(state.config.num_players):
            if p == player or p in state.eliminated:
                continue
            if (state.reciprocation_received(p) > 0
                    and state.reciprocation_standing(p) < floor):
                out.add(p)
        return out

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        m = state.map
        freeriders = self._freeriders(state, player)
        my_units = [u for u in state.units.values() if u.owner == player]
        my_unit_ids = {u.id for u in my_units}
        orders: dict[UnitId, Order] = {}
        used: set[UnitId] = set()

        # 1. Punish: attack free-rider units that sit on a supply. Coordinate a
        # second adjacent unit as Support so the attack can dislodge (str 2 vs a
        # lone holder's str 1).
        targets = sorted(
            (u for u in state.units.values()
             if u.owner in freeriders and m.is_supply(u.location)),
            key=lambda u: u.location,
        )
        for tgt in targets:
            adjacent = [
                u for u in my_units
                if u.id not in used
                and m.is_adjacent(u.location, tgt.location)
                and u.location != tgt.location
            ]
            if not adjacent:
                continue
            attacker = adjacent[0]
            orders[attacker.id] = Move(dest=tgt.location)
            used.add(attacker.id)
            if len(adjacent) >= 2:
                supporter = adjacent[1]
                orders[supporter.id] = Support(
                    target=attacker.id, require_dest=tgt.location
                )
                used.add(supporter.id)

        # 2. Reciprocate: back non-hostile, non-free-rider allies' declared
        # Moves (never a free-rider — that is the support we are denying).
        for other_pid, press in state.round_press_pending.items():
            if (other_pid == player or other_pid in state.eliminated
                    or other_pid in freeriders):
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
                    if u.id in used:
                        continue
                    if not m.is_adjacent(u.location, order.dest):
                        continue
                    if u.location == order.dest:
                        continue
                    orders[u.id] = Support(target=intent.unit_id)
                    used.add(u.id)
                    break

        # 3. Fallback: GreedyHold for anything not otherwise ordered.
        fallback = self._inner.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)
        return orders

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        freeriders = self._freeriders(state, player)
        stance = {
            p: (Stance.HOSTILE if p in freeriders else Stance.ALLY)
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        planned = self._inner.choose_orders(state, player)
        intents = [
            Intent(unit_id=uid, declared_order=order, visible_to=None)
            for uid, order in planned.items()
            if isinstance(order, Move)
        ]
        return Press(stance=stance, intents=intents)

    def chat_drafts(self, state, player):
        return []
