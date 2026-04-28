"""Simultaneous-order resolution and state transitions.

v1 simplifications vs. full DATC Diplomacy:
- Dislodged units are eliminated (no retreat/disband phase).
- No convoys (armies cannot cross water/non-adjacent).
- Head-to-head resolved by direct move-strength comparison.
- N-unit cycles (A->B->C->A) detected and resolved as all-success.
- No formal "defend strength vs hold strength" distinction; we use a single
  hold-strength for any non-moving unit that's being attacked.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Map,
    Move,
    NodeId,
    NodeType,
    Order,
    PlayerId,
    SupportHold,
    SupportMove,
    Unit,
    UnitId,
)


def initial_state(config: GameConfig, m: Map) -> GameState:
    """Build the starting GameState: one unit per player on their home node."""
    units: dict[UnitId, Unit] = {}
    ownership: dict[NodeId, PlayerId | None] = {n: None for n in m.nodes}
    next_id = 0
    for node_id in sorted(m.home_assignments.keys()):
        player = m.home_assignments[node_id]
        units[next_id] = Unit(id=next_id, owner=player, location=node_id)
        ownership[node_id] = player
        next_id += 1

    return GameState(
        turn=0,
        map=m,
        units=units,
        ownership=ownership,
        scores={p: 0.0 for p in range(config.num_players)},
        eliminated=set(),
        next_unit_id=next_id,
        config=config,
    )


# --- Order normalization ---------------------------------------------------


def _normalize(state: GameState, u_id: UnitId, order: Order,
               all_orders: dict[UnitId, Order]) -> Order:
    """Return order if valid, else Hold()."""
    unit = state.units[u_id]
    m = state.map

    if isinstance(order, Hold):
        return order

    if isinstance(order, Move):
        if not m.is_adjacent(unit.location, order.dest):
            return Hold()
        return order

    if isinstance(order, SupportHold):
        target = state.units.get(order.target)
        if target is None or target.id == u_id:
            return Hold()
        if not m.is_adjacent(unit.location, target.location):
            return Hold()
        target_order = all_orders.get(order.target, Hold())
        if not isinstance(target_order, Hold):
            return Hold()
        return order

    if isinstance(order, SupportMove):
        target = state.units.get(order.target)
        if target is None or target.id == u_id:
            return Hold()
        if not m.is_adjacent(unit.location, order.target_dest):
            return Hold()
        target_order = all_orders.get(order.target, Hold())
        if not isinstance(target_order, Move) or target_order.dest != order.target_dest:
            return Hold()
        # Refuse to support an attack on one's own unit (self-dislodge prevention).
        defender = state.unit_at(order.target_dest)
        if defender is not None and defender.owner == unit.owner:
            return Hold()
        return order

    return Hold()


# --- Support-cut detection -------------------------------------------------


def _is_cut(supporter: Unit, exclude_from: NodeId | None,
            canon: dict[UnitId, Order], state: GameState) -> bool:
    """Support is cut by any attack on supporter, except from `exclude_from`.
    Same-owner attacks don't count.
    """
    for u_id, order in canon.items():
        if u_id == supporter.id:
            continue
        if not isinstance(order, Move):
            continue
        if order.dest != supporter.location:
            continue
        attacker = state.units[u_id]
        if attacker.owner == supporter.owner:
            continue
        if exclude_from is None or attacker.location != exclude_from:
            return True
    return False


def _compute_cuts(canon: dict[UnitId, Order], state: GameState) -> set[UnitId]:
    cut: set[UnitId] = set()
    for u_id, order in canon.items():
        unit = state.units[u_id]
        if isinstance(order, SupportHold):
            if _is_cut(unit, None, canon, state):
                cut.add(u_id)
        elif isinstance(order, SupportMove):
            if _is_cut(unit, order.target_dest, canon, state):
                cut.add(u_id)
    return cut


def _find_cutters(supporter: Unit, exclude_from: NodeId | None,
                  canon: dict[UnitId, Order],
                  state: GameState) -> list[UnitId]:
    """Return the unit_ids of all enemy units whose Move into `supporter.location`
    cut this supporter's order. Mirrors _is_cut's filter exactly so reasons
    surfaced in the log match the resolver's actual cut decision.

    Used purely for logging (Haiku playtest UX gap: agents had no way to see
    why their support failed).
    """
    cutters: list[UnitId] = []
    for u_id, order in canon.items():
        if u_id == supporter.id:
            continue
        if not isinstance(order, Move):
            continue
        if order.dest != supporter.location:
            continue
        attacker = state.units[u_id]
        if attacker.owner == supporter.owner:
            continue
        if exclude_from is None or attacker.location != exclude_from:
            cutters.append(u_id)
    return cutters


# --- Strengths -------------------------------------------------------------


def _compute_strengths(canon: dict[UnitId, Order], cut: set[UnitId]
                       ) -> tuple[dict[UnitId, int], dict[UnitId, int]]:
    """Return (move_strength, hold_strength) per unit_id."""
    move_str: dict[UnitId, int] = {}
    hold_str: dict[UnitId, int] = {}
    for u_id, order in canon.items():
        if isinstance(order, Move):
            s = 1
            for v_id, v_order in canon.items():
                if v_id == u_id or v_id in cut:
                    continue
                if (isinstance(v_order, SupportMove)
                        and v_order.target == u_id
                        and v_order.target_dest == order.dest):
                    s += 1
            move_str[u_id] = s
        else:
            s = 1
            for v_id, v_order in canon.items():
                if v_id == u_id or v_id in cut:
                    continue
                if isinstance(v_order, SupportHold) and v_order.target == u_id:
                    s += 1
            hold_str[u_id] = s
    return move_str, hold_str


# --- Conflict resolution ---------------------------------------------------


def _resolve_h2h(canon: dict[UnitId, Order], move_str: dict[UnitId, int],
                 state: GameState) -> dict[UnitId, str]:
    """Detect head-to-head conflicts (A->B, B->A) and resolve them.

    Returns dict of unit_id -> 'success' | 'fail' | 'dislodged'.
    Same-owner head-to-heads always bounce (Rule X: cannot dislodge own unit).
    """
    out: dict[UnitId, str] = {}
    seen: set[UnitId] = set()
    for u_id, order in canon.items():
        if u_id in seen or not isinstance(order, Move):
            continue
        a = state.units[u_id]
        for v_id, v_order in canon.items():
            if v_id == u_id or v_id in seen or not isinstance(v_order, Move):
                continue
            b = state.units[v_id]
            if b.location == order.dest and v_order.dest == a.location:
                a_str = move_str[u_id]
                b_str = move_str[v_id]
                if a.owner == b.owner:
                    out[u_id] = "fail"
                    out[v_id] = "fail"
                elif a_str > b_str:
                    out[u_id] = "success"
                    out[v_id] = "dislodged"
                elif b_str > a_str:
                    out[u_id] = "dislodged"
                    out[v_id] = "success"
                else:
                    out[u_id] = "fail"
                    out[v_id] = "fail"
                seen.add(u_id)
                seen.add(v_id)
                break
    return out


def _resolve_moves(canon: dict[UnitId, Order], move_str: dict[UnitId, int],
                   hold_str: dict[UnitId, int], h2h: dict[UnitId, str],
                   state: GameState) -> dict[UnitId, str]:
    """Resolve all moves, returning unit_id -> outcome ('success', 'fail', 'dislodged')."""
    outcome = dict(h2h)

    # Group moves by destination, excluding head-to-head pairs already decided.
    moves_by_dest: dict[NodeId, list[UnitId]] = defaultdict(list)
    for u_id, order in canon.items():
        if isinstance(order, Move) and u_id not in h2h:
            moves_by_dest[order.dest].append(u_id)

    # For each destination, determine the unique strongest mover (or bounce).
    contest_winner: dict[NodeId, UnitId | None] = {}
    for dest, movers in moves_by_dest.items():
        sm = sorted(movers, key=lambda u: -move_str[u])
        if len(sm) >= 2 and move_str[sm[0]] == move_str[sm[1]]:
            contest_winner[dest] = None
            for u in movers:
                outcome[u] = "fail"
        else:
            contest_winner[dest] = sm[0]
            for u in sm[1:]:
                outcome[u] = "fail"

    # Iterate to resolve "vacating" chains.
    for _ in range(50):
        progress = False
        for dest, winner in list(contest_winner.items()):
            if winner is None or winner in outcome:
                continue
            atk_str = move_str[winner]
            attacker = state.units[winner]
            defender = state.unit_at(dest)
            if defender is None:
                outcome[winner] = "success"
                progress = True
                continue
            d_outcome = outcome.get(defender.id)
            d_order = canon[defender.id]
            if isinstance(d_order, Move):
                if d_outcome == "success":
                    # Defender vacated; attacker enters empty node.
                    outcome[winner] = "success"
                    progress = True
                    continue
                if d_outcome == "fail":
                    # Bounced defender holds with hold strength.
                    d_str = hold_str.get(defender.id, 1)
                    if attacker.owner == defender.owner:
                        # Rule X: cannot dislodge own unit.
                        outcome[winner] = "fail"
                    elif atk_str > d_str:
                        outcome[winner] = "success"
                        outcome[defender.id] = "dislodged"
                    else:
                        outcome[winner] = "fail"
                    progress = True
                    continue
                # Defender's outcome still pending — wait for next iteration.
            else:
                # Static defender (Hold / Support).
                d_str = hold_str.get(defender.id, 1)
                if attacker.owner == defender.owner:
                    # Rule X: cannot dislodge own unit.
                    outcome[winner] = "fail"
                elif atk_str > d_str:
                    outcome[winner] = "success"
                    outcome[defender.id] = "dislodged"
                else:
                    outcome[winner] = "fail"
                progress = True
        if not progress:
            break

    # Cycle detection for remaining unresolved moves (e.g. A->B->C->A).
    unresolved = [u for u, o in canon.items() if isinstance(o, Move) and u not in outcome]
    visited: set[UnitId] = set()
    for start in unresolved:
        if start in outcome or start in visited:
            continue
        chain: list[UnitId] = []
        curr = start
        while True:
            if curr in chain:
                # Cycle detected. If it closes back on `start` (chain[0]), all succeed.
                idx = chain.index(curr)
                cycle = chain[idx:]
                if cycle[0] == curr:
                    for u in cycle:
                        outcome[u] = "success"
                        visited.add(u)
                break
            chain.append(curr)
            order = canon.get(curr)
            if not isinstance(order, Move):
                break
            defender = state.unit_at(order.dest)
            if defender is None or defender.id == curr:
                break
            curr = defender.id

    # Anything still unresolved fails.
    for u, o in canon.items():
        if isinstance(o, Move) and u not in outcome:
            outcome[u] = "fail"

    return outcome


# --- Top-level turn function ----------------------------------------------


def _resolve_orders(state: GameState,
                    orders_by_player: dict[PlayerId, dict[UnitId, Order]]
                    ) -> GameState:
    """Internal: run order normalization, conflict resolution, build phase,
    scoring, and elimination, returning the post-resolution GameState.

    Called by both the legacy `resolve_turn` entry point and the new
    `finalize_round` (in foedus.press) which adds press-specific steps
    around the order resolution.
    """
    log: list[str] = [f"--- turn {state.turn + 1} ---"]

    # 1. Flatten + ownership-validate.
    flat: dict[UnitId, Order] = {}
    for player, pmap in orders_by_player.items():
        for u_id, order in pmap.items():
            unit = state.units.get(u_id)
            if unit is None or unit.owner != player:
                continue
            flat[u_id] = order
    for u_id in state.units:
        flat.setdefault(u_id, Hold())

    # 2. Normalize.
    canon: dict[UnitId, Order] = {
        u_id: _normalize(state, u_id, o, flat) for u_id, o in flat.items()
    }

    # 3. Cuts + strengths.
    cut = _compute_cuts(canon, state)
    # Surface cut-support events in the log so agents can see *why* a
    # supported move failed. (Both Haiku playtest agents flagged this as
    # the single biggest "explain failure" gap.)
    for supporter_id in sorted(cut):
        supporter = state.units[supporter_id]
        s_order = canon[supporter_id]
        exclude = (s_order.target_dest
                   if isinstance(s_order, SupportMove) else None)
        cutters = _find_cutters(supporter, exclude, canon, state)
        if cutters:
            cutter_s = ", ".join(f"u{c}" for c in sorted(cutters))
            log.append(
                f"  u{supporter_id} (p{supporter.owner}) support cut "
                f"by attack from {cutter_s}"
            )
    move_str, hold_str = _compute_strengths(canon, cut)

    # 4. Resolve.
    h2h = _resolve_h2h(canon, move_str, state)
    outcome = _resolve_moves(canon, move_str, hold_str, h2h, state)

    # 5. Apply: build new units dict, log moves and dislodgements.
    new_units: dict[UnitId, Unit] = {}
    for u_id, unit in state.units.items():
        result = outcome.get(u_id)
        if result == "dislodged":
            log.append(f"  u{u_id} (p{unit.owner}) dislodged at n{unit.location}")
            continue
        order = canon[u_id]
        if isinstance(order, Move) and result == "success":
            new_units[u_id] = replace(unit, location=order.dest)
            log.append(f"  u{u_id} (p{unit.owner}) moved n{unit.location} -> n{order.dest}")
        else:
            new_units[u_id] = unit
            if isinstance(order, Move):
                # Include attempted destination so agents can see what they
                # tried to do, not just "you bounced". (Haiku playtest UX.)
                log.append(
                    f"  u{u_id} (p{unit.owner}) bounced at n{unit.location} "
                    f"-> n{order.dest}"
                )

    # 6. Ownership: any node with a unit at end-of-turn is owned by that player;
    #    empty nodes retain prior ownership.
    new_owner = dict(state.ownership)
    for unit in new_units.values():
        new_owner[unit.location] = unit.owner

    # 7. Build phase (every config.build_period turns).
    next_id = state.next_unit_id
    new_turn = state.turn + 1
    if new_turn % state.config.build_period == 0:
        for player in range(state.config.num_players):
            if player in state.eliminated:
                continue
            supply = sum(1 for n, t in state.map.node_types.items()
                         if t in (NodeType.SUPPLY, NodeType.HOME)
                         and new_owner.get(n) == player)
            current_units = sum(1 for u in new_units.values() if u.owner == player)
            need = supply - current_units
            if need <= 0:
                continue
            occupied = {u.location for u in new_units.values()}
            # Sonnet playtest: prefer SUPPLY/HOME nodes over PLAIN, then by
            # node id. Without this, a low-id PLAIN absorbs a build slot
            # ahead of a higher-id supply, wasting the build.
            candidates = sorted(
                (n for n in state.map.nodes
                 if new_owner.get(n) == player and n not in occupied),
                key=lambda n: (not state.map.is_supply(n), n),
            )
            for n in candidates[:need]:
                new_units[next_id] = Unit(id=next_id, owner=player, location=n)
                log.append(f"  p{player} builds u{next_id} at n{n}")
                next_id += 1

    # 8. Tiered scoring: +1 per controlled supply this turn.
    new_scores = dict(state.scores)
    for player in range(state.config.num_players):
        if player in state.eliminated:
            continue
        supply = sum(1 for n, t in state.map.node_types.items()
                     if t in (NodeType.SUPPLY, NodeType.HOME)
                     and new_owner.get(n) == player)
        new_scores[player] = new_scores.get(player, 0.0) + supply

    # 9. Eliminations: 0 units AND 0 supply centers => out.
    new_elim = set(state.eliminated)
    for player in range(state.config.num_players):
        if player in new_elim:
            continue
        has_units = any(u.owner == player for u in new_units.values())
        has_supply = any(
            t in (NodeType.SUPPLY, NodeType.HOME) and new_owner.get(n) == player
            for n, t in state.map.node_types.items()
        )
        if not has_units and not has_supply:
            new_elim.add(player)
            log.append(f"  p{player} eliminated")

    return GameState(
        turn=new_turn,
        map=state.map,
        units=new_units,
        ownership=new_owner,
        scores=new_scores,
        eliminated=new_elim,
        next_unit_id=next_id,
        config=state.config,
        log=state.log + log,
    )


def resolve_turn(state: GameState,
                 orders_by_player: dict[PlayerId, dict[UnitId, Order]]
                 ) -> GameState:
    """Backward-compat entry point. Equivalent to the no-press resolution path.

    `orders_by_player[player][unit_id] = order`. Missing units default to Hold.
    Spoofed orders (a player ordering another's unit) are dropped silently.

    For new code prefer foedus.press.advance_turn or foedus.press.finalize_round.
    """
    return _resolve_orders(state, orders_by_player)
