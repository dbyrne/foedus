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
    """Phase-1 (chat) prompt. Player sees inbound chat earlier in this
    round + last round's press, may submit ONE chat draft (or skip)."""
    state = load()
    view = visible_state_for(state, player)
    print(f"=== TURN {state.turn + 1}/{state.config.max_turns}, "
          f"PHASE: NEGOTIATION (chat round), YOU ARE PLAYER {player} ===\n")

    print(f"Active opponents: {sorted(p for p in range(state.config.num_players) if p != player and p not in state.eliminated)}")
    print(f"Your supply count: {view['supply_count_you']}")
    print(f"Scores: {view['scores']}")
    print(f"Mutual-ally streak: {state.mutual_ally_streak}/"
          f"{state.config.detente_threshold} (détente fires at threshold)")
    print()

    # Public stance matrix from last round.
    if view["public_stance_matrix"]:
        print("PUBLIC STANCE MATRIX (last round):")
        for sender, stances in view["public_stance_matrix"].items():
            entries = ", ".join(
                f"p{tgt}={st}" for tgt, st in sorted(stances.items())
            )
            print(f"  p{sender}: {entries or '(none declared)'}")
        print()

    # Inbound intents from last round.
    if view["your_inbound_intents"]:
        print("INBOUND INTENTS YOU RECEIVED (last round):")
        for sender, intents in view["your_inbound_intents"].items():
            for it in intents:
                print(f"  p{sender} declared u{it.unit_id} -> "
                      f"{order_to_str(it.declared_order)} "
                      f"(visible_to={'public' if it.visible_to is None else sorted(it.visible_to)})")
        print()

    # Betrayals against you.
    if view["your_betrayals"]:
        print(f"BETRAYALS observed (cumulative, {len(view['your_betrayals'])}):")
        for b in view["your_betrayals"][-5:]:
            print(f"  turn {b.turn}: p{b.betrayer} declared "
                  f"u{b.intent.unit_id} -> {order_to_str(b.intent.declared_order)}, "
                  f"actually issued {order_to_str(b.actual_order)}")
        print()

    # Round chat so far (other players' chat earlier in this round).
    if view["round_chat_so_far"]:
        print(f"CHAT THIS ROUND SO FAR ({len(view['round_chat_so_far'])} msgs):")
        for m in view["round_chat_so_far"]:
            recip = ("public" if m.recipients is None
                     else f"to {sorted(m.recipients)}")
            print(f"  [p{m.sender} -> {recip}]: {m.body}")
        print()
    else:
        print("No chat yet this round.\n")

    print("=== INSTRUCTIONS ===")
    print(f"You may send ONE chat message this round (max "
          f"{state.config.chat_char_cap} chars), or skip.")
    print()
    print("RESPOND with a single JSON object — one of:")
    print('  {"recipients": null, "body": "..."}            // public broadcast')
    print('  {"recipients": [0, 2], "body": "..."}          // private to listed pids')
    print('  {}                                              // skip (no chat)')
    print()
    print("Strategic context: this game has Press v0. Stance + intents are")
    print("submitted in the COMMIT phase later. Use chat NOW to coordinate")
    print("alliances, share plans, threaten, deceive. Betrayal observations")
    print("are recorded if you declare an intent and don't follow through.")


def cmd_apply_chat(player: int, path: str) -> None:
    """Read chat draft JSON from file. Empty {} -> skip."""
    raw = json.loads(Path(path).read_text())
    if not raw:
        print(f"player {player}: chat skipped (empty draft)")
        return
    if "body" not in raw:
        print(f"WARN: chat draft for p{player} missing 'body'; skipping")
        return
    recipients_raw = raw.get("recipients")
    if recipients_raw is None:
        recipients = None
    else:
        try:
            recipients = frozenset(int(r) for r in recipients_raw)
        except (TypeError, ValueError):
            print(f"WARN: bad recipients for p{player}: {recipients_raw}; skipping")
            return
    draft = ChatDraft(recipients=recipients, body=str(raw["body"]))
    state = load()
    new_state = record_chat_message(state, player, draft)
    if new_state is state or len(new_state.round_chat) == len(state.round_chat):
        # Engine silently dropped (e.g. exceeded char cap, eliminated player).
        # Surface this to the orchestrator so the caller sees something happened.
        print(f"WARN: engine dropped chat from p{player} "
              f"(len={len(draft.body)}, cap={state.config.chat_char_cap}); "
              f"check eliminations, char cap, or phase")
        return
    save(new_state)
    recip_s = ("public" if recipients is None else f"to {sorted(recipients)}")
    print(f"player {player} chat ({recip_s}): {draft.body[:80]}"
          f"{'...' if len(draft.body) > 80 else ''}")


