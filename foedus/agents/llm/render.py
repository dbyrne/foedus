"""Prompt rendering for LLMDiplomat.

Composes foedus.render_common's existing building blocks (map, income
ledger, adjacency, betrayal/pact ledgers, public reputation, active
pacts, the response-format block) into the two LLM-call prompts
(negotiate, orders) instead of re-implementing any of that rendering --
scripts/foedus_press_play.py already renders the same content the same
way for a human LLM driver, and this mirrors it.
"""

from __future__ import annotations

from foedus.core import GameState, Intent, PlayerId
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
    render_reputation,
    render_turn_calendar,
)

NEGOTIATION_SYSTEM_PROMPT = (
    "You are an AI player in Foedus, a Diplomacy-inspired multi-agent "
    "strategy game. This is the negotiation phase: declare your public "
    "stance toward other players, optionally pre-declare intended orders "
    "(intents) as commitments others can see, and optionally propose or "
    "accept binding joint pacts. Breaking a declared intent or an accepted "
    "pact is recorded publicly and damages your reputation. Respond with "
    "ONLY a single JSON object -- no prose, no markdown fences."
)

ORDERS_SYSTEM_PROMPT = (
    "You are an AI player in Foedus, a Diplomacy-inspired multi-agent "
    "strategy game. This is the orders phase: choose one order per unit "
    "you own. Respond with ONLY a single JSON object -- no prose, no "
    "markdown fences."
)


def _render_visible_units(view: dict, player: PlayerId) -> list[str]:
    lines = ["VISIBLE UNITS:"]
    for u in view["visible_units"]:
        marker = "(YOURS)" if u["owner"] == player else f"(player {u['owner']})"
        lines.append(f"  u{u['id']} at node {u['location']} {marker}")
    return lines


def render_negotiation_prompt(
    state: GameState, view: dict, player: PlayerId
) -> tuple[str, str]:
    lines: list[str] = []
    lines.append(f"You are Player {player}. " + render_turn_calendar(state))
    lines.append(f"Scores: {view['scores']}")
    lines.append(f"Your supply count: {view['supply_count_you']}")
    lines.append("")
    lines.append(CAPTURE_RULE_TEXT)
    lines.append("")
    lines.append(render_income_ledger(state, player))
    lines.append("")
    lines.append(
        "MAP (^ = mountain, ~ = water, $<value> = supply, H = home, "
        "[node-mark:owner]):"
    )
    lines.append(render_map(state))
    lines.append("")
    lines.append(render_adjacency_table(state, view["visible_nodes"]))
    lines.append("")
    lines.extend(_render_visible_units(view, player))
    lines.append("")

    if view["public_stance_matrix"]:
        lines.append("PUBLIC STANCE MATRIX (last round):")
        for sender, stances in sorted(view["public_stance_matrix"].items()):
            entries = ", ".join(
                f"p{tgt}={st}" for tgt, st in sorted(stances.items())
            )
            lines.append(f"  p{sender}: {entries or '(none declared)'}")
        lines.append("")

    if view["your_inbound_intents"]:
        lines.append("INBOUND INTENTS YOU RECEIVED (last round):")
        for sender, intents in view["your_inbound_intents"].items():
            for it in intents:
                vis = "public" if it.visible_to is None else sorted(it.visible_to)
                lines.append(
                    f"  p{sender} declared u{it.unit_id} -> "
                    f"{order_to_str(it.declared_order, state)} (visible_to={vis})"
                )
        lines.append("")

    lines.append(render_betrayal_ledger(state, player))
    lines.append("")
    lines.append(render_active_pacts(state, player))
    lines.append("")
    lines.append(render_pact_breach_ledger(state, player))
    lines.append("")
    lines.append(render_reputation(state, player))
    lines.append("")

    recip = view.get("public_reciprocation") or {}
    if recip:
        lines.append(
            "RECIPROCATION STANDING (public, rolling window; "
            "given/received/standing/freeride_debt):"
        )
        for p, r in sorted(recip.items()):
            lines.append(
                f"  p{p}: {r['given']}/{r['received']}/"
                f"{r['standing']:.2f}/{r['freeride_debt']}"
            )
        lines.append("")

    lines.append("YOUR UNITS (for declaring intents):")
    for u in state.units.values():
        if u.owner != player:
            continue
        legal = legal_orders_for_unit(state, u.id)
        opts = ", ".join(order_to_str(o, state) for o in legal)
        lines.append(f"  u{u.id} at node {u.location}: legal orders = [{opts}]")
    lines.append("")

    lines.append("=== RESPONSE FORMAT ===")
    lines.append("Reply with ONE JSON object:")
    lines.append("{")
    lines.append('  "press": {')
    lines.append('    "stance": {"<other_pid>": "ally|neutral|hostile", ...},')
    lines.append('    "intents": [')
    lines.append(
        '      {"unit_id": <int>, "declared_order": <order>, '
        '"visible_to": null | [<pid>, ...]}'
    )
    lines.append("    ]")
    lines.append("  },")
    lines.append('  "pacts": {')
    lines.append('    "propose": [')
    lines.append(
        '      {"counterparty": <pid>, "terms": [{"player": <pid>, '
        '"unit_id": <int>, "declared_order": <order>}, ...]}'
    )
    lines.append("    ],")
    lines.append('    "accept": [<pact_id>, ...]')
    lines.append("  }")
    lines.append("}")
    lines.append("Order objects:")
    lines.append('  {"type": "Hold"}')
    lines.append('  {"type": "Move", "dest": <node_id>}')
    lines.append('  {"type": "Support", "target": <unit_id>}')
    lines.append('  {"type": "Support", "target": <unit_id>, "require_dest": <node_id>}')
    lines.append("Notes:")
    lines.append(
        "- press.stance / press.intents / pacts are all optional; default empty."
    )
    lines.append(
        "- visible_to=null means public broadcast; a list means a private group."
    )
    lines.append(
        "- if the order you later submit for a unit doesn't match a declared_order "
        "intent, recipients see a public BetrayalObservation against you."
    )
    lines.append(
        "- pacts.propose terms must include >=1 unit from you and >=1 from the "
        "counterparty, or the proposal is dropped. pacts.accept lists pact_ids of "
        "PROPOSED pacts (shown in ACTIVE PACTS above) where you are the "
        "counterparty."
    )
    lines.append(
        "- once accepted, diverging from a pact term at finalize is a stronger, "
        "publicly-reputation-tracked PactBreach."
    )

    return NEGOTIATION_SYSTEM_PROMPT, "\n".join(lines)


