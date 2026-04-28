"""foedus command-line entry point.

Two subcommand groups so far:
- `foedus play`         — interactive REPL for stepping through a game by hand
- `foedus agent serve`  — run an HTTP server that wraps an Agent class
"""

from __future__ import annotations

import importlib
import sys

import click

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
from foedus.press import advance_turn
from foedus.resolve import initial_state


# --- interactive `foedus play` ----------------------------------------------


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


# --- agent class import helper ---------------------------------------------


def _load_agent_class(import_path: str):
    if "." not in import_path:
        raise click.ClickException(
            f"--agent must be a fully qualified path (module.ClassName), got {import_path!r}"
        )
    module_path, class_name = import_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise click.ClickException(f"could not import module {module_path!r}: {e}")
    try:
        return getattr(module, class_name)
    except AttributeError:
        raise click.ClickException(
            f"module {module_path!r} has no attribute {class_name!r}"
        )


# --- click root --------------------------------------------------------------


@click.group()
@click.version_option()
def main() -> None:
    """foedus — lightweight Diplomacy-inspired multi-agent strategy game."""


@main.command()
@click.option("--players", default=4, show_default=True, type=int)
@click.option("--seed", default=None, type=int)
@click.option("--turns", default=10, show_default=True, type=int)
@click.option("--demo", is_flag=True,
              help="Generate a map and print initial state, then exit.")
def play(players: int, seed: int | None, turns: int, demo: bool) -> None:
    """Interactive REPL for stepping through a game by hand."""
    config = GameConfig(num_players=players, max_turns=turns, seed=seed)
    m = generate_map(config.num_players, seed=seed)
    state = initial_state(config, m)

    print(f"Generated map with {len(m.nodes)} nodes; "
          f"{sum(1 for t in m.node_types.values() if t in (NodeType.SUPPLY, NodeType.HOME))} supply centers.")
    print_state(state)

    if demo:
        return

    while not state.is_terminal():
        try:
            orders = collect_orders_interactive(state)
        except (EOFError, KeyboardInterrupt):
            print("\n(interrupted)")
            break
        state = advance_turn(state, orders)
        print()
        print("--- resolution log ---")
        for line in state.log[-30:]:
            print(line)
        print()
        print_state(state)

    print("=== final ===")
    print(f"Scores: {dict(state.scores)}")
    print(f"Eliminated: {sorted(state.eliminated)}")
    if state.scores:
        winner = max(state.scores.items(), key=lambda kv: kv[1])
        print(f"Highest score: player {winner[0]} with {winner[1]}")


@main.group()
def agent() -> None:
    """Agent serving + packaging commands."""


@agent.command(name="serve")
@click.option("--agent", "agent_path", required=True,
              help="Fully qualified Agent class path, e.g. foedus.RandomAgent.")
@click.option("--port", default=8080, show_default=True, type=int)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--name", default=None,
              help="Agent name reported via /info (default: class name).")
@click.option("--version", default="0.1.0", show_default=True)
def agent_serve(agent_path: str, port: int, host: str,
                name: str | None, version: str) -> None:
    """Run an HTTP server wrapping the named Agent class."""
    cls = _load_agent_class(agent_path)
    instance = cls()
    try:
        from foedus.remote.server import serve as _serve
    except ImportError as e:
        raise click.ClickException(
            "foedus[remote] extra not installed. Run: pip install foedus[remote]"
        ) from e
    click.echo(f"serving {agent_path} on http://{host}:{port}")
    _serve(instance, host=host, port=port,
           name=name or cls.__name__, version=version)


@agent.command(name="build")
@click.argument("tag")
@click.option("--agent", "agent_path", required=True,
              help="Fully qualified Agent class path, e.g. foedus.RandomAgent.")
@click.option("--context", "context_dir", default=".",
              type=click.Path(exists=True, file_okay=False),
              show_default=True,
              help="Build context (must contain pyproject.toml).")
@click.option("--dockerfile", default=None,
              type=click.Path(exists=True, dir_okay=False),
              help="Custom Dockerfile (default: bundled Dockerfile.agent).")
@click.option("--no-cache", is_flag=True, help="Skip layer cache.")
def agent_build(tag: str, agent_path: str, context_dir: str,
                dockerfile: str | None, no_cache: bool) -> None:
    """Build a Docker image that serves the named Agent over HTTP."""
    from pathlib import Path as _P
    from foedus.agent_build import DockerError, build_agent_image
    try:
        build_agent_image(
            tag, agent_path,
            context=_P(context_dir),
            dockerfile=_P(dockerfile) if dockerfile else None,
            no_cache=no_cache,
        )
    except DockerError as e:
        raise click.ClickException(str(e))
    click.echo(f"built {tag}")
    click.echo(f"  run with: foedus agent run {tag} --port 8080")


@agent.command(name="run")
@click.argument("tag")
@click.option("--port", default=8080, show_default=True, type=int,
              help="Host port to map to the container's :8080.")
@click.option("--name", default=None, help="Container name.")
@click.option("--keep", is_flag=True,
              help="Don't auto-remove the container on exit (default: auto-remove).")
def agent_run(tag: str, port: int, name: str | None, keep: bool) -> None:
    """Start an agent container. Returns the container ID."""
    from foedus.agent_build import DockerError, run_agent_container
    try:
        cid = run_agent_container(
            tag, port=port, name=name, auto_remove=not keep,
        )
    except DockerError as e:
        raise click.ClickException(str(e))
    click.echo(f"started container {cid[:12]}")
    click.echo(f"  agent listening on http://localhost:{port}")
    click.echo(f"  curl http://localhost:{port}/info")


@agent.command(name="stop")
@click.argument("name_or_id")
@click.option("--timeout", default=10, show_default=True,
              help="Seconds to wait for clean shutdown before SIGKILL.")
def agent_stop(name_or_id: str, timeout: int) -> None:
    """Stop a running agent container."""
    from foedus.agent_build import DockerError, stop_agent_container
    try:
        stop_agent_container(name_or_id, timeout=timeout)
    except DockerError as e:
        raise click.ClickException(str(e))
    click.echo(f"stopped {name_or_id}")


@main.group(name="play-server")
def play_server() -> None:
    """HTTP game server for UI clients (Godot, web, terminal)."""


@play_server.command(name="start")
@click.option("--port", default=8090, show_default=True, type=int)
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Use 0.0.0.0 for LAN play (no auth — local-trust only).")
def play_server_start(port: int, host: str) -> None:
    """Start the game server (foreground, blocking)."""
    try:
        from foedus.game_server import serve
    except ImportError as e:
        raise click.ClickException(
            "foedus[remote] extra not installed. Run: pip install foedus[remote]"
        ) from e
    click.echo(f"foedus game server: http://{host}:{port}")
    serve(host=host, port=port)


if __name__ == "__main__":
    sys.exit(main(standalone_mode=True))
