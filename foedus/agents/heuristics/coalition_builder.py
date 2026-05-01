"""CoalitionBuilder — aid-chain maximalist with a permanent tight bloc.

v2: picks the (up to 2) geographically nearest surviving non-self players
as a permanent bloc, measured by minimum BFS distance between any pair of
units. Falls back to lowest-id ordering when the agent has no units.
Lowest-id is used as a tiebreak for equal distances.

Declares ALLY toward bloc members only, supports their units reactively
(Support without require_dest), and dumps every aid token on bloc partners
— distributed evenly to keep the leverage ledger balanced. Outsiders get
NEUTRAL stance and no aid.

The bet: geographically-coherent blocs translate the strategy's tight-
coordination intent into actual map-level pile-ons.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    AidSpend,
    GameState,
    Intent,
    Move,
    Order,
    PlayerId,
    Press,
    Stance,
    Support,
    UnitId,
)


class CoalitionBuilder:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    # ------------------------------------------------------------------
    # Bloc helpers
    # ------------------------------------------------------------------

    def _bfs_distance(self, state: GameState, src: int, dst: int) -> int:
        """Graph distance from src to dst; returns large int if unreachable."""
        if src == dst:
            return 0
        from collections import deque
        seen = {src}
        queue: deque[tuple[int, int]] = deque([(src, 0)])
        while queue:
            node, d = queue.popleft()
            for nbr in state.map.neighbors(node):
                if nbr in seen:
                    continue
                if not state.map.is_passable(nbr):
                    continue
                if nbr == dst:
                    return d + 1
                seen.add(nbr)
                queue.append((nbr, d + 1))
        return 10 ** 9

    def _bloc_partners(self, state: GameState, player: PlayerId) -> frozenset[PlayerId]:
        """Pick up to 2 nearest surviving partners by min unit-pair BFS distance.

        Falls back to lowest-id ordering for tiebreak and when the agent has
        no units (no geographic information available).
        """
        survivors = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        if not survivors:
            return frozenset()

        my_units = [u for u in state.units.values() if u.owner == player]
        if not my_units:
            # No units — fall back to lowest-id.
            return frozenset(sorted(survivors)[:2])

        distances: list[tuple[int, int]] = []  # (distance, partner_id)
        for partner in survivors:
            partner_units = [u for u in state.units.values() if u.owner == partner]
            if not partner_units:
                distances.append((10 ** 9, partner))
                continue
            min_d = min(
                self._bfs_distance(state, mu.location, pu.location)
                for mu in my_units
                for pu in partner_units
            )
            distances.append((min_d, partner))

        distances.sort(key=lambda x: (x[0], x[1]))
        chosen = [pid for _, pid in distances[:2]]
        return frozenset(chosen)

    # ------------------------------------------------------------------
    # Agent protocol
    # ------------------------------------------------------------------

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        bloc = self._bloc_partners(state, player)
        stance: dict[PlayerId, Stance] = {}
        for p in range(state.config.num_players):
            if p == player or p in state.eliminated:
                continue
            stance[p] = Stance.ALLY if p in bloc else Stance.NEUTRAL
        # Publish own GreedyHold-planned moves as intents for bloc partners
        planned = self._inner.choose_orders(state, player)
        intents = [
            Intent(unit_id=uid, declared_order=order, visible_to=None)
            for uid, order in planned.items()
            if isinstance(order, Move)
        ]
        return Press(stance=stance, intents=intents)

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        m = state.map
        bloc = self._bloc_partners(state, player)
        my_units = [u for u in state.units.values() if u.owner == player]
        my_unit_ids = {u.id for u in my_units}
        bloc_units = [u for u in state.units.values() if u.owner in bloc]

        orders: dict[UnitId, Order] = {}
        used: set[UnitId] = set()

        for u in my_units:
            if u.id in used:
                continue
            my_nbrs = m.neighbors(u.location)

            # Find geometrically reachable bloc partner units to support.
            # Prefer the partner we owe the most (lowest leverage toward them).
            candidates: list[tuple[float, int]] = []  # (leverage, unit_id)
            for v in bloc_units:
                v_nbrs = m.neighbors(v.location)
                # Supporter must be adjacent to v's location OR share a neighbor
                reachable = (
                    v.location in my_nbrs
                    or bool(my_nbrs & v_nbrs)
                )
                if not reachable:
                    continue
                # Patron-defense gate: skip bloc partners with high inverse leverage.
                if state.leverage(v.owner, player) > 2:
                    continue
                # Prefer partner with lowest leverage from our side (we owe them most)
                lev = state.leverage(player, v.owner)
                candidates.append((lev, v.id))

            if candidates:
                # Pick the unit whose partner we owe the most (lowest leverage)
                candidates.sort(key=lambda x: x[0])
                _, best_unit_id = candidates[0]
                orders[u.id] = Support(target=best_unit_id)
                used.add(u.id)

        # Fallback: GreedyHold for units with no support opportunity
        fallback = self._inner.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)
        return orders

    def choose_aid(self, state: GameState,
                   player: PlayerId) -> list[AidSpend]:
        """Spend every token on bloc partners, evenly distributed.

        Targets the partner unit furthest forward (most adjacencies to
        unowned supply nodes). Falls back to lowest-id partner unit.
        """
        balance = state.aid_tokens.get(player, 0)
        if balance <= 0:
            return []

        bloc = self._bloc_partners(state, player)
        if not bloc:
            return []

        # Check mutual-ALLY gate if press history exists.
        # At turn 0 (no history) we skip the gate — engine allows it.
        allowed_bloc: set[PlayerId] = set()
        if not state.press_history:
            allowed_bloc = set(bloc)
        else:
            last = state.press_history[-1]
            my_prev = last.get(player)
            for partner in bloc:
                if my_prev is None:
                    # No previous press from us — skip gate
                    allowed_bloc.add(partner)
                    continue
                their_prev = last.get(partner)
                if their_prev is None:
                    allowed_bloc.add(partner)
                    continue
                # Check mutual ALLY
                we_ally_them = my_prev.stance.get(partner, Stance.NEUTRAL) == Stance.ALLY
                they_ally_us = their_prev.stance.get(player, Stance.NEUTRAL) == Stance.ALLY
                if we_ally_them and they_ally_us:
                    allowed_bloc.add(partner)

        if not allowed_bloc:
            return []

        # Build list of partner units ordered by "frontier" score
        # (adjacencies to unowned supply/home nodes — more = further forward).
        m = state.map
        def frontier_score(unit_node: int) -> int:
            count = 0
            for nbr in m.neighbors(unit_node):
                if m.is_supply(nbr) and state.ownership.get(nbr) is None:
                    count += 1
            return count

        # Collect all partner units from allowed bloc, sorted by
        # (descending frontier, ascending unit_id) for round-robin fairness.
        partner_units: list[tuple[int, int, int]] = []  # (partner_pid, unit_id, node)
        for pid in sorted(allowed_bloc):
            # Patron-defense gate: skip bloc partners with high inverse leverage.
            if state.leverage(pid, player) > 2:
                continue
            for u in state.units.values():
                if u.owner == pid:
                    fs = frontier_score(u.location)
                    partner_units.append((pid, u.id, fs))

        # Sort: highest frontier first, then lowest unit_id for ties
        partner_units.sort(key=lambda x: (-x[2], x[1]))

        # Round-robin across bloc partners, spending full balance
        spends: list[AidSpend] = []
        if not partner_units:
            return []

        for i in range(balance):
            _, unit_id, _ = partner_units[i % len(partner_units)]
            spends.append(AidSpend(target_unit=unit_id))

        return spends

    def chat_drafts(self, state: GameState, player: PlayerId) -> list:
        return []
