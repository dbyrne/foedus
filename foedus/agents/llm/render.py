"""Prompt rendering for LLMDiplomat.

Composes foedus.render_common's existing building blocks (map, income
ledger, adjacency, betrayal/pact ledgers, public reputation, active
pacts, the response-format block) into the two LLM-call prompts
(negotiate, orders) instead of re-implementing any of that rendering --
scripts/foedus_press_play.py already renders the same content the same
way for a human LLM driver, and this mirrors it.
"""

from __future__ import annotations

from foedus.agents.llm.campaign_memory import (
    CampaignMemory, GameFacts, IdentityContext,
)
from foedus.agents.llm.memory import ReciprocationMemory
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

SELF_NOTE_SYSTEM_PROMPT = (
    "You just finished a game of Foedus. The next game reuses the SAME seats, "
    "so you will face these same opponents again. Write a brief private note to "
    "your future self: at most 80 words, plain text only (no markdown, no JSON, "
    "no headings). Capture whatever you judge useful for playing these opponents "
    "next time. The note is for your eyes only."
)

# Ruleset v1.1 identity-keyed variant: seats rotate between games, so the note
# must reference opponents by their stable handle, not the seat they held.
SELF_NOTE_SYSTEM_PROMPT_IDENTITY = (
    "You just finished a game of Foedus. Across this campaign you keep facing "
    "the same opponents; each is identified by a stable handle that does NOT "
    "change between games, even though their seat numbers do. Write a brief "
    "private note to your future self: at most 80 words, plain text only (no "
    "markdown, no JSON, no headings). Capture whatever you judge useful for "
    "playing these opponents (referred to by handle) next time. The note is for "
    "your eyes only."
)


def _hlabel(seat: PlayerId, identity: IdentityContext | None) -> str:
    """Seat label, annotated with the entrant's stable handle when an identity
    legend is active: ``p2 (Foxtrot)``; plain ``p2`` otherwise."""
    if identity is not None and seat in identity.seat_to_handle:
        return f"p{seat} ({identity.seat_to_handle[seat]})"
    return f"p{seat}"


def render_identity_legend(
    identity: IdentityContext, player: PlayerId
) -> list[str]:
    """The per-game seat legend (Ruleset v1.1). Maps this game's seats to the
    campaign-stable handles so the agent can connect handle-keyed cross-game
    memory to the seats it acts on this game. Neutral text (counts/labels only,
    passes the leading-words denylist)."""
    lines = [
        "PLAYER HANDLES THIS GAME (each handle is the same entrant every game "
        "of this campaign; seat numbers change between games, handles do not):"
    ]
    for seat, handle in sorted(identity.seat_to_handle.items()):
        me = " (you)" if seat == player else ""
        lines.append(f"  p{seat} = {handle}{me}")
    return lines


def _render_visible_units(view: dict, player: PlayerId,
                          identity: IdentityContext | None = None) -> list[str]:
    lines = ["VISIBLE UNITS:"]
    for u in view["visible_units"]:
        if u["owner"] == player:
            marker = "(YOURS)"
        elif identity is not None:
            # "(p2 (Foxtrot))": keeps the seat number (the metrics extractor +
            # the engine work in seat space) and adds the stable handle.
            marker = f"({_hlabel(u['owner'], identity)})"
        else:
            # No identity => byte-identical to the pre-v1.1 seat-keyed prompt.
            marker = f"(player {u['owner']})"
        lines.append(f"  u{u['id']} at node {u['location']} {marker}")
    return lines


