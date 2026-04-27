"""Tiny interactive CLI for stepping through games by hand.

Lets you see the map, see each player's view (with fog), enter orders, and
resolve turns. Useful for debugging the engine and getting a feel for the game
before any agents exist.
"""

from __future__ import annotations

import argparse
import sys

from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Move,
    NodeType,
    Order,
    SupportHold,
    SupportMove,
    UnitId,
)
from foedus.fog import visible_state_for
from foedus.mapgen import generate_map
from foedus.resolve import initial_state, resolve_turn


def print_map(state: GameState) -> None:
    """Render the hex map ASCII-style with node id and owner."""
    coords_by_node = state.map.coords
    occupant = {u.location: u for u in state.units.values()}
    qs = [c[0] for c in coords_by_node.values()]
    rs = [c[1] for c in coords_by_node.values()]
    qmin, qmax = min(qs), max(qs)
    rmin, rmax = min(rs), max(rs)
    by_qr = {coords_by_node[n]: n for n in coords_by_node}

    print()
    for r in range(rmin, rmax + 1):
        # offset based on r for hex visualization
        indent = " " * (2 * (r - rmin))
        line = indent
        for q in range(qmin, qmax + 1):
            n = by_qr.get((q, r))
            if n is None:
                line += "      "
                continue
            t = state.map.node_types[n]
            mark = "*" if t == NodeType.SUPPLY else ("H" if t == NodeType.HOME else ".")
            owner = state.ownership.get(n)
            owner_s = str(owner) if owner is not None else "-"
            unit = occupant.get(n)
            unit_s = f"u{unit.id}p{unit.owner}" if unit else "    "
            line += f"[{n:>2}{mark}{owner_s}]"
        print(line)
    print()


def print_state(state: GameState) -> None:
    print(f"Turn {state.turn}/{state.config.max_turns}  "
          f"scores={dict(state.scores)}  eliminated={sorted(state.eliminated)}")
    print_map(state)
    print("Units:")
    for u in sorted(state.units.values(), key=lambda u: u.id):
        loc = u.location
        coord = state.map.coords[loc]
        print(f"  u{u.id} player {u.owner} at node {loc} {coord}")
    print()


def print_player_view(state: GameState, player: int) -> None:
    view = visible_state_for(state, player)
    print(f"=== Player {player} view (fog of war) ===")
    print(f"  supply_count: {view['supply_count_you']}, score: {view['scores'].get(player)}")
    print(f"  visible_nodes: {view['visible_nodes']}")
    print("  visible_units:")
    for u in view["visible_units"]:
        marker = "(you)" if u["owner"] == player else "(enemy)"
        print(f"    u{u['id']} player {u['owner']} at node {u['location']} {marker}")
    print()


def parse_order(unit_id: UnitId, raw: str) -> Order:
    """Parse a single-line order. Examples:
        h               -> Hold
        m 5             -> Move to node 5
        sh 3            -> Support hold of unit 3
        sm 3 5          -> Support unit 3 moving to node 5
    """
    parts = raw.strip().split()
    if not parts:
        return Hold()
    cmd = parts[0].lower()
    if cmd == "h":
        return Hold()
    if cmd == "m" and len(parts) >= 2:
        return Move(dest=int(parts[1]))
    if cmd == "sh" and len(parts) >= 2:
        return SupportHold(target=int(parts[1]))
    if cmd == "sm" and len(parts) >= 3:
        return SupportMove(target=int(parts[1]), target_dest=int(parts[2]))
    print(f"  (could not parse '{raw}', defaulting to Hold)")
    return Hold()


def collect_orders_interactive(state: GameState) -> dict[int, dict[UnitId, Order]]:
    """Prompt each active player for their orders this turn."""
    orders: dict[int, dict[UnitId, Order]] = {}
    for player in range(state.config.num_players):
        if player in state.eliminated:
            continue
        print_player_view(state, player)
        units = [u for u in state.units.values() if u.owner == player]
        if not units:
            print(f"  player {player} has no units this turn")
            orders[player] = {}
            continue
        pmap: dict[UnitId, Order] = {}
        for u in units:
            print(f"  Order for u{u.id} at node {u.location}? (h | m N | sh U | sm U N)")
            print(f"    adjacent nodes: {sorted(state.map.neighbors(u.location))}")
            raw = input("  > ")
            pmap[u.id] = parse_order(u.id, raw)
        orders[player] = pmap
    return orders


def main() -> int:
    parser = argparse.ArgumentParser(description="foedus CLI")
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--demo", action="store_true",
                        help="Generate a map and print initial state, then exit")
    args = parser.parse_args()

    config = GameConfig(num_players=args.players, max_turns=args.turns, seed=args.seed)
    m = generate_map(config.num_players, seed=args.seed)
    state = initial_state(config, m)

    print(f"Generated map with {len(m.nodes)} nodes; {sum(1 for t in m.node_types.values() if t in (NodeType.SUPPLY, NodeType.HOME))} supply centers.")
    print_state(state)

    if args.demo:
        return 0

    while not state.is_terminal():
        try:
            orders = collect_orders_interactive(state)
        except (EOFError, KeyboardInterrupt):
            print("\n(interrupted)")
            break
        state = resolve_turn(state, orders)
        print()
        print("--- resolution log ---")
        for line in state.log[-30:]:
            print(line)
        print()
        print_state(state)

    print("=== final ===")
    print(f"Scores: {dict(state.scores)}")
    print(f"Eliminated: {sorted(state.eliminated)}")
    winner = max(state.scores.items(), key=lambda kv: kv[1])
    print(f"Winner: player {winner[0]} with score {winner[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
