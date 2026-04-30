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

import math
import os
import random
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
    Support,
    SupportHold,
    SupportLapsed,
    SupportMove,
    Unit,
    UnitId,
)


def _assign_high_value_supplies(m: Map, config: GameConfig) -> Map:
    """Bundle 5b (C3): mark a fraction of non-HOME SUPPLY nodes as
    high-value (yielding `high_value_supply_yield` per turn instead of 1).

    Deterministic from `config.seed` via a derived RNG namespace, so the
    same config + map produce the same value assignment. Returns the
    input map unchanged when fraction or yield disable the mechanic.
    """
    fraction = config.high_value_supply_fraction
    yield_ = config.high_value_supply_yield
    if fraction <= 0 or yield_ <= 1:
        return m
    eligible = sorted(
        n for n in m.nodes if m.node_types[n] == NodeType.SUPPLY
    )
    if not eligible:
        return m
    count = int(math.floor(len(eligible) * fraction + 0.5))
    if count <= 0:
        return m
    rng = random.Random((config.seed or 0) * 17 + 7)
    chosen = rng.sample(eligible, min(count, len(eligible)))
    new_values = dict(m.supply_values)
    for n in chosen:
        new_values[n] = yield_
    return replace(m, supply_values=new_values)


def initial_state(config: GameConfig, m: Map) -> GameState:
    """Build the starting GameState: one unit per player on their home node."""
    # Bundle 5b (C3): apply high-value supply assignment if mapgen didn't
    # already populate it. Skip when supply_values already non-empty (e.g.,
    # state was wire-loaded or the caller pre-assigned).
    if not m.supply_values:
        m = _assign_high_value_supplies(m, config)

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

    if isinstance(order, Support):
        target = state.units.get(order.target)
        if target is None or target.id == u_id:
            return Hold()
        target_order = all_orders.get(order.target, Hold())

        # Pin variant: behaves like legacy SupportMove, exact-match required.
        if order.require_dest is not None:
            if not m.is_adjacent(unit.location, order.require_dest):
                return Hold()
            if not isinstance(target_order, Move) or target_order.dest != order.require_dest:
                return Hold()
            defender = state.unit_at(order.require_dest)
            if defender is not None and defender.owner == unit.owner:
                return Hold()
            return order

        # Reactive default: support whatever target's canon order does.
        if isinstance(target_order, Move):
            if not m.is_adjacent(unit.location, target_order.dest):
                return Hold()
            defender = state.unit_at(target_order.dest)
            if defender is not None and defender.owner == unit.owner:
                return Hold()
            return order
        # target holds, supports, or supports-a-supporter: support lands at
        # target's location (E6 — supporting a supporter is supporting them
        # in place).
        if not m.is_adjacent(unit.location, target.location):
            return Hold()
        return order

    return Hold()


def _normalize_with_reason(
    state: GameState, u_id: UnitId, order: Order,
    all_orders: dict[UnitId, Order],
) -> tuple[Order, str | None]:
    """Same as _normalize but returns (canon, lapse_reason).

    lapse_reason is one of the SupportLapsed.reason literals when a Support
    or legacy SupportHold/SupportMove gets normalized to Hold; None for
    successful normalizations or non-support orders.
    """
    unit = state.units[u_id]
    m = state.map

    if isinstance(order, (Hold, Move)):
        return _normalize(state, u_id, order, all_orders), None

    if isinstance(order, Support):
        target = state.units.get(order.target)
        if target is None:
            return Hold(), "target_destroyed"
        if target.id == u_id:
            return Hold(), "geometry_break"  # self-support
        target_order = all_orders.get(order.target, Hold())

        if order.require_dest is not None:
            if not m.is_adjacent(unit.location, order.require_dest):
                return Hold(), "geometry_break"
            if not isinstance(target_order, Move) or target_order.dest != order.require_dest:
                return Hold(), "pin_mismatch"
            defender = state.unit_at(order.require_dest)
            if defender is not None and defender.owner == unit.owner:
                return Hold(), "self_dislodge_blocked"
            return order, None

        if isinstance(target_order, Move):
            if not m.is_adjacent(unit.location, target_order.dest):
                return Hold(), "geometry_break"
            defender = state.unit_at(target_order.dest)
            if defender is not None and defender.owner == unit.owner:
                return Hold(), "self_dislodge_blocked"
            return order, None
        # Hold / Support / SupportMove / SupportHold — support lands at target's location.
        if not m.is_adjacent(unit.location, target.location):
            return Hold(), "geometry_break"
        return order, None

    # Legacy SupportHold / SupportMove paths — unchanged for now.
    canon = _normalize(state, u_id, order, all_orders)
    if canon == Hold() and not isinstance(order, Hold):
        return canon, "geometry_break"
    return canon, None


