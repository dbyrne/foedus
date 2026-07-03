"""Shared prompt-rendering helpers for press-aware seat views.

Both the game server (foedus/game_server/render.py) and the offline
orchestrator (scripts/foedus_press_play.py) build the same kind of
plain-text seat prompt for LLM-driven players. This module holds the
presentation logic that's identical between them — map/order formatting,
the capture-rule text, the per-turn income ledger, adjacency tables, the
turn calendar, and the betrayal ledger — so both callers (and any future
caller, e.g. janus.llm.render) render the same numbers from the same code.

Phase 0a (arena legibility): the playtest that motivated this module found
the economy was a black box (supply values hidden, capture rule unstated,
no income ledger) and the board was illegible for coordination (support
targets unidentified, adjacency only shown for own units). See
docs/superpowers/specs/2026-07-01-foedus-phase0-arena-fixes-design.md
section 0a (F1/F2) for the full rationale.
"""

from __future__ import annotations

from foedus.core import (
    GameState,
    Hold,
    Map,
    Move,
    NodeId,
    NodeType,
    Order,
    PactStatus,
    PlayerId,
    ReputationTally,
    Support,
)

CAPTURE_RULE_TEXT = (
    "CAPTURE RULE: two ways to capture a supply/home center. (1) INSTANT: "
    "win a combat that dislodges the enemy unit occupying it — ownership "
    "flips the same turn, no Hold required. (2) WALK-IN: move onto an "
    "unoccupied/undefended one and then Hold it through the next "
    "resolution — passing through captures nothing. Plain nodes flip "
    "ownership on entry every turn. A captured center stays yours after "
    "you leave, until another player captures it by either method above."
)


def node_label(m: Map, n: NodeId) -> str:
    """Node id + terrain mark, with supply value embedded for SUPPLY nodes.

    Examples: "29$2" (value-2 supply), "24$1" (value-1 supply), "5H" (home
    — always value 1, so no value suffix), "8^" (mountain), "3~" (water),
    "12" (plain). HOME never gets a value suffix without consulting
    supply_value() because mapgen's high-value assignment only ever
    targets NodeType.SUPPLY (see resolve.py::_assign_high_value_supplies);
    HOME nodes are always value 1 by construction.

    Falls back to the bare id string for a node not in the map, so rendering
    an order that references an out-of-map id (e.g. an untrusted agent/LLM
    submitting Move(dest=<bogus>) as an intent or pact term) never crashes the
    prompt — resolution already drops such orders via normalization.
    """
    if n not in m.node_types:
        return str(n)
    t = m.node_types[n]
    if t == NodeType.SUPPLY:
        return f"{n}${m.supply_value(n)}"
    if t == NodeType.HOME:
        return f"{n}H"
    if t == NodeType.MOUNTAIN:
        return f"{n}^"
    if t == NodeType.WATER:
        return f"{n}~"
    return str(n)


def order_to_str(o: Order, state: GameState | None = None, *, bare: bool = False) -> str:
    """Render an Order for display.

    Without `state`, renders the bare structural form (dest/target ids
    only). With `state`, Move destinations show their value-annotated node
    label and Support targets show owner + location inline — e.g.
    "Support(target=u3 [P2 @ n25])" — so a support option is legible
    without cross-referencing a separate visible-units list (playtest
    finding: players were offered Support(target=uX) for units that
    weren't listed anywhere with an owner or location).

    `bare=True` forces truly bare integer ids regardless of `state` --
    for machine-facing text an LLM must copy verbatim into JSON, where
    "7$1"/"u3" are invalid tokens (diagnosed root cause of ~42% of
    LLMDiplomat parse failures: the model copied these labels straight
    into declared_order/orders JSON values).
    """
    if isinstance(o, Hold):
        return "Hold"
    if isinstance(o, Move):
        if bare:
            dest = str(o.dest)
        else:
            dest = node_label(state.map, o.dest) if state is not None else str(o.dest)
        return f"Move(dest={dest})"
    if isinstance(o, Support):
        if bare:
            target_s = str(o.target)
        else:
            target_s = f"u{o.target}"
            if state is not None:
                target = state.units.get(o.target)
                if target is not None:
                    target_s += f" [P{target.owner} @ n{target.location}]"
        if o.require_dest is None:
            return f"Support(target={target_s})"
        return f"Support(target={target_s}, require_dest={o.require_dest})"
    return str(o)


