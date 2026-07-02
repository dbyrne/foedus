"""CoalitionBuilder — tight geographic bloc, reactive cross-support.

Picks the (up to 2) geographically nearest surviving non-self players as a
permanent bloc, measured by minimum BFS distance between any pair of units.
Falls back to lowest-id ordering when the agent has no units; lowest-id is
also the tiebreak for equal distances.

Declares ALLY toward bloc members only and supports their units reactively
(Support without require_dest, lowest-unit-id tiebreak). Outsiders get NEUTRAL
stance. The bet: geographically-coherent blocs translate tight-coordination
intent into actual map-level pile-ons — which, under the reciprocity model,
also build the bloc's reciprocation standing.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
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

            # Find geometrically reachable bloc partner units to support;
            # deterministic lowest-unit-id tiebreak.
            candidates: list[int] = []  # unit_ids
            for v in bloc_units:
                v_nbrs = m.neighbors(v.location)
                # Supporter must be adjacent to v's location OR share a neighbor
                reachable = (
                    v.location in my_nbrs
                    or bool(my_nbrs & v_nbrs)
                )
                if not reachable:
                    continue
                candidates.append(v.id)

            if candidates:
                orders[u.id] = Support(target=min(candidates))
                used.add(u.id)

        # Fallback: GreedyHold for units with no support opportunity
        fallback = self._inner.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)
        return orders

    def chat_drafts(self, state: GameState, player: PlayerId) -> list:
        return []