# Commit phase commands (Task 5)
def cmd_prompt_commit(player: int) -> None:
    """Phase-2 (commit) prompt. Player sees ALL same-turn chat visible
    to them, plus map + legal orders, then submits press + orders."""
    state = load()
    view = visible_state_for(state, player)

    print(f"=== TURN {state.turn + 1}/{state.config.max_turns}, "
          f"PHASE: COMMIT (orders + press), YOU ARE PLAYER {player} ===\n")

    # All chat visible to you this round.
    if view["round_chat_so_far"]:
        print(f"CHAT THIS ROUND ({len(view['round_chat_so_far'])} msgs):")
        for m in view["round_chat_so_far"]:
            recip = ("public" if m.recipients is None
                     else f"to {sorted(m.recipients)}")
            print(f"  [p{m.sender} -> {recip}]: {m.body}")
        print()
    else:
        print("(no chat this round)\n")

    # Map.
    print("MAP (^ = mountain, ~ = water, $ = supply, H = home, "
          "[node-type-owner], u<id>p<player> = unit):")
    print(render_map(state))
    print()
    print(f"Your visible nodes: {view['visible_nodes']}")
    print(f"Your supply count: {view['supply_count_you']}")
    print(f"Scores: {view['scores']}")
    print(f"Mutual-ally streak: {state.mutual_ally_streak}/"
          f"{state.config.detente_threshold}")
    print()

    # Visible units.
    print("VISIBLE UNITS:")
    for u in view["visible_units"]:
        marker = "(YOURS)" if u["owner"] == player else f"(player {u['owner']})"
        print(f"  unit u{u['id']} at node {u['location']} {marker}")
    print()

    # Your units + legal orders.
    print("YOUR UNITS — choose ONE order per unit:")
    for u in state.units.values():
        if u.owner != player:
            continue
        legal = legal_orders_for_unit(state, u.id)
        print(f"  u{u.id} at node {u.location} (adj: "
              f"{sorted(state.map.neighbors(u.location))})")
        for i, o in enumerate(legal):
            print(f"    [{i}] {order_to_str(o)}")
    print()

    print("=== RESPONSE FORMAT ===")
    print("Reply with ONE JSON object combining press tokens and orders:")
    print('{')
    print('  "press": {')
    print('    "stance": {"<other_pid>": "ally|neutral|hostile", ...},')
    print('    "intents": [')
    print('      {"unit_id": <int>,')
    print('       "declared_order": <order>,')
    print('       "visible_to": null | [<pid>, ...]}')
    print('    ]')
    print('  },')
    print('  "orders": {"<unit_id>": <order>, ...}')
    print('}')
    print()
    print("Order objects:")
    print('  {"type": "Hold"}')
    print('  {"type": "Move", "dest": <node_id>}')
    print('  {"type": "SupportHold", "target": <unit_id>}')
    print('  {"type": "SupportMove", "target": <unit_id>, "target_dest": <node_id>}')
    print()
    print("Notes:")
    print("- press.stance / press.intents are optional; default empty.")
    print("- visible_to=null means public broadcast; list = private group.")
    print("- intents about units you don't own are silently dropped.")
    print("- if your declared_order doesn't match your actual order at finalize,")
    print("  recipients see a BetrayalObservation. Plan accordingly.")
    print("- orders is required; default-Hold any owned unit you omit.")


def _parse_stance(d: dict) -> dict[int, Stance]:
    out: dict[int, Stance] = {}
    for k, v in d.items():
        try:
            pid = int(k)
            stance = Stance(v if isinstance(v, str) else v.value)
            out[pid] = stance
        except (TypeError, ValueError, AttributeError) as e:
            print(f"WARN: bad stance entry {k}={v!r}: {e}; skipping")
    return out


def _parse_intent(d: dict) -> Intent | None:
    try:
        unit_id = int(d["unit_id"])
        declared = parse_order(d["declared_order"])
        vt_raw = d.get("visible_to")
        if vt_raw is None:
            vt: frozenset[int] | None = None
        else:
            vt = frozenset(int(x) for x in vt_raw)
        return Intent(unit_id=unit_id, declared_order=declared,
                      visible_to=vt)
    except (KeyError, TypeError, ValueError) as e:
        print(f"WARN: bad intent {d!r}: {e}; skipping")
        return None


def cmd_apply_commit(player: int, path: str) -> None:
    """Parse {press, orders} JSON, submit press, store orders for advance."""
    state = load()
    raw = json.loads(Path(path).read_text())

    # Press (optional).
    press_raw = raw.get("press") or {}
    stance = _parse_stance(press_raw.get("stance") or {})
    intents = []
    for it_raw in press_raw.get("intents") or []:
        parsed = _parse_intent(it_raw)
        if parsed is not None:
            intents.append(parsed)
    press = Press(stance=stance, intents=intents)
    state = submit_press_tokens(state, player, press)
    save(state)

    # Orders (required).
    orders_raw = raw.get("orders") or {}
    parsed_orders: dict[UnitId, Order] = {}
    for uid_s, od in orders_raw.items():
        try:
            uid = int(uid_s)
        except ValueError:
            print(f"WARN: non-int unit_id key {uid_s!r}; skipping")
            continue
        unit = state.units.get(uid)
        if unit is None:
            print(f"WARN: unit u{uid} doesn't exist; skipping")
            continue
        if unit.owner != player:
            print(f"WARN: unit u{uid} not owned by p{player}; skipping")
            continue
        try:
            parsed_orders[uid] = parse_order(od)
        except (KeyError, ValueError) as e:
            print(f"WARN: bad order for u{uid}: {e}; defaulting to Hold")
            parsed_orders[uid] = Hold()
    # Default-Hold any owned unit the LLM omitted.
    for u in state.units.values():
        if u.owner == player:
            parsed_orders.setdefault(u.id, Hold())
    with ORDERS_PICKLE(player).open("wb") as f:
        pickle.dump(parsed_orders, f)

    # Summary line.
    stance_s = ", ".join(f"p{p}={s.value}" for p, s in stance.items()) or "(empty)"
    intents_s = f"{len(intents)} intent(s)" if intents else "no intents"
    orders_s = ", ".join(
        f"u{uid}={order_to_str(o)}"
        for uid, o in sorted(parsed_orders.items())
    )
    print(f"player {player} press: stance={{{stance_s}}}, {intents_s}")
    print(f"player {player} orders: {orders_s}")


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
