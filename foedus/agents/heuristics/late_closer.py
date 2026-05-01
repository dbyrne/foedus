"""LateCloser — information-asymmetry exploit.

Reads other players' submitted press intents (from state.round_press_pending)
at order-submission time and picks orders that exploit the picture.

The bet: in a turn where the simulator iterates agents in player order, agent N
sees players 0..N-1's already-submitted press in state.round_press_pending.
LateCloser ALWAYS reads this carefully and adapts. Even when no info is
available (it's player 0), it falls back to Greedy expansion — but its real
edge shows when it's seat 1, 2, or 3 with information.

Strategy:
  Press: ALLY toward all opponents + deliberately deceptive intents (worst-
    neighbor Move for each unit) to confuse other agents' support targeting.
  Orders: pinned Support on visible ally captures > snag undefended supplies >
    Greedy fallback. Deliberately ignores declared deceptive intents (accepts
    BetrayalObservation cost).
  Aid: spend on visible ally Moves to supply where mutual-ALLY status holds.
"""

from __future__ import annotations

from collections import deque

from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics._tiebreak import shuffled_neighbors
from foedus.core import (
    AidSpend,
    GameState,
    Intent,
    Move,
    NodeId,
    Order,
    PlayerId,
    Press,
    Stance,
    Support,
    UnitId,
)


class LateCloser:
    """Information-asymmetry exploit heuristic.

    Declares deceptive intents; exploits visible intents from earlier-seated
    players to pin-support their captures and snag aid-boosted supplies.
    Accepts BetrayalObservation cost as the price of the information edge.
    """

    def __init__(self) -> None:
        self._greedy = Greedy()

    # ------------------------------------------------------------------
    # Press
    # ------------------------------------------------------------------

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        """ALLY toward all; declare deliberately deceptive intents."""
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        intents = []
        m = state.map
        for unit in state.units.values():
            if unit.owner != player:
                continue
            neighbors = list(m.edges.get(unit.location, frozenset()))
            if not neighbors:
                continue
            # Pick the "worst" neighbor: fewest unowned supplies reachable 1 hop
            # from that neighbor, tie-broken by lowest node id.
            worst = min(
                neighbors,
                key=lambda n: (
                    sum(
                        1 for nn in m.edges.get(n, frozenset())
                        if m.is_supply(nn) and state.ownership.get(nn) != player
                    ),
                    n,
                ),
            )
            intents.append(Intent(
                unit_id=unit.id,
                declared_order=Move(dest=worst),
                visible_to=None,
            ))
        return Press(stance=opponents, intents=intents)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        my_unit_ids = {u.id for u in my_units}
        orders: dict[UnitId, Order] = {}
        used: set[UnitId] = set()

        # Build predicted ally move destinations from submitted press.
        # Entry: (ally_unit_id, dest_node, ally_player_id)
        predicted: list[tuple[UnitId, NodeId, PlayerId]] = []
        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid in state.eliminated:
                continue
            for intent in press.intents:
                # Skip intents not visible to us
                if (intent.visible_to is not None
                        and player not in intent.visible_to):
                    continue
                if not isinstance(intent.declared_order, Move):
                    continue
                predicted.append(
                    (intent.unit_id, intent.declared_order.dest, other_pid)
                )

        # Priority 1: pinned Support on visible ally captures of supply.
        for ally_uid, dest, ally_pid in predicted:
            if not m.is_supply(dest):
                continue
            ally_unit = state.units.get(ally_uid)
            if ally_unit is None or ally_unit.owner != ally_pid:
                continue
            # Check that dest is not defended by the ally themselves
            # (they're moving to it, so no defender issue from their side).
            for u in my_units:
                if u.id in used:
                    continue
                if not m.is_adjacent(u.location, dest):
                    continue
                if u.location == dest:
                    continue
                orders[u.id] = Support(target=ally_uid, require_dest=dest)
                used.add(u.id)
                break

        # Priority 2: snag undefended supplies not targeted by predicted allies.
        predicted_dests = {dest for _, dest, _ in predicted}
        for u in my_units:
            if u.id in used:
                continue
            # Find adjacent unowned supply not in predicted_dests
            best_supply: NodeId | None = None
            for nbr in sorted(m.edges.get(u.location, frozenset())):
                if (m.is_supply(nbr)
                        and state.ownership.get(nbr) != player
                        and nbr not in predicted_dests
                        and state.unit_at(nbr) is None):
                    best_supply = nbr
                    break
            if best_supply is not None:
                orders[u.id] = Move(dest=best_supply)
                used.add(u.id)

        # Priority 3: Greedy fallback for remaining units.
        fallback = self._greedy.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)

        return orders

    # ------------------------------------------------------------------
    # Aid
    # ------------------------------------------------------------------

    def choose_aid(self, state: GameState, player: PlayerId) -> list[AidSpend]:
        balance = state.aid_tokens.get(player, 0)
        if balance <= 0:
            return []
        if not state.press_history:
            return []
        last = state.press_history[-1]
        my_prev = last.get(player)
        if my_prev is None:
            return []

        m = state.map
        spends: list[AidSpend] = []

        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid in state.eliminated:
                continue
            # Mutual-ALLY gate: both declared ALLY in the prior turn.
            their_prev = last.get(other_pid)
            if their_prev is None:
                continue
            if my_prev.stance.get(other_pid, Stance.NEUTRAL) != Stance.ALLY:
                continue
            if their_prev.stance.get(player, Stance.NEUTRAL) != Stance.ALLY:
                continue
            for intent in press.intents:
                if (intent.visible_to is not None
                        and player not in intent.visible_to):
                    continue
                order = intent.declared_order
                if not isinstance(order, Move):
                    continue
                if not m.is_supply(order.dest):
                    continue
                # Defender check: only aid if dest is undefended or weakly held.
                defender = state.unit_at(order.dest)
                if defender is not None and defender.owner == other_pid:
                    continue  # they're already there
                ally_unit = state.units.get(intent.unit_id)
                if ally_unit is None or ally_unit.owner != other_pid:
                    continue
                spends.append(AidSpend(target_unit=intent.unit_id))
                if len(spends) >= balance:
                    break
            if len(spends) >= balance:
                break

        return spends[:balance]

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def chat_drafts(self, state: GameState, player: PlayerId) -> list:
        return []