def render_reciprocation_record(
    memory: ReciprocationMemory, player: PlayerId,
    identity: IdentityContext | None = None,
) -> list[str]:
    """The agent-side reciprocation record for `player` (see
    foedus.agents.llm.memory). Purely factual bookkeeping: per opponent, how
    many of the turns this seat observed they declared ALLY toward it, how many
    turns this seat spent supporting their units, and this seat's own prior
    declared stances toward them.

    NEUTRALITY is a hard requirement (experiment integrity): counts and turn
    numbers only. No advice, judgement, or leading language — the experiment
    tests whether the model acts on information, not whether a prompt can smuggle
    in the conclusion. The one framing sentence names what the section is.
    """
    opponents = memory.opponents()
    if not opponents:
        return ["RECIPROCATION RECORD: none observed yet."]
    lines = [
        "RECIPROCATION RECORD (your own observations across prior turns; "
        "declared stances you received and Support you have given — from your "
        "fogged views only):"
    ]
    for p in opponents:
        rec = memory.record(p)
        prior = ", ".join(rec.my_prior_stances) or "none"
        # All three stance counts are surfaced symmetrically (no single-lens
        # emphasis) — factual bookkeeping only, per the neutrality requirement.
        lines.append(
            f"  {_hlabel(p, identity)}: declared toward you across {rec.turns_observed} observed "
            f"turns — ally {rec.ally_toward_me}, neutral {rec.neutral_toward_me}, "
            f"hostile {rec.hostile_toward_me}; you gave Support to their units on "
            f"{rec.turns_i_supported_them} turns; your prior stances toward them: "
            f"{prior}."
        )
    return lines


def _fmt_score(s: float) -> str:
    # Integer scores render without a trailing ".0"; fractional keep precision.
    return f"{s:g}"


def render_game_facts(facts: GameFacts, player: PlayerId) -> list[str]:
    """Neutral per-game facts for the PRIOR GAMES section: counts and outcomes
    only, no advice or judgement (same neutrality bar as the within-game
    reciprocation ledger). The self-note is rendered SEPARATELY, verbatim.

    `their_support_intent_toward_me` is labeled as a DECLARED intent, never as
    executed support, because executed support is not fog-observable.

    When the record carries handles (Ruleset v1.1), opponents and scores are
    rendered by the entrant's stable handle rather than the seat it held that
    game, so a later game reads the record about the same entrant regardless of
    seat rotation.
    """
    def _label(seat: PlayerId) -> str:
        if facts.handles and seat in facts.handles:
            return facts.handles[seat]
        return f"p{seat}"

    scores = "; ".join(
        f"{_label(p)}={_fmt_score(s)}" for p, s in sorted(facts.final_scores.items())
    )
    if facts.my_handle is not None:
        who = f"you played as {facts.my_handle}"
    else:
        who = f"you were seat p{facts.my_seat}"
    lines = [
        f"  Game (seed {facts.seed}): final scores {scores}; {who}, "
        f"finished rank {facts.my_rank} of {facts.n_players}."
    ]
    for p, of in sorted(facts.per_opponent.items()):
        lines.append(
            f"    {_label(p)}: declared ally toward you on {of.ally_toward_me} of "
            f"{of.turns_observed} observed turns; you gave Support to their units "
            f"on {of.my_supports_of_them} turns; they declared Support intents "
            f"toward your units on {of.their_support_intent_toward_me} turns; "
            f"accepted pact with you: {'yes' if of.pact_with_me else 'no'}; "
            f"breach by them toward you: {'yes' if of.breach_involving_me else 'no'}."
        )
    return lines


def render_campaign_record(
    campaign_memory: CampaignMemory, player: PlayerId
) -> list[str]:
    """The PRIOR GAMES section: per past game (capped, oldest-first) the neutral
    facts followed by this seat's OWN verbatim note. Empty when no prior game
    has been recorded (i.e. game 1 of a campaign)."""
    games = campaign_memory.recent()
    if not games:
        return []
    lines = [
        "PRIOR GAMES (your own records from earlier games this campaign, "
        "oldest first — factual counts from your fogged views, then your own "
        "note to yourself):"
    ]
    for rec in games:
        lines.extend(render_game_facts(rec.facts, player))
        # The note is the agent's OWN words: rendered EXACTLY, no editing.
        note = rec.self_note.strip() or "(none)"
        lines.append(f'    Your note to yourself: "{note}"')
    return lines


def render_self_note_prompt(
    facts: GameFacts, player: PlayerId
) -> tuple[str, str]:
    """The one post-game LLM call that asks a seat to write its own ≤80-word
    note to its future self. The neutral facts are handed to the model; the note
    it returns is stored verbatim (see campaign_memory)."""
    if facts.my_handle is not None:
        system = SELF_NOTE_SYSTEM_PROMPT_IDENTITY
        header = f"You are {facts.my_handle}. The game just ended."
    else:
        system = SELF_NOTE_SYSTEM_PROMPT
        header = f"You are Player {player}. The game just ended."
    lines = [
        header,
        "",
        "FACTS FROM THE GAME YOU JUST PLAYED:",
    ]
    lines.extend(render_game_facts(facts, player))
    lines.append("")
    lines.append(
        "Write your note now: at most 80 words, plain text, no markdown."
    )
    return system, "\n".join(lines)


