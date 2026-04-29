"""ReciprocalCooperator — same as Cooperator, but with memory.

EXPERIMENTAL probe (Bundle 4 follow-up). Same as Cooperator — reads
declared Move-on-supply intents from press and cross-supports adjacent
allies — but only supports a player who has previously cross-supported
ANY of our units. First contact is a freebie (everyone starts trustworthy);
players who never reciprocate get cut off after one turn.

This is the *agent-side* fix for the DishonestCooperator freerider
exploit, complementing the engine-side reciprocity rule
(FOEDUS_ALLIANCE_RECIPROCITY=1). It tackles the structural exploit
(combat-help + time arbitrage) that the engine-side rule can't address
because the engine doesn't know about agent-internal trust state.

Maintains a per-instance set of `trusted` PlayerIds. On each turn,
inspects state.press_history for the prior turn's SupportMove orders
... but those aren't in press_history (which is just the press tokens,
not orders). Instead, inspects the prior turn's resolution log via
state.log. Hacky and fragile but quick-and-dirty for the test.
"""

from __future__ import annotations

import re

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    GameState, Intent, Move, Order, PlayerId, Press, Stance, SupportMove,
    UnitId,
)


class ReciprocalCooperator:
    def __init__(self) -> None:
        self._inner = GreedyHold()
        # Players who've cross-supported any of our units in past turns.
        # Reset per-game (instance).
        self._trusted: set[PlayerId] = set()
        # Last turn we updated trust for, to avoid double-scanning.
        self._last_scan_turn = -1

    def _update_trust(self, state: GameState, player: PlayerId) -> None:
        """Scan the resolution log for cross-supports we received in any
        prior turn, since the last scan. Adds those players to trusted."""
        if state.turn <= self._last_scan_turn:
            return
        # Match e.g. "alliance bonus +3 to p2 (mover) and p1 (supporter) for capture at n7"
        # Or any past log line where a player p_X issued SupportMove targeting one of our units.
        # We don't have direct access to past canon orders, so we look for log
        # lines indicating successful cross-support of our units.
        # The simpler signal: the alliance-bonus log line shows mover+supporter pairs.
        for line in state.log:
            if "alliance bonus" not in line:
                continue
            # Extract: "to p{N} (mover) and p{X} (supporter)"
            m = re.search(r"to p(\d+) \(mover\) and p([\d,]+) \(supporter\)", line)
            if not m:
                continue
            mover = int(m.group(1))
            supporters = [int(x) for x in m.group(2).split(",")]
            if mover == player:
                # Other players supported our attack; they're trusted.
                self._trusted.update(supporters)
        self._last_scan_turn = state.turn

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        self._update_trust(state, player)
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        my_unit_ids = {u.id for u in my_units}
        orders: dict[UnitId, Order] = {}
        used: set[UnitId] = set()
        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid in state.eliminated:
                continue
            their_stance_toward_me = press.stance.get(player, Stance.NEUTRAL)
            if their_stance_toward_me == Stance.HOSTILE:
                continue
            # NEW: trust gate. First-contact (turn 0) is allowed; afterward
            # only support players who've supported us before.
            if state.turn > 0 and other_pid not in self._trusted:
                continue
            for intent in press.intents:
                order = intent.declared_order
                if not isinstance(order, Move):
                    continue
                if not m.is_supply(order.dest):
                    continue
                for u in my_units:
                    if u.id in used:
                        continue
                    if not m.is_adjacent(u.location, order.dest):
                        continue
                    if u.location == order.dest:
                        continue
                    target_unit = state.units.get(intent.unit_id)
                    if target_unit is None or target_unit.owner != other_pid:
                        continue
                    orders[u.id] = SupportMove(
                        target=intent.unit_id,
                        target_dest=order.dest,
                    )
                    used.add(u.id)
                    break
        fallback = self._inner.choose_orders(state, player)
        for uid in my_unit_ids:
            if uid not in orders:
                orders[uid] = fallback.get(uid)
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