def render_orders_prompt(
    state: GameState, view: dict, player: PlayerId, own_intents: list[Intent]
) -> tuple[str, str]:
    lines: list[str] = []
    lines.append(f"You are Player {player}. " + render_turn_calendar(state))
    lines.append(CAPTURE_RULE_TEXT)
    lines.append("")
    lines.append(
        "MAP (^ = mountain, ~ = water, $<value> = supply, H = home, "
        "[node-mark:owner]):"
    )
    lines.append(render_map(state))
    lines.append("")
    lines.append(render_adjacency_table(state, view["visible_nodes"]))
    lines.append("")
    lines.append(render_income_ledger(state, player))
    lines.append("")
    lines.extend(_render_visible_units(view, player))
    lines.append("")

    if own_intents:
        lines.append(
            f"YOUR DECLARED INTENTS THIS ROUND (turn {state.turn + 1}) -- an "
            "order that diverges from these will be recorded as a public "
            "BetrayalObservation against you for anyone in visible_to:"
        )
        for it in own_intents:
            vis = "public" if it.visible_to is None else sorted(it.visible_to)
            lines.append(
                f"  u{it.unit_id} -> {order_to_str(it.declared_order, state)} "
                f"(visible_to={vis})"
            )
        lines.append("")

    lines.append(render_active_pacts(state, player))
    lines.append("")

    lines.append("YOUR UNITS — choose ONE order per unit:")
    for u in state.units.values():
        if u.owner != player:
            continue
        legal = legal_orders_for_unit(state, u.id)
        lines.append(
            f"  u{u.id} at node {u.location} "
            f"(adj: {sorted(state.map.neighbors(u.location))})"
        )
        for i, o in enumerate(legal):
            lines.append(f"    [{i}] {order_to_str(o, state)}")
    lines.append("")

    lines.append("=== RESPONSE FORMAT ===")
    lines.append('Reply with ONE JSON object: {"orders": {"<unit_id>": <order>, ...}}')
    lines.append("Order objects:")
    lines.append('  {"type": "Hold"}')
    lines.append('  {"type": "Move", "dest": <node_id>}')
    lines.append('  {"type": "Support", "target": <unit_id>}')
    lines.append('  {"type": "Support", "target": <unit_id>, "require_dest": <node_id>}')
    lines.append("Any owned unit you omit defaults to Hold.")

    return ORDERS_SYSTEM_PROMPT, "\n".join(lines)
