"""Press-aware prompt rendering for the game server.

Functions here build the plain-text prompts shown to LLM-seat players in
chat phase and commit phase. String-formatting logic that's identical
between this server-side renderer and the offline orchestrator
(scripts/foedus_press_play.py) lives in foedus.render_common so the two
never drift.

Spec: docs/superpowers/specs/2026-04-29-autonomous-press-harness-design.md
Phase 0a legibility fixes: docs/superpowers/specs/2026-07-01-foedus-phase0-arena-fixes-design.md
"""

from __future__ import annotations

from io import StringIO

from foedus.core import GameState, PlayerId
from foedus.fog import visible_state_for
from foedus.legal import legal_orders_for_unit
from foedus.render_common import (
    CAPTURE_RULE_TEXT,
    order_to_str,
    render_active_pacts,
    render_adjacency_table,
    render_betrayal_ledger,
    render_income_ledger,
    render_map,
    render_pact_breach_ledger,
    render_turn_calendar,
)


def render_chat_prompt(state: GameState, player: PlayerId) -> str:
    """Build the chat-phase prompt for `player`. Returns a plain-text
    string suitable for printing to stdout or returning over HTTP."""
    out = StringIO()
    view = visible_state_for(state, player)
    out.write(
        f"=== TURN {state.turn + 1}/{state.config.max_turns}, "
        f"PHASE: NEGOTIATION (chat round), YOU ARE PLAYER {player} ===\n\n"
    )

    active = sorted(
        p for p in range(state.config.num_players)
        if p != player and p not in state.eliminated
    )
    out.write(f"Active opponents: {active}\n")
    out.write(f"Your supply count: {view['supply_count_you']}\n")
    out.write(f"Scores: {view['scores']}\n")
    out.write(
        f"Mutual-ally streak: {state.mutual_ally_streak}/"
        f"{state.config.detente_threshold} (détente fires at threshold)\n"
    )
    out.write(render_turn_calendar(state) + "\n\n")
    out.write(CAPTURE_RULE_TEXT + "\n\n")
    out.write(render_income_ledger(state, player) + "\n\n")

    if view["public_stance_matrix"]:
        out.write("PUBLIC STANCE MATRIX (last round):\n")
        for sender, stances in view["public_stance_matrix"].items():
            entries = ", ".join(
                f"p{tgt}={st}" for tgt, st in sorted(stances.items())
            )
            out.write(f"  p{sender}: {entries or '(none declared)'}\n")
        out.write("\n")

    if view["your_inbound_intents"]:
        out.write("INBOUND INTENTS YOU RECEIVED (last round):\n")
        for sender, intents in view["your_inbound_intents"].items():
            for it in intents:
                vt = ('public' if it.visible_to is None
                      else sorted(it.visible_to))
                out.write(
                    f"  p{sender} declared u{it.unit_id} -> "
                    f"{order_to_str(it.declared_order, state)} "
                    f"(visible_to={vt})\n"
                )
        out.write("\n")

    out.write(render_betrayal_ledger(state, player) + "\n\n")
    out.write(render_active_pacts(state, player) + "\n\n")
    out.write(render_pact_breach_ledger(state, player) + "\n\n")

    if view["round_chat_so_far"]:
        out.write(
            f"CHAT THIS ROUND SO FAR ({len(view['round_chat_so_far'])} msgs):\n"
        )
        for m in view["round_chat_so_far"]:
            recip = ("public" if m.recipients is None
                     else f"to {sorted(m.recipients)}")
            out.write(f"  [p{m.sender} -> {recip}]: {m.body}\n")
        out.write("\n")
    else:
        out.write("No chat yet this round.\n\n")

    out.write("=== INSTRUCTIONS ===\n")
    out.write(
        f"You may send ONE chat message this round (max "
        f"{state.config.chat_char_cap} chars), or skip.\n\n"
    )
    out.write("RESPOND with a single JSON object — one of:\n")
    out.write('  {"recipients": null, "body": "..."}            // public broadcast\n')
    out.write('  {"recipients": [0, 2], "body": "..."}          // private\n')
    out.write('  {}                                              // skip\n\n')
    out.write(
        "Strategic context: this game has Press v0. Stance + intents are\n"
        "submitted in the COMMIT phase later. Use chat NOW to coordinate\n"
        "alliances, share plans, threaten, deceive. Betrayal observations\n"
        "are recorded if you declare an intent and don't follow through.\n"
    )
    return out.getvalue()