def render_map(state: GameState) -> str:
    """ASCII hex map with owner + node-type-and-value marks."""
    coords = state.map.coords
    qs = [c[0] for c in coords.values()]
    rs = [c[1] for c in coords.values()]
    qmin, qmax = min(qs), max(qs)
    rmin, rmax = min(rs), max(rs)
    by_qr = {coords[n]: n for n in coords}
    lines = []
    for r in range(rmin, rmax + 1):
        indent = " " * (3 * (r - rmin))
        row = indent
        for q in range(qmin, qmax + 1):
            n = by_qr.get((q, r))
            if n is None:
                row += "        "
                continue
            owner = state.ownership.get(n)
            owner_s = str(owner) if owner is not None else "-"
            row += f"[{node_label(state.map, n):>4}:{owner_s}]"
        lines.append(row)
    return "\n".join(lines)


def build_turns(state: GameState) -> list[int]:
    """Turn numbers on which a build phase fires, up to max_turns."""
    bp = state.config.build_period
    return list(range(bp, state.config.max_turns + 1, bp))


def income_ledger(state: GameState, player: PlayerId) -> dict:
    """Per-turn income data for `player`, matching resolve.py's tiered
    scoring loop (step 8) exactly — same node-type/ownership filter, same
    `map.supply_value` lookup — so the numbers shown never drift from what
    the engine actually pays out.

    Returns:
      owned: sorted [(node, value), ...] currently owned by `player`
      per_turn: sum of owned values (what player nets if nothing changes)
      occupying: sorted [(node, value), ...] where player has a unit on a
        supply/home they don't yet own (a fresh walk-in — Hold to convert)
      last_turn_delta: player's actual score change from the last resolved
        turn (0.0 before any turn has resolved)
    """
    owned_nodes = sorted(
        n for n, t in state.map.node_types.items()
        if t in (NodeType.SUPPLY, NodeType.HOME)
        and state.ownership.get(n) == player
    )
    owned = [(n, state.map.supply_value(n)) for n in owned_nodes]
    per_turn = sum(v for _, v in owned)

    occupying_nodes = sorted(
        u.location for u in state.units.values()
        if u.owner == player
        and state.map.is_supply(u.location)
        and state.ownership.get(u.location) != player
    )
    occupying = [(n, state.map.supply_value(n)) for n in occupying_nodes]

    return {
        "owned": owned,
        "per_turn": per_turn,
        "occupying": occupying,
        "last_turn_delta": state.last_turn_score_delta.get(player, 0.0),
    }


def render_income_ledger(state: GameState, player: PlayerId) -> str:
    data = income_ledger(state, player)
    owned_s = ",".join(f"{n}(v{v})" for n, v in data["owned"]) or "none"
    lines = [f"INCOME: you OWN centers {{{owned_s}}} = +{data['per_turn']:g}/turn."]
    if data["occupying"]:
        occ_s = ",".join(f"{n}(v{v})" for n, v in data["occupying"])
        lines.append(
            f"OCCUPYING (not yet converted): {{{occ_s}}} — stay put "
            f"(Hold/Support) through the next resolution to capture."
        )
    bt = build_turns(state)
    bt_s = ", ".join(str(t) for t in bt) if bt else "none"
    lines.append(
        f"Last turn you scored {data['last_turn_delta']:+g}. "
        f"Build turns: {bt_s}. Scoring resolves at end of each turn."
    )
    return "\n".join(lines)


def render_adjacency_table(state: GameState, nodes: list[NodeId]) -> str:
    """Full neighbor list for every node in `nodes` (typically a player's
    fog-visible set) — not just nodes with a unit on them — so agents can
    plan multi-turn routes."""
    lines = ["ADJACENCY (visible nodes):"]
    for n in sorted(nodes):
        neighbors = sorted(state.map.neighbors(n))
        nbr_s = ", ".join(node_label(state.map, nb) for nb in neighbors)
        lines.append(f"  {node_label(state.map, n)}: {nbr_s or '(none)'}")
    return "\n".join(lines)


def render_turn_calendar(state: GameState) -> str:
    bt = build_turns(state)
    bt_s = str(bt) if bt else "none"
    return (
        f"TURN CALENDAR: turn {state.turn + 1}/{state.config.max_turns}, "
        f"build turns: {bt_s}, détente threshold: "
        f"{state.config.detente_threshold}"
    )


