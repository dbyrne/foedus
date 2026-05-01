"""Opportunist — pure reactive-support specialist.

Unlike Cooperator, Opportunist does not wait for an ally to declare a
Move-on-supply Intent. Instead, every owned unit emits a reactive
Support(target=ally_unit) whenever any ally unit is geometrically reachable
as a support target — using the same adjacency criteria as legal.py.

The bet: reactive Support adapts to whatever the ally actually does this turn,
so blanket-support captures gains that destination-guessing agents miss.

Same leverage-ledger gate as Cooperator: don't subsidize freeriders.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Hold, Move, Order, PlayerId, Press, Stance, Support, UnitId,
)


class Opportunist:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        my_unit_ids = {u.id for u in my_units}
        orders: dict[UnitId, Order] = {}
        used: set[UnitId] = set()

        # Collect ally units (non-eliminated, non-self).
        ally_units = [
            u for u in state.units.values()
            if u.owner != player and u.owner not in state.eliminated
        ]

        # Build stance lookup from the latest submitted press.
        # round_press_pending is keyed by player id.
        def ally_stance_toward_me(ally_pid: PlayerId) -> Stance:
            press = state.round_press_pending.get(ally_pid)
            if press is None:
                return Stance.NEUTRAL
            return press.stance.get(player, Stance.NEUTRAL)

        for u in my_units:
            if u.id in used:
                continue
            my_nbrs = m.neighbors(u.location)

            # Find geometrically reachable ally units (same criteria as legal.py).
            candidates: list = []
            for v in ally_units:
                # Freerider gate.
                if state.leverage(player, v.owner) > 1:
                    continue
                # Geometric reachability: adjacent to v, OR shares a neighbor
                # with v (could support a Move from v).
                if v.location in my_nbrs:
                    reachable = True
                elif any(n in my_nbrs for n in m.neighbors(v.location)):
                    reachable = True
                else:
                    reachable = False
                if not reachable:
                    continue
                # Prefer ALLY stancers over NEUTRAL; skip HOSTILE.
                stance = ally_stance_toward_me(v.owner)
                if stance == Stance.HOSTILE:
                    continue
                stance_rank = 0 if stance == Stance.ALLY else 1
                candidates.append((stance_rank, v.id, v))

            if candidates:
                # Pick best candidate: lowest stance_rank, then lowest unit id.
                candidates.sort(key=lambda t: (t[0], t[1]))
                _, _, best = candidates[0]
                orders[u.id] = Support(target=best.id)
                used.add(u.id)

        # Fall back to GreedyHold for remaining own units.
        fallback = self._inner.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)

        return orders

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        from foedus.core import Intent
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

    def choose_aid(self, state: GameState,
                   player: PlayerId):
        """Spend tokens on any ALLY partner whose unit we are supporting.

        Prioritizes partners with negative leverage (they owe us).
        Stops spending on partners where leverage(self, partner) > 1.
        """
        from foedus.core import AidSpend
        balance = state.aid_tokens.get(player, 0)
        if balance <= 0:
            return []

        # Determine which units we plan to support this turn.
        my_orders = self.choose_orders(state, player)
        supported_unit_ids: set[UnitId] = {
            order.target
            for order in my_orders.values()
            if isinstance(order, Support)
        }
        if not supported_unit_ids:
            return []

        # Build partner priority list: partners with highest leverage-against-us
        # first (they owe us the most, spending on them is best for reciprocity).
        partner_priority: list[tuple[int, PlayerId]] = []
        for other_pid in range(state.config.num_players):
            if other_pid == player or other_pid in state.eliminated:
                continue
            if state.leverage(player, other_pid) > 1:
                continue
            lev_against_us = state.leverage(other_pid, player)
            partner_priority.append((lev_against_us, other_pid))
        partner_priority.sort(key=lambda x: -x[0])

        spends: list = []
        for _, other_pid in partner_priority:
            if len(spends) >= balance:
                break
            their_units = [
                u for u in state.units.values()
                if u.owner == other_pid and u.id in supported_unit_ids
            ]
            for u in their_units:
                if len(spends) >= balance:
                    break
                spends.append(AidSpend(target_unit=u.id))

        return spends[:balance]

    def chat_drafts(self, state, player):
        return []