def render_commit_prompt(state: GameState, player: PlayerId) -> str:
    """Build the commit-phase prompt for `player`."""
    out = StringIO()
    view = visible_state_for(state, player)
    out.write(
        f"=== TURN {state.turn + 1}/{state.config.max_turns}, "
        f"PHASE: COMMIT (orders + press), YOU ARE PLAYER {player} ===\n\n"
    )

    if view["round_chat_so_far"]:
        out.write(
            f"CHAT THIS ROUND ({len(view['round_chat_so_far'])} msgs):\n"
        )
        for m in view["round_chat_so_far"]:
            recip = ("public" if m.recipients is None
                     else f"to {sorted(m.recipients)}")
            out.write(f"  [p{m.sender} -> {recip}]: {m.body}\n")
        out.write("\n")
    else:
        out.write("(no chat this round)\n\n")

    out.write(CAPTURE_RULE_TEXT + "\n\n")

    out.write(
        "MAP (^ = mountain, ~ = water, $<value> = supply, H = home, "
        "[node-mark:owner]):\n"
    )
    out.write(render_map(state) + "\n\n")
    out.write(f"Your visible nodes: {view['visible_nodes']}\n")
    out.write(f"Your supply count: {view['supply_count_you']}\n")
    out.write(f"Scores: {view['scores']}\n")
    out.write(
        f"Mutual-ally streak: {state.mutual_ally_streak}/"
        f"{state.config.detente_threshold}\n"
    )
    out.write(render_turn_calendar(state) + "\n\n")
    out.write(render_income_ledger(state, player) + "\n\n")
    out.write(render_adjacency_table(state, view["visible_nodes"]) + "\n\n")
    out.write(render_betrayal_ledger(state, player) + "\n\n")
    out.write(render_active_pacts(state, player) + "\n\n")
    out.write(render_pact_breach_ledger(state, player) + "\n\n")

    out.write("VISIBLE UNITS:\n")
    for u in view["visible_units"]:
        marker = "(YOURS)" if u["owner"] == player else f"(player {u['owner']})"
        out.write(f"  unit u{u['id']} at node {u['location']} {marker}\n")
    out.write("\n")

    out.write("YOUR UNITS — choose ONE order per unit:\n")
    for u in state.units.values():
        if u.owner != player:
            continue
        legal = legal_orders_for_unit(state, u.id)
        out.write(
            f"  u{u.id} at node {u.location} (adj: "
            f"{sorted(state.map.neighbors(u.location))})\n"
        )
        for i, o in enumerate(legal):
            out.write(f"    [{i}] {order_to_str(o, state)}\n")
    out.write("\n")

    out.write("=== RESPONSE FORMAT ===\n")
    out.write(
        "Reply with ONE JSON object combining press tokens and orders:\n"
    )
    out.write('{\n')
    out.write('  "press": {\n')
    out.write('    "stance": {"<other_pid>": "ally|neutral|hostile", ...},\n')
    out.write('    "intents": [\n')
    out.write('      {"unit_id": <int>,\n')
    out.write('       "declared_order": <order>,\n')
    out.write('       "visible_to": null | [<pid>, ...]}\n')
    out.write('    ]\n')
    out.write('  },\n')
    out.write('  "orders": {"<unit_id>": <order>, ...}\n')
    out.write('}\n\n')
    out.write('Order objects:\n')
    out.write('  {"type": "Hold"}\n')
    out.write('  {"type": "Move", "dest": <node_id>}\n')
    out.write('  {"type": "Support", "target": <unit_id>}\n')
    out.write('  {"type": "Support", "target": <unit_id>, '
              '"require_dest": <node_id>}\n\n')
    out.write("Notes:\n")
    out.write(
        "- press.stance / press.intents are optional; default empty.\n"
        "- visible_to=null means public broadcast; list = private group.\n"
        "- intents about units you don't own are silently dropped.\n"
        "- if your declared_order doesn't match your actual order at finalize,\n"
        "  recipients see a BetrayalObservation. Plan accordingly.\n"
        "- orders is required; default-Hold any owned unit you omit.\n"
    )
    return out.getvalue()