def render_negotiation_prompt(
    state: GameState, view: dict, player: PlayerId,
    recip_memory: ReciprocationMemory | None = None,
    campaign_memory: CampaignMemory | None = None,
    identity: IdentityContext | None = None,
) -> tuple[str, str]:
    lines: list[str] = []
    lines.append(f"You are Player {player}. " + render_turn_calendar(state))
    if identity is not None:
        lines.extend(render_identity_legend(identity, player))
        lines.append("")
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
    lines.extend(_render_visible_units(view, player, identity))
    lines.append("")

    if view["public_stance_matrix"]:
        lines.append("PUBLIC STANCE MATRIX (last round):")
        for sender, stances in sorted(view["public_stance_matrix"].items()):
            entries = ", ".join(
                f"{_hlabel(tgt, identity)}={st}" for tgt, st in sorted(stances.items())
            )
            lines.append(f"  {_hlabel(sender, identity)}: {entries or '(none declared)'}")
        lines.append("")

    if view["your_inbound_intents"]:
        lines.append("INBOUND INTENTS YOU RECEIVED (last round):")
        for sender, intents in view["your_inbound_intents"].items():
            for it in intents:
                vis = "public" if it.visible_to is None else sorted(it.visible_to)
                lines.append(
                    f"  {_hlabel(sender, identity)} declared u{it.unit_id} -> "
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
                f"  {_hlabel(p, identity)}: {r['given']}/{r['received']}/"
                f"{r['standing']:.2f}/{r['freeride_debt']}"
            )
        lines.append("")

    # Optional cross-game memory (campaign mode). Default OFF -> nothing
    # appended, so the prompt is byte-identical to the single-game arm. Rendered
    # before the within-game ledger: prior-game history, then this game's record.
    if campaign_memory is not None:
        section = render_campaign_record(campaign_memory, player)
        if section:
            lines.extend(section)
            lines.append("")

    # Optional agent-side reciprocation memory (default OFF -> nothing appended,
    # so the prompt is byte-identical to the no-ledger arm).
    if recip_memory is not None:
        lines.extend(render_reciprocation_record(recip_memory, player, identity))
        lines.append("")

    lines.append("YOUR UNITS (for declaring intents):")
    for u in state.units.values():
        if u.owner != player:
            continue
        legal = legal_orders_for_unit(state, u.id)
        opts = ", ".join(order_to_str(o, state, bare=True) for o in legal)
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
    lines.append(
        "- in JSON, use bare integer node/unit ids (e.g. 7, not 7$1; 2, not 2H)."
    )

    return NEGOTIATION_SYSTEM_PROMPT, "\n".join(lines)


def render_orders_prompt(
    state: GameState, view: dict, player: PlayerId, own_intents: list[Intent],
    identity: IdentityContext | None = None,
) -> tuple[str, str]:
    lines: list[str] = []
    lines.append(f"You are Player {player}. " + render_turn_calendar(state))
    if identity is not None:
        lines.extend(render_identity_legend(identity, player))
        lines.append("")
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
    lines.extend(_render_visible_units(view, player, identity))
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
            lines.append(f"    [{i}] {order_to_str(o, state, bare=True)}")
    lines.append("")

    lines.append("=== RESPONSE FORMAT ===")
    lines.append('Reply with ONE JSON object: {"orders": {"<unit_id>": <order>, ...}}')
    lines.append("Order objects:")
    lines.append('  {"type": "Hold"}')
    lines.append('  {"type": "Move", "dest": <node_id>}')
    lines.append('  {"type": "Support", "target": <unit_id>}')
    lines.append('  {"type": "Support", "target": <unit_id>, "require_dest": <node_id>}')
    lines.append("Any owned unit you omit defaults to Hold.")
    lines.append(
        "In JSON, use bare integer node/unit ids (e.g. 7, not 7$1; 2, not 2H)."
    )

    return ORDERS_SYSTEM_PROMPT, "\n".join(lines)