# --- Support-cut detection -------------------------------------------------


def _find_cutters(supporter: Unit, exclude_from: NodeId | None,
                  canon: dict[UnitId, Order],
                  state: GameState) -> list[UnitId]:
    """Return the unit_ids of all enemy units whose Move into `supporter.location`
    cuts this supporter's order. Same-owner attacks don't count; the
    `exclude_from` location is exempted (it's the SupportMove's target_dest,
    where the supporter is currently helping the attacker).

    The single source of truth for cut filtering: `_is_cut` is a thin wrapper
    that returns `bool(_find_cutters(...))`, and the cut-event log loop in
    `_resolve_orders` consumes the same list. Don't drift these.
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


def _is_cut(supporter: Unit, exclude_from: NodeId | None,
            canon: dict[UnitId, Order], state: GameState) -> bool:
    """Support is cut iff any enemy unit moves into the supporter's location
    (excluding the SupportMove's target_dest). Delegates to `_find_cutters`
    so the filter logic stays single-sourced.
    """
    return bool(_find_cutters(supporter, exclude_from, canon, state))


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
        elif isinstance(order, Support):
            target = state.units.get(order.target)
            target_order = canon.get(order.target, Hold()) if target else Hold()
            # Determine the "exclude_from" — for a reactive support of a Move,
            # the supporter is helping at target's destination, so attacks
            # FROM that destination shouldn't count as cuts (matches the
            # SupportMove convention).
            if order.require_dest is not None:
                exclude = order.require_dest
            elif isinstance(target_order, Move):
                exclude = target_order.dest
            else:
                exclude = None
            if _is_cut(unit, exclude, canon, state):
                cut.add(u_id)
    return cut


# --- Strengths -------------------------------------------------------------


def _compute_aid_per_unit(state: GameState,
                          canon: dict[UnitId, Order]) -> dict[UnitId, int]:
    """Bundle 4 (reactive aid): count AidSpends that landed on each unit.

    A spend lands iff the target unit still exists (i.e., its owner is not
    eliminated and it appears in canon). Multiple spenders aiding the same
    unit stack additively. No target_order match required.
    """
    out: dict[UnitId, int] = defaultdict(int)
    for spender, spends in state.round_aid_pending.items():
        if spender in state.eliminated:
            continue
        for spend in spends:
            target_unit = state.units.get(spend.target_unit)
            if target_unit is None:
                continue
            if target_unit.owner == spender:
                continue  # safeguard
            if spend.target_unit not in canon:
                continue
            out[spend.target_unit] += 1
    return dict(out)


def _compute_strengths(canon: dict[UnitId, Order], cut: set[UnitId],
                       state: GameState,
                       aid_per_unit: dict[UnitId, int]
                       ) -> tuple[
                           dict[UnitId, int],
                           dict[UnitId, int],
                           list[tuple[UnitId, PlayerId, PlayerId, int]],
                       ]:
    """Return (move_strength, hold_strength, leverage_events) per unit_id.

    `leverage_events` is a list of (u_id, attacker_pid, target_pid, bonus)
    tuples — one per Move whose leverage bonus is non-zero. The caller
    logs these for instrumentation; the return value of the strengths is
    unaffected.

    Bundle 4 additions:
    - +`aid_per_unit[u]` to a unit's own strength (its move or its hold).
    - +`aid_per_unit[v]` to a support's contribution (so aided SupportMove
      contributes 2 to the supported unit's strength rather than 1).
    - Leverage bonus on Moves: when A's Move targets a hex owned by player B
      (or containing B's unit), add `state.leverage_bonus(A, B)` to A's
      move strength.
    """
    move_str: dict[UnitId, int] = {}
    hold_str: dict[UnitId, int] = {}
    leverage_events: list[tuple[UnitId, PlayerId, PlayerId, int]] = []
    for u_id, order in canon.items():
        unit = state.units[u_id]
        if isinstance(order, Move):
            s = 1 + aid_per_unit.get(u_id, 0)
            # Leverage bonus: pick the most-relevant defender at dest.
            target_pid: PlayerId | None = None
            occupant = state.unit_at(order.dest)
            if occupant is not None and occupant.owner != unit.owner:
                target_pid = occupant.owner
            else:
                ow = state.ownership.get(order.dest)
                if ow is not None and ow != unit.owner:
                    target_pid = ow
            if target_pid is not None:
                lev = state.leverage_bonus(unit.owner, target_pid)
                s += lev
                if lev > 0:
                    leverage_events.append(
                        (u_id, unit.owner, target_pid, lev)
                    )
            for v_id, v_order in canon.items():
                if v_id == u_id or v_id in cut:
                    continue
                if (isinstance(v_order, SupportMove)
                        and v_order.target == u_id
                        and v_order.target_dest == order.dest):
                    s += 1 + aid_per_unit.get(v_id, 0)
                if isinstance(v_order, Support) and v_order.target == u_id:
                    # Reactive support backing this move: lands iff target's
                    # canon move-dest matches the supporter's geometry.
                    if v_order.require_dest is not None:
                        if v_order.require_dest != order.dest:
                            continue
                    # Geometry already validated in _normalize; if v_order
                    # made it into canon as a non-Hold, it lands.
                    s += 1 + aid_per_unit.get(v_id, 0)
            move_str[u_id] = s
        else:
            s = 1 + aid_per_unit.get(u_id, 0)
            for v_id, v_order in canon.items():
                if v_id == u_id or v_id in cut:
                    continue
                if isinstance(v_order, SupportHold) and v_order.target == u_id:
                    s += 1 + aid_per_unit.get(v_id, 0)
                if isinstance(v_order, Support) and v_order.target == u_id:
                    # Reactive support backing this hold (target is holding).
                    s += 1 + aid_per_unit.get(v_id, 0)
            hold_str[u_id] = s
    return move_str, hold_str, leverage_events


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
    canon: dict[UnitId, Order] = {}
    lapses: list[SupportLapsed] = []
    for u_id, o in flat.items():
        c, reason = _normalize_with_reason(state, u_id, o, flat)
        canon[u_id] = c
        if reason is not None and isinstance(o, (Support, SupportHold, SupportMove)):
            target_id = (
                o.target if hasattr(o, "target") else u_id
            )
            lapses.append(SupportLapsed(
                turn=state.turn + 1,
                supporter=u_id,
                target=target_id,
                reason=reason,  # type: ignore[arg-type]
            ))

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
    aid_per_unit = _compute_aid_per_unit(state, canon)
    move_str, hold_str, leverage_events = _compute_strengths(
        canon, cut, state, aid_per_unit
    )
    for u_id, attacker_pid, target_pid, lev in leverage_events:
        log.append(
            f"  leverage bonus +{lev} to p{attacker_pid} (via u{u_id}) "
            f"vs p{target_pid}"
        )

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

    # 6. Ownership update.
    #
    # Mechanic A (Bundle 2): supply/home ownership only flips on
    # combat capture (a unit dislodged on the supply) OR after a unit
    # has been on the supply for a full turn (held start-of-N to
    # end-of-N).  Walk-ins onto undefended supplies do NOT flip
    # ownership immediately — the walker must hold for the next full
    # turn (rule (b) on turn N+1) to lock it in.
    #
    # Plain nodes flip every turn based on end-of-turn occupant
    # (unchanged from prior behavior).
    #
    # Spec: docs/superpowers/specs/2026-04-29-supply-ownership-cadence-design.md
    new_owner = dict(state.ownership)

    # Snapshot start-of-turn supply occupants from `state.units` (the
    # input state, before this turn's moves resolved).
    start_supply_occupants: dict[NodeId, PlayerId] = {}
    for unit in state.units.values():
        if state.map.is_supply(unit.location):
            start_supply_occupants[unit.location] = unit.owner

    # Rule (a) — dislodgement transfers ownership immediately.  Find
    # the successful attacker who entered the dislodged unit's node.
    for u_id, outcome_val in outcome.items():
        if outcome_val != "dislodged":
            continue
        defender = state.units[u_id]
        if not state.map.is_supply(defender.location):
            continue
        attacker_id = next(
            (uid for uid, o in canon.items()
             if isinstance(o, Move)
             and o.dest == defender.location
             and outcome.get(uid) == "success"),
            None,
        )
        if attacker_id is not None:
            new_owner[defender.location] = state.units[attacker_id].owner

    # Rule (b) — same player on supply at start AND end of turn flips
    # ownership.  Iterate end-of-turn supply occupants from new_units
    # and check against the start-of-turn snapshot.
    #
    # Write-order safety: rule (b) cannot stomp rule (a)'s assignment
    # for a freshly-dislodged supply, because the dislodging attacker
    # was NOT at the defender's node at start of turn — so the
    # start_supply_occupants check below is False and rule (b) does
    # not fire for that node.  Don't reorder these two loops without
    # re-checking this invariant.
    for unit in new_units.values():
        if not state.map.is_supply(unit.location):
            continue
        if start_supply_occupants.get(unit.location) == unit.owner:
            new_owner[unit.location] = unit.owner

    # Plain nodes: every-turn flip (unchanged).
    for unit in new_units.values():
        if not state.map.is_supply(unit.location):
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

    # 8. Tiered scoring: +map.supply_value(n) per controlled supply this turn.
    # Bundle 5b (C3): supply_value defaults to 1 (v1 behavior) but is 2 for
    # the small fraction marked as high-value at mapgen. HOME nodes always
    # yield 1 — high-value heterogeneity is for contested non-home supplies.
    new_scores = dict(state.scores)
    for player in range(state.config.num_players):
        if player in state.eliminated:
            continue
        supply_score = sum(
            state.map.supply_value(n)
            for n, t in state.map.node_types.items()
            if t in (NodeType.SUPPLY, NodeType.HOME)
            and new_owner.get(n) == player
        )
        new_scores[player] = new_scores.get(player, 0.0) + supply_score

    # 8b. EXPERIMENTAL: alliance-capture bonus.
    #
    # When a Move successfully captures a supply AND a SupportMove from a
    # DIFFERENT player exists this turn with matching (target_unit,
    # target_dest), both the capturing player and each cross-player
    # supporter receive `bonus` extra score. This rewards genuine
    # cross-player cooperation (the press system carries the signal —
    # supporters read the captor's declared Intents to know where to
    # support) and creates a second viable top-tier strategy alongside
    # solo GreedyHold expansion.
    #
    # Default value: 3.0 (the empirical sweet spot from 5000-game sweeps;
    # see docs/research/2026-04-29-alliance-bonus-experiment.md). At
    # bonus=3, a Cooperator heuristic outscores GreedyHold by +1.7 in the
    # full random pool, but doesn't dominate. Lower bonus → no incentive
    # to cooperate; higher bonus → cooperation becomes the new monopoly.
    #
    # Set FOEDUS_ALLIANCE_BONUS=0 to revert to v1 scoring (no bonus).
    #
    # KNOWN EXPLOIT: a freerider that publishes Move-on-supply Intents
    # (so genuine cooperators support its attacks) but never reciprocates
    # outscores cooperators dramatically in fixed-seat tests (DC +10.7 vs
    # 3 Coop at bonus=0; +12.0 at bonus=3). The exploit is invisible in
    # random-pool sweeps because dishonest agents are diluted out of
    # cooperator-rich neighborhoods. Bundle 4's full design needs paired
    # Intent-break consequences before this stops being abusable.
    # Until then, this is a soft-ship: real but not yet hardened.
    bonus = float(os.environ.get("FOEDUS_ALLIANCE_BONUS", "3") or 0)
    if bonus:
        # Bundle 4: alliance bonus is gated on aid-spend (when
        # config.alliance_requires_aid is True). A SupportMove without an
        # AidSpend backing the mover's order contributes combat support but
        # does NOT trigger the alliance bonus. This collapses two mechanics
        # (alliance bonus + aid resource) into one: aid is the alliance
        # currency, naked SupportMove is tactical-only.
        require_aid = state.config.alliance_requires_aid

        def _is_aided(supporter_pid: PlayerId, mover_unit: UnitId,
                     mover_dest: NodeId) -> bool:
            if not require_aid:
                return True
            spends = state.round_aid_pending.get(supporter_pid, [])
            for sp in spends:
                if sp.target_unit == mover_unit:
                    return True
            return False

        # Build a quick lookup: (target_unit_id, target_dest) -> [supporter pids]
        support_index: dict[tuple[UnitId, NodeId], list[PlayerId]] = defaultdict(list)
        for sup_id, s_order in canon.items():
            if not isinstance(s_order, (SupportMove, Support)):
                continue
            sup_unit = state.units.get(sup_id)
            if sup_unit is None or sup_id in cut:
                continue
            mover = state.units.get(s_order.target)
            if mover is None or mover.owner == sup_unit.owner:
                continue
            # Determine the supported destination.
            if isinstance(s_order, SupportMove):
                supported_dest = s_order.target_dest
            else:
                # reactive Support: use target's canon move-dest if any.
                tgt_order = canon.get(s_order.target)
                if not isinstance(tgt_order, Move):
                    continue
                supported_dest = tgt_order.dest
                if s_order.require_dest is not None and s_order.require_dest != supported_dest:
                    continue
            # Bundle 4: gate on aid-spend.
            if not _is_aided(sup_unit.owner, s_order.target, supported_dest):
                continue
            support_index[(s_order.target, supported_dest)].append(
                sup_unit.owner
            )
        for u_id, order in canon.items():
            if not isinstance(order, Move):
                continue
            if outcome.get(u_id) != "success":
                continue
            if not state.map.is_supply(order.dest):
                continue
            mover = state.units.get(u_id)
            if mover is None:
                continue
            supporters = [s for s in support_index.get((u_id, order.dest), [])
                          if s != mover.owner]  # alliance = different player
            if not supporters:
                continue
            # Both mover and each cross-player supporter get the bonus.
            new_scores[mover.owner] = (
                new_scores.get(mover.owner, 0.0) + bonus
            )
            for sup_pid in supporters:
                new_scores[sup_pid] = (
                    new_scores.get(sup_pid, 0.0) + bonus
                )
            log.append(
                f"  alliance bonus +{bonus:g} to p{mover.owner} (mover) "
                f"and p{','.join(str(s) for s in supporters)} (supporter) "
                f"for capture at n{order.dest}"
            )

    # 8c. Bundle 4: combat reward.
    #
    # `combat_reward` to the attacker for each successful dislodgement;
    # `supporter_combat_reward` to each uncut cross-player supporter of the
    # dislodging attack. Same-owner supports don't get the reward (the
    # attacker's own player already got combat_reward). Both knobs default
    # to 1.0 each; set to 0.0 for v1 behavior.
    cr = state.config.combat_reward
    sr = state.config.supporter_combat_reward
    if cr != 0.0 or sr != 0.0:
        for u_id, outcome_val in outcome.items():
            if outcome_val != "dislodged":
                continue
            defender = state.units[u_id]
            attacker_id = next(
                (uid for uid, o in canon.items()
                 if isinstance(o, Move)
                 and o.dest == defender.location
                 and outcome.get(uid) == "success"),
                None,
            )
            if attacker_id is None:
                continue
            attacker = state.units[attacker_id]
            if cr != 0.0:
                new_scores[attacker.owner] = (
                    new_scores.get(attacker.owner, 0.0) + cr
                )
                log.append(
                    f"  combat reward +{cr:g} to p{attacker.owner} "
                    f"for dislodging u{u_id} at n{defender.location}"
                )
            if sr != 0.0:
                for sup_id, s_order in canon.items():
                    if not isinstance(s_order, (SupportMove, Support)):
                        continue
                    if sup_id in cut:
                        continue
                    if isinstance(s_order, SupportMove):
                        if (s_order.target != attacker_id
                                or s_order.target_dest != defender.location):
                            continue
                    else:
                        if s_order.target != attacker_id:
                            continue
                        tgt_order = canon.get(s_order.target)
                        if (not isinstance(tgt_order, Move)
                                or tgt_order.dest != defender.location):
                            continue
                        if (s_order.require_dest is not None
                                and s_order.require_dest != defender.location):
                            continue
                    sup_unit = state.units.get(sup_id)
                    if sup_unit is None or sup_unit.owner == attacker.owner:
                        continue
                    new_scores[sup_unit.owner] = (
                        new_scores.get(sup_unit.owner, 0.0) + sr
                    )
                    log.append(
                        f"  supporter reward +{sr:g} to p{sup_unit.owner} "
                        f"(via u{sup_id}) for dislodgement at n{defender.location}"
                    )

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
        support_lapses=lapses,
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
