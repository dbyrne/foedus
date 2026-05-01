"""Opportunist v2 — two-tier pinned/reactive support specialist.

v1 emitted blanket reactive Support(target=ally) for any geometrically
reachable ally without reading declared intents, leading to wasted unit-turns
supporting allies who Hold or move into bounces.

v2 two-tier targeting in choose_orders:

  Tier 1 — PINNED support when intel is visible.
    Scan round_press_pending for a visible Move intent from any non-self,
    non-eliminated player. If the moving unit is geographically reachable from
    our unit AND the move destination is adjacent to our unit (geometric
    requirement for the pin), emit Support(target=ally_unit, require_dest=dest).
    Qualifies for the alliance-bonus +3. Prefer highest-value supply dest;
    tiebreak lowest target unit ID.

  Tier 2 — REACTIVE support when no Tier 1 match exists.
    Fall back to v1 behaviour: emit Support(target=ally_unit) (reactive) for
    any geometrically reachable ally. Prefer ALLY-toward-us over NEUTRAL;
    tiebreak lowest unit ID.

  Tier 3 — GreedyHold fallback.
    No reachable ally → GreedyHold.

Leverage gate applies in both Tier 1 and Tier 2 (don't subsidise freeriders).
HOSTILE-toward-us allies are skipped in both tiers.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Hold, Move, Order, PlayerId, Press, Stance, Support, UnitId,
)


class Opportunist:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ally_stance_toward_me(self, state: GameState,
                                player: PlayerId, ally_pid: PlayerId) -> Stance:
        press = state.round_press_pending.get(ally_pid)
        if press is None:
            return Stance.NEUTRAL
        return press.stance.get(player, Stance.NEUTRAL)

    def _is_freerider(self, state: GameState,
                       player: PlayerId, other: PlayerId) -> bool:
        return state.leverage(player, other) > 1

    # ------------------------------------------------------------------
    # choose_orders — two-tier support logic
    # ------------------------------------------------------------------

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        my_unit_ids = {u.id for u in my_units}
        orders: dict[UnitId, Order] = {}

        # Collect ally units (non-eliminated, non-self).
        ally_units = [
            u for u in state.units.values()
            if u.owner != player and u.owner not in state.eliminated
        ]

        for u in my_units:
            my_nbrs = m.neighbors(u.location)

            # -----------------------------------------------------------
            # Tier 1: pinned support — scan press for visible Move intents
            # -----------------------------------------------------------
            tier1_candidates: list = []
            for ally_pid, press in state.round_press_pending.items():
                if ally_pid == player or ally_pid in state.eliminated:
                    continue
                # Stance filter: skip HOSTILE allies.
                stance = self._ally_stance_toward_me(state, player, ally_pid)
                if stance == Stance.HOSTILE:
                    continue
                # Leverage gate.
                if self._is_freerider(state, player, ally_pid):
                    continue
                for intent in press.intents:
                    if not isinstance(intent.declared_order, Move):
                        continue
                    # The ally unit must belong to ally_pid.
                    ally_unit = state.units.get(intent.unit_id)
                    if ally_unit is None or ally_unit.owner != ally_pid:
                        continue
                    dest = intent.declared_order.dest
                    # Geometric requirement for pinned support:
                    #   our unit must be reachable from the ally unit
                    #   (adjacent to ally, or shares a neighbor with it),
                    #   AND dest must be in our neighbor set.
                    ally_loc = ally_unit.location
                    reachable = (
                        ally_loc in my_nbrs
                        or any(n in my_nbrs for n in m.neighbors(ally_loc))
                    )
                    if not reachable:
                        continue
                    if dest not in my_nbrs:
                        continue
                    # Supply value of destination (0 if not a supply node).
                    sv = m.supply_value(dest) if m.is_supply(dest) else 0
                    # Negate sv for sort (want highest first).
                    tier1_candidates.append((-sv, ally_unit.id, ally_unit, dest))

            if tier1_candidates:
                tier1_candidates.sort(key=lambda t: (t[0], t[1]))
                _, _, best, dest = tier1_candidates[0]
                orders[u.id] = Support(target=best.id, require_dest=dest)
                continue

            # -----------------------------------------------------------
            # Tier 2: reactive support — any geometrically reachable ally
            # -----------------------------------------------------------
            tier2_candidates: list = []
            for v in ally_units:
                if self._is_freerider(state, player, v.owner):
                    continue
                stance = self._ally_stance_toward_me(state, player, v.owner)
                if stance == Stance.HOSTILE:
                    continue
                # Geometric reachability.
                if v.location in my_nbrs:
                    reachable = True
                elif any(n in my_nbrs for n in m.neighbors(v.location)):
                    reachable = True
                else:
                    continue
                stance_rank = 0 if stance == Stance.ALLY else 1
                tier2_candidates.append((stance_rank, v.id, v))

            if tier2_candidates:
                tier2_candidates.sort(key=lambda t: (t[0], t[1]))
                _, _, best = tier2_candidates[0]
                orders[u.id] = Support(target=best.id)
                continue

            # Tier 3: GreedyHold (filled in below)

        # Fill remaining units with GreedyHold.
        fallback = self._inner.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)

        return orders

    # ------------------------------------------------------------------
    # choose_press — UNCHANGED from v1
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # choose_aid — tightened to concentrate on Tier 1 (pinned) targets
    # ------------------------------------------------------------------

    def choose_aid(self, state: GameState, player: PlayerId):
        """Spend tokens on ally units we are pinned-supporting this turn.

        Tier 1 pinned targets take priority; falls back to all supported units
        if no Tier 1 targets present. Leverage gate applied (no freeriders).
        """
        from foedus.core import AidSpend
        balance = state.aid_tokens.get(player, 0)
        if balance <= 0:
            return []

        my_orders = self.choose_orders(state, player)

        # Separate pinned (require_dest set) vs reactive supports.
        pinned_unit_ids: set[UnitId] = {
            order.target
            for order in my_orders.values()
            if isinstance(order, Support) and order.require_dest is not None
        }
        reactive_unit_ids: set[UnitId] = {
            order.target
            for order in my_orders.values()
            if isinstance(order, Support) and order.require_dest is None
        }

        # Prefer pinned targets; fall back to reactive.
        priority_unit_ids = pinned_unit_ids if pinned_unit_ids else reactive_unit_ids
        if not priority_unit_ids:
            return []

        # Build partner priority: highest leverage-against-us first.
        partner_priority: list[tuple[int, PlayerId]] = []
        for other_pid in range(state.config.num_players):
            if other_pid == player or other_pid in state.eliminated:
                continue
            if self._is_freerider(state, player, other_pid):
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
                if u.owner == other_pid and u.id in priority_unit_ids
            ]
            for u in their_units:
                if len(spends) >= balance:
                    break
                spends.append(AidSpend(target_unit=u.id))

        return spends[:balance]

    def chat_drafts(self, state, player):
        return []