def render_betrayal_ledger(state: GameState, player: PlayerId) -> str:
    """Standing betrayal ledger: cumulative counts by betrayer plus the
    most recent entries, so social state isn't held in the agent's head."""
    betrayals = state.betrayals.get(player, [])
    if not betrayals:
        return "BETRAYAL LEDGER: none observed yet."
    counts: dict[PlayerId, int] = {}
    for b in betrayals:
        counts[b.betrayer] = counts.get(b.betrayer, 0) + 1
    counts_s = ", ".join(f"p{p}={c}" for p, c in sorted(counts.items()))
    lines = [
        f"BETRAYAL LEDGER (cumulative, {len(betrayals)} total; "
        f"by player: {counts_s}):"
    ]
    for b in betrayals[-5:]:
        lines.append(
            f"  turn {b.turn}: p{b.betrayer} declared "
            f"u{b.intent.unit_id} -> {order_to_str(b.intent.declared_order, state)}, "
            f"actually issued {order_to_str(b.actual_order, state)}"
        )
    return "\n".join(lines)


def render_active_pacts(state: GameState, player: PlayerId) -> str:
    """F5: an "ACTIVE PACTS" block listing the live pacts `player` is a party
    to (proposed + accepted), so binding joint commitments are on the record
    rather than held in the agent's head.

    A pact is bilateral — only its two parties see it (matches fog's
    `your_pacts`). Each term shows the obligated player, unit, and the
    value-annotated order via `order_to_str`.
    """
    mine = [
        p for p in state.pacts
        if player == p.proposer or player == p.counterparty
    ]
    if not mine:
        return "ACTIVE PACTS: none."
    lines = ["ACTIVE PACTS (binding joint commitments):"]
    for p in mine:
        head = (
            f"  pact #{p.pact_id} [{p.status.value}] "
            f"between p{p.proposer} and p{p.counterparty}"
        )
        if p.status == PactStatus.PROPOSED:
            head += f" — awaiting p{p.counterparty} acceptance"
        lines.append(head)
        for t in p.terms:
            lines.append(
                f"    - p{t.player} u{t.unit_id} -> "
                f"{order_to_str(t.declared_order, state)}"
            )
    return "\n".join(lines)


def render_pact_breach_ledger(state: GameState, player: PlayerId) -> str:
    """F5: standing pact-breach ledger for `player` (breaches they observed),
    rendered alongside the betrayal ledger. Cumulative counts by breacher plus
    the most recent entries."""
    breaches = state.pact_breaches.get(player, [])
    if not breaches:
        return "PACT BREACH LEDGER: none observed yet."
    counts: dict[PlayerId, int] = {}
    for b in breaches:
        counts[b.breacher] = counts.get(b.breacher, 0) + 1
    counts_s = ", ".join(f"p{p}={c}" for p, c in sorted(counts.items()))
    lines = [
        f"PACT BREACH LEDGER (cumulative, {len(breaches)} total; "
        f"by player: {counts_s}):"
    ]
    for b in breaches[-5:]:
        lines.append(
            f"  turn {b.turn}: p{b.breacher} broke pact #{b.pact_id} — "
            f"pledged u{b.term.unit_id} -> "
            f"{order_to_str(b.term.declared_order, state)}, "
            f"actually issued {order_to_str(b.actual_order, state)}"
        )
    return "\n".join(lines)


def render_reputation(state: GameState, player: PlayerId) -> str:
    """F6: PUBLIC cumulative breach tally, visible to every player (not just
    victims like `render_betrayal_ledger`/`render_pact_breach_ledger`) — the
    social cost that lets the whole table refuse to ally with a proven
    betrayer. Lists every surviving player, defaulting absent entries to
    zero, so a clean record is as legible as a bad one."""
    survivors = sorted(
        p for p in range(state.config.num_players) if p not in state.eliminated
    )
    lines = [
        "REPUTATION (public, cumulative; intent breaches / pact breaches / total):"
    ]
    for p in survivors:
        r = state.reputation.get(p, ReputationTally())
        marker = " (you)" if p == player else ""
        lines.append(
            f"  p{p}{marker}: {r.intent_breaches} intent / "
            f"{r.pact_breaches} pact / {r.total} total"
        )
    return "\n".join(lines)
