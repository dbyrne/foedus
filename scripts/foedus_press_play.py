"""Press-aware orchestrator for a Haiku-vs-HeuristicAgent foedus game.

Drives a two-phase round (chat -> commit) per turn via subagent calls.
State persists in a pickle so this can be invoked iteratively from chat.

Workflow per turn:
  for each LLM seat P in LLM_SEATS:
    prompt_chat P     -> agent prompt for chat phase
    apply_chat P FILE -> driver records the chat draft (or skip)
  for each LLM seat P in LLM_SEATS:
    prompt_commit P     -> agent prompt for commit phase
    apply_commit P FILE -> driver submits press + writes orders
  advance               -> heuristic press + signal_done + finalize_round

Spec: docs/superpowers/specs/2026-04-28-press-driver-design.md
Plan: docs/superpowers/plans/2026-04-28-press-driver-bundle-3.md
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

from foedus.agents.heuristic import HeuristicAgent
from foedus.core import (
    Archetype,
    ChatDraft,
    GameConfig,
    Hold,
    Intent,
    Move,
    Order,
    Press,
    Stance,
    SupportHold,
    SupportMove,
    UnitId,
)
from foedus.fog import visible_state_for
from foedus.legal import legal_orders_for_unit
from foedus.mapgen import generate_map
from foedus.press import (
    finalize_round,
    record_chat_message,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import initial_state

STATE_FILE = Path("/tmp/foedus_press_state.pickle")
CHAT_FILE = lambda p: Path(f"/tmp/foedus_press_chat_p{p}.json")
COMMIT_FILE = lambda p: Path(f"/tmp/foedus_press_commit_p{p}.json")
ORDERS_PICKLE = lambda p: Path(f"/tmp/foedus_press_orders_p{p}.pickle")

LLM_SEATS = {0, 1}        # players 0 and 1 are Haiku
HEURISTIC_SEATS = {2, 3}  # players 2 and 3 are HeuristicAgent


def save(state) -> None:
    with STATE_FILE.open("wb") as f:
        pickle.dump(state, f)


def load():
    with STATE_FILE.open("rb") as f:
        return pickle.load(f)


def cmd_init() -> None:
    cfg = GameConfig(
        num_players=4,
        max_turns=7,
        seed=42,
        archetype=Archetype.CONTINENTAL_SWEEP,
        stagnation_cost=1.0,
    )
    m = generate_map(cfg.num_players, seed=cfg.seed,
                     archetype=cfg.archetype, map_radius=cfg.map_radius)
    state = initial_state(cfg, m)
    save(state)
    # Clean up any per-player files from a previous run.
    for p in range(cfg.num_players):
        for fn in (CHAT_FILE(p), COMMIT_FILE(p), ORDERS_PICKLE(p)):
            if fn.exists():
                fn.unlink()
    print(f"initialized: {len(m.coords)} hexes, "
          f"{cfg.num_players} players (LLM: {sorted(LLM_SEATS)}, "
          f"Heuristic: {sorted(HEURISTIC_SEATS)}), "
          f"max_turns={cfg.max_turns}, "
          f"detente_threshold={cfg.detente_threshold}")


def render_map(state) -> str:
    """ASCII hex map with owner + node-type marks."""
    coords = state.map.coords
    qs = [c[0] for c in coords.values()]
    rs = [c[1] for c in coords.values()]
    qmin, qmax = min(qs), max(qs)
    rmin, rmax = min(rs), max(rs)
    by_qr = {coords[n]: n for n in coords}
    occupant = {u.location: u for u in state.units.values()}
    lines = []
    for r in range(rmin, rmax + 1):
        indent = " " * (3 * (r - rmin))
        row = indent
        for q in range(qmin, qmax + 1):
            n = by_qr.get((q, r))
            if n is None:
                row += "      "
                continue
            t = state.map.node_types[n]
            from foedus.core import NodeType
            if t == NodeType.HOME:
                mark = "H"
            elif t == NodeType.SUPPLY:
                mark = "$"
            elif t == NodeType.MOUNTAIN:
                mark = "^"
            elif t == NodeType.WATER:
                mark = "~"
            else:
                mark = "."
            owner = state.ownership.get(n)
            owner_s = str(owner) if owner is not None else "-"
            unit = occupant.get(n)
            unit_s = f"u{unit.id}p{unit.owner}" if unit else "    "
            row += f"[{n:>2}{mark}{owner_s}]"
        lines.append(row)
    return "\n".join(lines)


def order_to_str(o: Order) -> str:
    if isinstance(o, Hold):
        return "Hold"
    if isinstance(o, Move):
        return f"Move(dest={o.dest})"
    if isinstance(o, SupportHold):
        return f"SupportHold(target=u{o.target})"
    if isinstance(o, SupportMove):
        return f"SupportMove(target=u{o.target}, target_dest={o.target_dest})"
    return str(o)


def parse_order(d: dict) -> Order:
    t = d["type"]
    if t == "Hold":
        return Hold()
    if t == "Move":
        return Move(dest=int(d["dest"]))
    if t == "SupportHold":
        return SupportHold(target=int(d["target"]))
    if t == "SupportMove":
        return SupportMove(target=int(d["target"]),
                           target_dest=int(d["target_dest"]))
    raise ValueError(f"unknown order type: {t}")


def cmd_status() -> None:
    state = load()
    print(f"turn {state.turn}/{state.config.max_turns}")
    print(f"phase: {state.phase.value}")
    print(f"terminal: {state.is_terminal()}")
    print(f"scores: {state.scores}")
    print(f"eliminated: {sorted(state.eliminated)}")
    print(f"winners: {state.winners()}")
    print(f"mutual_ally_streak: {state.mutual_ally_streak}/"
          f"{state.config.detente_threshold}")
    print(f"round_done: {sorted(state.round_done)}")
    print(f"round_chat msgs: {len(state.round_chat)}")
    print(f"round_press_pending: {sorted(state.round_press_pending)}")


def cmd_log() -> None:
    state = load()
    for line in state.log:
        print(line)


def cmd_feedback(player: int) -> None:
    """Print prompt for end-of-game feedback from one of the LLM players."""
    state = load()
    print(f"=== POST-GAME FEEDBACK PROMPT for PLAYER {player} (Haiku) ===\n")
    print(f"You played as Player {player} in a {state.config.num_players}-player "
          f"foedus game. The game ran for {state.turn} turns.\n")
    print(f"Final scores (all players): {dict(state.final_scores())}")
    print(f"Eliminated: {sorted(state.eliminated)}")
    print(f"Winners: {state.winners()}")
    print(f"Détente reached: {state.detente_reached}")
    print(f"Your final score: {state.scores.get(player, 0)}")
    print()
    print("This game exposed Press v0 features: stance declarations,")
    print("intents, chat. We want your candid feedback on whether press")
    print("actually let you do something interesting, or felt like noise.")
    print()
    print("Full resolution log:")
    for line in state.log:
        print(f"  {line}")
    print()
    print("Questions:")
    print("- Did you use stance / intents / chat in any meaningful way?")
    print("- Did press let you coordinate with other players?")
    print("- Was there any betrayal observation that changed your play?")
    print("- Did the heuristics' ALLY declarations affect your reasoning?")
    print("- Anything you wanted to do but the press surface didn't allow?")
    print("- Compared to a press-less game, did this feel deeper or just noisier?")


# Chat phase commands (Task 4)
def cmd_prompt_chat(player: int) -> None:
    raise NotImplementedError("Task 4 will fill this in.")


def cmd_apply_chat(player: int, path: str) -> None:
    raise NotImplementedError("Task 4 will fill this in.")


# Commit phase commands (Task 5)
def cmd_prompt_commit(player: int) -> None:
    raise NotImplementedError("Task 5 will fill this in.")


def cmd_apply_commit(player: int, path: str) -> None:
    raise NotImplementedError("Task 5 will fill this in.")


# Advance (Task 6)
def cmd_advance() -> None:
    raise NotImplementedError("Task 6 will fill this in.")


COMMANDS = {
    "init": cmd_init,
    "prompt_chat": lambda: cmd_prompt_chat(int(sys.argv[2])),
    "apply_chat": lambda: cmd_apply_chat(int(sys.argv[2]), sys.argv[3]),
    "prompt_commit": lambda: cmd_prompt_commit(int(sys.argv[2])),
    "apply_commit": lambda: cmd_apply_commit(int(sys.argv[2]), sys.argv[3]),
    "advance": cmd_advance,
    "status": cmd_status,
    "feedback": lambda: cmd_feedback(int(sys.argv[2])),
    "log": cmd_log,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: {sys.argv[0]} {{init|prompt_chat P|apply_chat P FILE|"
              f"prompt_commit P|apply_commit P FILE|advance|status|"
              f"feedback P|log}}")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
