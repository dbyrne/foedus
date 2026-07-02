"""Round-lifecycle engine functions for Press v0.

The engine never holds a timer or async event loop. These are pure
state-transition functions; drivers (CLI, web UI, training harness) call
them as events arrive.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from foedus.core import (
    BetrayalObservation,
    ChatDraft,
    ChatMessage,
    DoneCleared,
    GameState,
    Hold,
    Intent,
    IntentRevised,
    Move,
    Order,
    Pact,
    PactBreach,
    PactStatus,
    PactTerm,
    Phase,
    PlayerId,
    Press,
    ReputationTally,
    Stance,
    Support,
    SupportRound,
    UnitId,
)


def intent_dependencies(
    state: GameState,
) -> dict[PlayerId, frozenset[tuple[PlayerId, UnitId]]]:
    """Return per-player set of (other_player, unit) pairs whose intents/orders
    that player's pending plans mechanically depend on.

    A player P depends on (Q, U) iff P has a declared Intent for one of P's
    units whose order is Support(target=U) where state.units[U].owner == Q
    (including the Support(target=U, require_dest=X) pin variant — same
    dependency rule, since the pin's viability hinges on Q's choice for U).

    Self-dependencies (Q == P) are excluded; Q must be a different player.
    The graph is unit-grained: a single ally with two units yields up to two
    distinct (Q, U_a), (Q, U_b) entries when both are referenced.
    """
    out: dict[PlayerId, set[tuple[PlayerId, UnitId]]] = {}
    # Walk pending press intents.
    for player, press in state.round_press_pending.items():
        for intent in press.intents:
            order = intent.declared_order
            if not isinstance(order, Support):
                continue
            target_unit = state.units.get(order.target)
            if target_unit is None or target_unit.owner == player:
                continue
            out.setdefault(player, set()).add(
                (target_unit.owner, target_unit.id)
            )
    return {p: frozenset(deps) for p, deps in out.items()}


def submit_press_tokens(state: GameState, player: PlayerId,
                        press: Press) -> GameState:
    """Set/replace player's pending press tokens for the current round.

    Multiple calls overwrite (revisability until done). Intents are filtered:
    - intents about units not owned by `player` are dropped
    - intents with empty visible_to (or visible_to filtered to empty) are dropped
    - eliminated and self-references in visible_to are removed

    Returns state unchanged if:
    - phase is not NEGOTIATION
    - player is eliminated
    - player has already signaled done this round
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if player in state.eliminated:
        return state
    if player in state.round_done:
        return state

    cleaned_intents: list[Intent] = []
    for intent in press.intents:
        # Ownership filter.
        unit = state.units.get(intent.unit_id)
        if unit is None or unit.owner != player:
            continue
        # Visibility filter.
        vt = intent.visible_to
        if vt is None:
            cleaned_intents.append(intent)
            continue
        # Drop eliminated and self-references.
        cleaned_vt = frozenset(
            p for p in vt if p not in state.eliminated and p != player
        )
        if not cleaned_vt:
            continue  # empty after filter -> drop
        if cleaned_vt == vt:
            cleaned_intents.append(intent)
        else:
            cleaned_intents.append(replace(intent, visible_to=cleaned_vt))

    cleaned = Press(stance=dict(press.stance), intents=cleaned_intents)

    new_pending = dict(state.round_press_pending)
    new_pending[player] = cleaned

    # ----- Live intent visibility + dependency-aware done auto-clear -----

    # Build per-unit lookup of previously-submitted intents by THIS player
    # (last write wins).
    prev_press = state.round_press_pending.get(player)
    prev_by_unit: dict[UnitId, Intent] = {}
    if prev_press is not None:
        for it in prev_press.intents:
            prev_by_unit[it.unit_id] = it

    new_revisions = list(state.intent_revisions)
    new_done = set(state.round_done)
    new_clears = list(state.done_clears)
    revised_unit_keys: set[tuple[PlayerId, UnitId]] = set()

    for intent in cleaned_intents:
        prev = prev_by_unit.get(intent.unit_id)
        if prev == intent:
            continue  # no change
        new_revisions.append(IntentRevised(
            turn=state.turn + 1,
            player=player,
            intent=intent,
            previous=prev,
            visible_to=intent.visible_to,
        ))
        if prev is not None:  # E3: first declarations don't trigger auto-clear
            revised_unit_keys.add((player, intent.unit_id))

    # Detect retractions: previous intent for a unit no longer present in
    # the new submission.
    new_unit_ids = {it.unit_id for it in cleaned_intents}
    for prev_unit_id, prev_intent in prev_by_unit.items():
        if prev_unit_id not in new_unit_ids:
            new_revisions.append(IntentRevised(
                turn=state.turn + 1,
                player=player,
                intent=None,  # retraction
                previous=prev_intent,
                visible_to=prev_intent.visible_to,
            ))
            revised_unit_keys.add((player, prev_unit_id))

    s_pending = replace(state, round_press_pending=new_pending)
    deps = intent_dependencies(s_pending)

    for dependent_player, dep_set in deps.items():
        if dependent_player == player:
            continue  # self-revision doesn't clear own done
        for revised_key in revised_unit_keys:
            if revised_key in dep_set and dependent_player in new_done:
                new_done.discard(dependent_player)
                new_clears.append(DoneCleared(
                    turn=state.turn + 1,
                    player=dependent_player,
                    source_player=player,
                    source_unit=revised_key[1],
                ))
                break  # one clear per dependent per submit

    return replace(
        s_pending,
        intent_revisions=new_revisions,
        done_clears=new_clears,
        round_done=new_done,
    )


def signal_done(state: GameState, player: PlayerId) -> GameState:
    """Mark a player as done negotiating. Idempotent. Cannot be undone.

    Returns state unchanged if phase is not NEGOTIATION or player is eliminated.
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if player in state.eliminated:
        return state

    new_done = set(state.round_done)
    new_done.add(player)
    return replace(state, round_done=new_done)


def propose_pact(state: GameState, proposer: PlayerId,
                 counterparty: PlayerId,
                 terms: tuple[PactTerm, ...] | list[PactTerm]) -> GameState:
    """Propose a binding joint commitment (F5) between `proposer` and
    `counterparty` for the upcoming resolution.

    Terms are filtered silently (matching the order-normalization invariant —
    degenerate submissions vanish, never raise):
    - a term whose `player` is neither proposer nor counterparty is dropped
    - a term whose `unit_id` is not owned by `term.player` right now is dropped
    - a unit may carry at most ONE obligation: for a repeated `unit_id` the
      first term wins and later ones are dropped. This is load-bearing — it
      stops a proposer from stacking two conflicting obligations on a unit
      (which would guarantee a mismatch at finalize and manufacture a false
      breach against a fully-complying party).

    A Pact is created only if, after filtering, at least one term remains for
    EACH party — a genuine two-sided commitment. Otherwise the proposal is
    dropped (state returned unchanged).

    Returns state unchanged if:
    - phase is not NEGOTIATION
    - proposer or counterparty is eliminated
    - proposer == counterparty
    - proposer has already signaled done this round
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if proposer in state.eliminated or counterparty in state.eliminated:
        return state
    if proposer == counterparty:
        return state
    if proposer in state.round_done:
        return state

    parties = {proposer, counterparty}
    cleaned: list[PactTerm] = []
    seen_units: set[UnitId] = set()
    for term in terms:
        if term.player not in parties:
            continue
        unit = state.units.get(term.unit_id)
        if unit is None or unit.owner != term.player:
            continue
        if term.unit_id in seen_units:
            continue  # one obligation per unit; first wins (see docstring)
        seen_units.add(term.unit_id)
        cleaned.append(term)

    if not any(t.player == proposer for t in cleaned):
        return state
    if not any(t.player == counterparty for t in cleaned):
        return state

    pact = Pact(
        pact_id=state.next_pact_id,
        proposer=proposer,
        counterparty=counterparty,
        terms=tuple(cleaned),
        status=PactStatus.PROPOSED,
        proposed_turn=state.turn,
    )
    return replace(
        state,
        pacts=state.pacts + [pact],
        next_pact_id=state.next_pact_id + 1,
    )


def accept_pact(state: GameState, pact_id: int,
                accepter: PlayerId) -> GameState:
    """Ratify a PROPOSED pact. Only the pact's `counterparty` may accept.

    Once ACCEPTED the pact is binding for the next resolution. Idempotent
    (accepting an already-ACCEPTED pact is a no-op).

    Returns state unchanged if:
    - phase is not NEGOTIATION
    - accepter is eliminated or has signaled done this round
    - no PROPOSED pact with `pact_id` exists whose counterparty is `accepter`
    - the pact's proposer has since been eliminated (can't ratify a
      commitment with a party who no longer exists)
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if accepter in state.eliminated:
        return state
    if accepter in state.round_done:
        return state

    new_pacts: list[Pact] = []
    changed = False
    for pact in state.pacts:
        if (pact.pact_id == pact_id
                and pact.status == PactStatus.PROPOSED
                and pact.counterparty == accepter
                and pact.proposer not in state.eliminated):
            new_pacts.append(replace(pact, status=PactStatus.ACCEPTED))
            changed = True
        else:
            new_pacts.append(pact)
    if not changed:
        return state
    return replace(state, pacts=new_pacts)


def signal_chat_done(state: GameState, player: PlayerId) -> GameState:
    """Mark a player as done with the chat phase. Idempotent.

    Bundle 6: gates the commit-phase opening. Cannot be undone within a
    round. Returns state unchanged if phase is not NEGOTIATION or player
    is eliminated.
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if player in state.eliminated:
        return state
    new_chat_done = set(state.chat_done)
    new_chat_done.add(player)
    return replace(state, chat_done=new_chat_done)


def is_chat_phase_complete(state: GameState) -> bool:
    """True iff every surviving player has signaled chat-done.

    Bundle 6: when this returns True, the chat phase is closed and
    /commit submissions become valid.
    """
    survivors = {
        p for p in range(state.config.num_players) if p not in state.eliminated
    }
    return survivors.issubset(state.chat_done)


def is_round_complete(state: GameState) -> bool:
    """True iff every surviving player has signaled done."""
    survivors = {
        p for p in range(state.config.num_players) if p not in state.eliminated
    }
    return survivors.issubset(state.round_done)


def force_round_end(state: GameState) -> GameState:
    """Driver-invoked when timer expires (or driver decides to end).

    Marks all not-yet-done survivors as done with their most-recent submitted
    press (or empty Press if never submitted).
    """
    survivors = {
        p for p in range(state.config.num_players) if p not in state.eliminated
    }
    new_done = set(state.round_done)
    new_pending = dict(state.round_press_pending)
    for p in survivors:
        if p not in new_done:
            new_done.add(p)
            if p not in new_pending:
                new_pending[p] = Press(stance={}, intents=[])
    return replace(state, round_done=new_done,
                   round_press_pending=new_pending)


def record_chat_message(state: GameState, sender: PlayerId,
                        draft: ChatDraft) -> GameState:
    """Append a chat message to the current round's chat log.

    Engine constructs the canonical ChatMessage from sender + draft +
    state.turn + a monotonic sequence number.

    Drops the message silently (returns state unchanged) if:
    - phase is not NEGOTIATION
    - sender is eliminated or already signaled done
    - any named recipient is eliminated
    - body exceeds config.chat_char_cap
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if sender in state.eliminated:
        return state
    if sender in state.round_done:
        return state
    if len(draft.body) > state.config.chat_char_cap:
        return state
    if draft.recipients is not None:
        for r in draft.recipients:
            if r in state.eliminated:
                return state

    msg = ChatMessage(
        turn=state.turn,
        sequence=len(state.round_chat),
        sender=sender,
        recipients=draft.recipients,
        body=draft.body,
    )
    new_chat = list(state.round_chat)
    new_chat.append(msg)
    return replace(state, round_chat=new_chat)


def _broken_intents(
    flat: dict[UnitId, Order],
    state: GameState,
) -> list[tuple[PlayerId, Intent, Order]]:
    """Return (sender, intent, actual_order) for every declared Intent in the
    locked round press whose sender's RAW submitted order doesn't match.

    Shared by `_verify_intents` (which fans each broken intent out to every
    observer in its `visible_to` set) and F6's breach-penalty/reputation
    accounting (which must count each broken intent exactly ONCE regardless
    of how many players observe it -- a public intent with visible_to=None
    still reaches every survivor, but it's one broken promise).
    """
    out: list[tuple[PlayerId, Intent, Order]] = []
    for sender, press in state.round_press_pending.items():
        for intent in press.intents:
            unit = state.units.get(intent.unit_id)
            if unit is None or unit.owner != sender:
                continue  # void: unit dead or never owned by sender
            submitted = flat.get(intent.unit_id, Hold())
            if submitted != intent.declared_order:
                out.append((sender, intent, submitted))
    return out


def _fan_out_betrayals(
    broken: list[tuple[PlayerId, Intent, Order]],
    state: GameState,
) -> dict[PlayerId, list[BetrayalObservation]]:
    """Deliver each broken intent in `broken` to every player in its
    visible_to set (or all surviving non-senders if visible_to is None).

    Split out from `_verify_intents` so `finalize_round` can compute
    `_broken_intents` once and reuse it for both this fan-out AND the F6
    breach-penalty/reputation accounting, instead of recomputing it twice.
    """
    out: dict[PlayerId, list[BetrayalObservation]] = defaultdict(list)
    survivors = {
        p for p in range(state.config.num_players) if p not in state.eliminated
    }
    for sender, intent, submitted in broken:
        # Determine who observes the betrayal.
        if intent.visible_to is None:
            recipients = {p for p in survivors if p != sender}
        else:
            recipients = {
                p for p in intent.visible_to
                if p in survivors and p != sender
            }
        for recipient in recipients:
            out[recipient].append(BetrayalObservation(
                turn=state.turn + 1,
                betrayer=sender,
                intent=intent,
                actual_order=submitted,
            ))
    return dict(out)


def _verify_intents(
    flat: dict[UnitId, Order],
    state: GameState,
) -> dict[PlayerId, list[BetrayalObservation]]:
    """For each (sender, intent) tuple in the locked round press, check whether
    sender's RAW submitted order for the intent's unit matches the declared
    order. Mismatches emit BetrayalObservation to each player in the intent's
    visible_to set (or all surviving non-senders if visible_to is None).
    """
    return _fan_out_betrayals(_broken_intents(flat, state), state)


def _broken_pact_terms(
    flat: dict[UnitId, Order],
    state: GameState,
) -> list[tuple[Pact, PactTerm, Order]]:
    """Return (pact, term, actual_order) for every ACCEPTED pact term whose
    party's RAW submitted order doesn't match, regardless of whether the
    pact's other party (the observer) is still alive.

    Mirrors `_broken_intents`: shared by `_fan_out_pact_breaches` (which
    additionally gates delivery to the observer's private pact_breaches
    ledger on the observer being alive — a dead player can't act on a
    breach notification) and F6's breach-penalty/reputation accounting,
    which must count every broken commitment as true behavior independent
    of whether anyone survived to witness it. Code review finding: deriving
    the penalty/reputation count from the observer-gated dict instead of
    from this unfiltered list would let a player dodge the cost of a
    broken pact by timing the betrayal against an ally who happens to be
    eliminated the same turn -- an asymmetry `_broken_intents` never had
    (it was already observer-blind).
    """
    out: list[tuple[Pact, PactTerm, Order]] = []
    for pact in state.pacts:
        if pact.status != PactStatus.ACCEPTED:
            continue
        for term in pact.terms:
            unit = state.units.get(term.unit_id)
            if unit is None or unit.owner != term.player:
                continue  # void: party can't be bound by a lost unit
            submitted = flat.get(term.unit_id, Hold())
            if submitted != term.declared_order:
                out.append((pact, term, submitted))
    return out


def _fan_out_pact_breaches(
    broken: list[tuple[Pact, PactTerm, Order]],
    state: GameState,
) -> dict[PlayerId, list[PactBreach]]:
    """Deliver each broken pact term in `broken` to the OTHER party of its
    pact (the one who relied on the commitment) — unless that observer is
    eliminated, in which case there's no one left to notify.

    Split out from `_verify_pacts` so `finalize_round` can compute
    `_broken_pact_terms` once and reuse it for both this fan-out AND the F6
    breach-penalty/reputation accounting, mirroring `_fan_out_betrayals`.
    """
    breaches: dict[PlayerId, list[PactBreach]] = defaultdict(list)
    for pact, term, submitted in broken:
        observer = (
            pact.counterparty if term.player == pact.proposer
            else pact.proposer
        )
        if observer in state.eliminated:
            continue
        breaches[observer].append(PactBreach(
            turn=state.turn + 1,
            pact_id=pact.pact_id,
            breacher=term.player,
            term=term,
            actual_order=submitted,
        ))
    return dict(breaches)


def _verify_pacts(
    flat: dict[UnitId, Order],
    state: GameState,
) -> tuple[dict[PlayerId, list[PactBreach]], list[Pact]]:
    """Resolve pact obligations at finalize.

    Returns `(breaches_by_observer, surviving_pacts)`:

    - For every ACCEPTED pact, each term is checked against the RAW submitted
      order for its unit (`flat`), exactly as `_verify_intents` compares
      intents. A term is VOID (no breach) if its unit is gone or no longer
      owned by `term.player`. Otherwise a breach fires iff the submitted order
      differs from the declared order; the resulting `PactBreach` is delivered
      to the OTHER party of the pact (the one who relied on the commitment).
      ACCEPTED pacts are consumed (never survive).
    - PROPOSED pacts proposed THIS round survive (one more round to be
      accepted); older un-accepted proposals expire.
    """
    breaches = _fan_out_pact_breaches(_broken_pact_terms(flat, state), state)
    surviving: list[Pact] = [
        pact for pact in state.pacts
        if pact.status != PactStatus.ACCEPTED and pact.proposed_turn == state.turn
        # PROPOSED this round -> keep one more round. ACCEPTED pacts are
        # consumed regardless of honor/breach; older PROPOSED pacts expire.
    ]
    return breaches, surviving


def _stagnation_cost_deltas(
    canon: dict[UnitId, Order],
    state: GameState,
) -> dict[PlayerId, float]:
    """Return per-player score deltas for the stagnation cost.

    A player "did nothing" this turn if all their canon orders are
    Hold or Support-of-holder (no Move, no Support-of-mover). Such players pay
    `config.stagnation_cost`. Eliminated and unit-less players are exempt.

    If config.stagnation_cost == 0, returns an empty dict (disabled).

    History: stagnation_cost was originally 1.0 by default (Bundle 1) to
    discourage the v1 all-Hold détente-attractor degenerate game. Bundle 2's
    hold-or-dislodge supply-ownership rule now incentivizes committed
    Holds directly (you must Hold on a fresh capture to lock in ownership
    via rule (b)), making the stagnation penalty perverse — a single-unit
    player Holding to capture was paying for the strategically-correct play.
    The default was therefore changed to 0.0 in Bundle 2. The penalty
    mechanism is preserved here for callers who want the v1 behavior.
    """
    cost = state.config.stagnation_cost
    if cost == 0.0:
        return {}

    out: dict[PlayerId, float] = {}
    for p in range(state.config.num_players):
        if p in state.eliminated:
            continue
        p_units = [u for u in state.units.values() if u.owner == p]
        if not p_units:
            continue
        p_orders = [canon.get(u.id) for u in p_units]
        # Treat Move and support-of-mover as "did something":
        # Support(target=X) is active iff X's canon order is a Move.
        from foedus.core import Support  # local import to avoid cycle
        active = False
        for o in p_orders:
            if isinstance(o, Move):
                active = True
                break
            if isinstance(o, Support):
                # Active only when the supported unit is itself moving.
                target_order = canon.get(o.target)
                if isinstance(target_order, Move):
                    active = True
                    break
        if not active:
            out[p] = -cost
    return out


# --- Primitive A: harm-typed breaches ---------------------------------------
#
# A divergence (submitted != declared) is a BREACH only when it harms a
# COMMITTED party X. For an Intent, X is a player the breacher declared ALLY
# toward within the intent's audience; for a Pact term, X is the co-signer.
# Harm is computed from engine state (pre-state vs post-resolution + the
# resolver's ResolutionDetail), never from self-reported labels. Pro-social
# redirects (Move -> Support a third party or the ally itself) harm no
# committed party and are NOT breaches.


def _committed_parties_for_intent(
    sender: PlayerId,
    intent: Intent,
    locked_press: dict[PlayerId, Press],
    survivors: set[PlayerId],
) -> set[PlayerId]:
    """Players toward whom `sender`'s current-round stance is ALLY, within the
    intent's audience (all survivors for a public intent, else visible_to).

    A unilateral Move-intent toward a NEUTRAL/HOSTILE player is information,
    not a promise — deviating from it can betray no one.
    """
    press = locked_press.get(sender)
    stance = press.stance if press is not None else {}
    audience = survivors if intent.visible_to is None else intent.visible_to
    return {
        x for x in audience
        if x != sender and x in survivors
        and stance.get(x, Stance.NEUTRAL) == Stance.ALLY
    }


def _pact_committed_party(pact: Pact, term: PactTerm) -> PlayerId:
    """The pact's OTHER signer — the party who relied on this term."""
    return pact.counterparty if term.player == pact.proposer else pact.proposer


def _breach_harms_party(
    breacher: PlayerId,
    X: PlayerId,
    unit_id: UnitId,
    declared_order: Order,
    state: GameState,
    s_after: GameState,
    detail: "object",
) -> bool:
    """True iff the DEVIATING unit `unit_id`'s actual action harmed committed
    party X (H1 aggression / H2 abandoned defense).

    Attribution is scoped to the specific deviating unit — NOT the breacher as
    a whole — so a pro-social redirect on one unit is never flagged just because
    a *different* unit of the same player harmed X the same turn (the false
    positive both code reviews caught). H1 fires only if THIS unit's own Move,
    or the (uncut) Move its own Support backed, dislodged X's unit or captured
    X's supply/home center.
    """
    m = state.map
    canon_order = detail.canon.get(unit_id)
    # The mover(s) this unit is responsible for: its own Move, or the mover its
    # uncut Support backed (a pinned Support must match the mover's dest).
    movers: list[UnitId] = []
    if isinstance(canon_order, Move):
        movers.append(unit_id)
    elif isinstance(canon_order, Support) and unit_id not in detail.cut:
        tgt_order = detail.canon.get(canon_order.target)
        if isinstance(tgt_order, Move) and (
            canon_order.require_dest is None
            or canon_order.require_dest == tgt_order.dest
        ):
            movers.append(canon_order.target)
    for mv in movers:
        if detail.outcome.get(mv) != "success":
            continue
        mv_order = detail.canon.get(mv)
        if not isinstance(mv_order, Move):
            continue
        # H1b (dislodge): this move dislodged an X unit.
        for d_uid, atk in detail.dislodged_by.items():
            if atk != mv:
                continue
            victim = state.units.get(d_uid)
            if victim is not None and victim.owner == X:
                return True
        # H1a (capture): this move captured an X supply/home center FOR THE
        # breacher. (A supporter-backed cross-player capture flips ownership to
        # the mover, not the breacher, and is caught by the H1b check above.)
        n = mv_order.dest
        if (m.is_supply(n) and state.ownership.get(n) == X
                and s_after.ownership.get(n) == breacher):
            return True
    # H2a (abandoned support-defense): THIS unit's DECLARED order was a Support
    # of X's unit, abandoned, and that unit was dislodged this turn.
    if isinstance(declared_order, Support):
        tgt = state.units.get(declared_order.target)
        if (tgt is not None and tgt.owner == X
                and detail.outcome.get(tgt.id) == "dislodged"):
            return True
    # H2b (abandoned hold-defense): THIS unit's DECLARED order was a Hold
    # adjacent to an X supply/home center captured (flipped from X) this turn.
    if isinstance(declared_order, Hold):
        u = state.units.get(unit_id)
        if u is not None:
            for c in m.neighbors(u.location):
                if not m.is_supply(c):
                    continue
                if state.ownership.get(c) != X:
                    continue
                new_owner = s_after.ownership.get(c)
                if new_owner is not None and new_owner != X:
                    return True
    return False


def _harmful_intent_breaches(
    broken: list[tuple[PlayerId, Intent, Order]],
    state: GameState,
    s_after: GameState,
    detail: "object",
    locked_press: dict[PlayerId, Press],
) -> list[tuple[PlayerId, Intent, Order]]:
    """Filter raw intent deviations to the harm-typed subset (Primitive A)."""
    survivors = {
        p for p in range(state.config.num_players) if p not in state.eliminated
    }
    out: list[tuple[PlayerId, Intent, Order]] = []
    for sender, intent, submitted in broken:
        parties = _committed_parties_for_intent(
            sender, intent, locked_press, survivors
        )
        if any(
            _breach_harms_party(
                sender, X, intent.unit_id, intent.declared_order,
                state, s_after, detail,
            )
            for X in parties
        ):
            out.append((sender, intent, submitted))
    return out


def _harmful_pact_breaches(
    broken: list[tuple[Pact, PactTerm, Order]],
    state: GameState,
    s_after: GameState,
    detail: "object",
) -> list[tuple[Pact, PactTerm, Order]]:
    """Filter raw pact-term deviations to the harm-typed subset (Primitive A)."""
    out: list[tuple[Pact, PactTerm, Order]] = []
    for pact, term, submitted in broken:
        X = _pact_committed_party(pact, term)
        if _breach_harms_party(
            term.player, X, term.unit_id, term.declared_order,
            state, s_after, detail,
        ):
            out.append((pact, term, submitted))
    return out


# --- Primitive B: per-turn reciprocation ledger -----------------------------


def _reciprocation_round(
    state: GameState,
    detail: "object",
    locked_press: dict[PlayerId, Press],
) -> tuple[frozenset[PlayerId], frozenset[PlayerId]]:
    """Compute this turn's (gave, received) sets for the reciprocation window.

    A player GAVE iff it issued >=1 uncut cross-player Support of a beneficiary
    it declared ALLY toward this round; the beneficiary's owner RECEIVED. Uses
    only real Support orders (present on every driver path).
    """
    gave: set[PlayerId] = set()
    received: set[PlayerId] = set()
    for uid, order in detail.canon.items():
        if uid in detail.cut:
            continue
        if not isinstance(order, Support):
            continue
        sup = state.units.get(uid)
        tgt = state.units.get(order.target)
        if sup is None or tgt is None or tgt.owner == sup.owner:
            continue
        press = locked_press.get(sup.owner)
        stance = press.stance if press is not None else {}
        if stance.get(tgt.owner, Stance.NEUTRAL) != Stance.ALLY:
            continue
        gave.add(sup.owner)
        received.add(tgt.owner)
    return frozenset(gave), frozenset(received)


def finalize_round(state: GameState,
                   orders_by_player: dict[PlayerId, dict[UnitId, Order]]
                   ) -> GameState:
    """Atomically: lock press, run order resolution + Press v0 post-steps,
    archive press/chat to history, return state for the next turn in
    NEGOTIATION phase with cleared scratch."""

    locked_press = dict(state.round_press_pending)
    locked_chat = list(state.round_chat)

    # Build the raw `flat` ourselves for use by _verify_intents.
    flat: dict[UnitId, Order] = {}
    for player, pmap in orders_by_player.items():
        for u_id, order in pmap.items():
            unit = state.units.get(u_id)
            if unit is None or unit.owner != player:
                continue
            flat[u_id] = order
    # Default missing units to Hold.
    for u_id in state.units:
        flat.setdefault(u_id, Hold())

    # Compute the RAW per-unit deviations from declared Intents / accepted Pact
    # terms (submitted != declared). These are harm-typed below via Primitive A
    # once resolution attribution is available.
    broken_intents_raw = _broken_intents(flat, state)
    broken_pact_terms_raw = _broken_pact_terms(flat, state)
    surviving_pacts = [
        pact for pact in state.pacts
        if pact.status != PactStatus.ACCEPTED and pact.proposed_turn == state.turn
    ]

    # Compute stance-matrix update against locked press.
    streak_increment = _all_pairs_mutual_ally(state)

    # Run the order resolution, capturing attribution (outcome + dislodge map)
    # for harm-typing.
    from foedus.resolve import _resolve_orders_detailed
    s_after, detail = _resolve_orders_detailed(state, orders_by_player)
    canon = detail.canon

    # Primitive A: a divergence counts as a breach only if it harmed a
    # committed party (an ALLY the breacher declared toward / a pact co-signer).
    # Pro-social redirects (Move -> Support) that harm no committed ally are
    # dropped here — no BetrayalObservation, no penalty, no reputation hit.
    broken_intents = _harmful_intent_breaches(
        broken_intents_raw, state, s_after, detail, locked_press
    )
    broken_pact_terms = _harmful_pact_breaches(
        broken_pact_terms_raw, state, s_after, detail
    )
    new_betrayals = _fan_out_betrayals(broken_intents, state)
    new_pact_breaches = _fan_out_pact_breaches(broken_pact_terms, state)

    # Apply stagnation cost deltas using the (post-normalization) canon.
    deltas = _stagnation_cost_deltas(canon, state)
    new_scores = dict(s_after.scores)
    for p, delta in deltas.items():
        new_scores[p] = new_scores.get(p, 0.0) + delta

    # Phase 0a (F1): fold the stagnation adjustment into the score delta
    # _resolve_orders already recorded, so last_turn_score_delta always
    # equals the true before/after score change for this turn.
    new_score_delta = dict(s_after.last_turn_score_delta)
    for p, delta in deltas.items():
        new_score_delta[p] = new_score_delta.get(p, 0.0) + delta

    # F6: betrayal teeth. Deduct a configurable score penalty from the
    # BREACHER for each broken declared Intent or broken accepted Pact term
    # this turn, and increment their PUBLIC reputation tally regardless of
    # penalty config (reputation tracks true behavior, not the mechanical
    # cost). Both counts are derived from `broken_intents`/`broken_pact_terms`
    # (computed above, BEFORE the observer-eliminated filtering that
    # `_fan_out_betrayals`/`_fan_out_pact_breaches` apply) rather than from
    # `new_betrayals`/`new_pact_breaches` -- deliberately, on two counts:
    #   1. A public (visible_to=None) intent breach fans out to every
    #      observer, but must still count as ONE broken commitment.
    #   2. Code review finding: deriving the penalty/reputation count from
    #      the observer-gated dicts would let a player dodge the cost of a
    #      breach by timing it against an ally who happens to be eliminated
    #      the same turn -- a real commitment was still broken even if no
    #      one survived to be individually notified.
    #
    # Clamping: like stagnation_cost, this can push a raw score negative.
    # scoring.py's payout functions already clamp with max(0, ...) at
    # consumption time, so raw scores are left unclamped here as the true
    # record of what happened this turn.
    intent_penalty = state.config.intent_breach_penalty
    pact_penalty = state.config.pact_breach_penalty

    breach_penalty: dict[PlayerId, float] = defaultdict(float)
    if intent_penalty:
        for breacher, _, _ in broken_intents:
            breach_penalty[breacher] += intent_penalty
    if pact_penalty:
        for _, term, _ in broken_pact_terms:
            breach_penalty[term.player] += pact_penalty
    for p, penalty in breach_penalty.items():
        new_scores[p] = new_scores.get(p, 0.0) - penalty
        new_score_delta[p] = new_score_delta.get(p, 0.0) - penalty

    new_reputation = dict(state.reputation)
    for breacher, _, _ in broken_intents:
        prev = new_reputation.get(breacher, ReputationTally())
        new_reputation[breacher] = replace(
            prev, intent_breaches=prev.intent_breaches + 1
        )
    for _, term, _ in broken_pact_terms:
        prev = new_reputation.get(term.player, ReputationTally())
        new_reputation[term.player] = replace(
            prev, pact_breaches=prev.pact_breaches + 1
        )

    # Update mutual_ally_streak. Bundle 4: any observed betrayal this turn
    # resets the streak to 0 (subject to config.betrayal_resets_detente).
    # This closes the "détente by lying" bug where Sycophant tables declare
    # ALLY but break their declared intents under the hood.
    if streak_increment:
        new_streak = state.mutual_ally_streak + 1
    else:
        new_streak = 0
    if state.config.betrayal_resets_detente and new_betrayals:
        new_streak = 0

    # Merge betrayals into the persistent dict. Carry forward from the
    # PRE-resolution state, not s_after — _resolve_orders constructs a fresh
    # GameState and doesn't propagate the new Press v0 fields, so s_after
    # has empty defaults for these.
    merged_betrayals = {p: list(v) for p, v in state.betrayals.items()}
    for p, obs_list in new_betrayals.items():
        merged_betrayals.setdefault(p, []).extend(obs_list)

    # F5: merge pact breaches into the persistent ledger (same carry-forward
    # rationale as betrayals — _resolve_orders drops press-layer fields).
    merged_pact_breaches = {p: list(v) for p, v in state.pact_breaches.items()}
    for p, obs_list in new_pact_breaches.items():
        merged_pact_breaches.setdefault(p, []).extend(obs_list)

    # F5: drop any surviving PROPOSED pact whose party was eliminated in this
    # round's resolution — a commitment with a dead party can never be honored
    # and would otherwise render "awaiting p<dead>" next round. (_verify_pacts
    # runs pre-resolution, so it can't see this round's eliminations.)
    surviving_pacts = [
        p for p in surviving_pacts
        if p.proposer not in s_after.eliminated
        and p.counterparty not in s_after.eliminated
    ]

    # Primitive B: record this turn's ally-Support activity and roll the
    # reciprocation window forward (trimmed to config.reciprocation_window).
    gave, received = _reciprocation_round(state, detail, locked_press)
    window = state.config.reciprocation_window
    new_support_ledger = state.support_ledger + [
        SupportRound(turn=state.turn + 1, gave=gave, received=received)
    ]
    if window > 0:
        new_support_ledger = new_support_ledger[-window:]
    else:
        new_support_ledger = []

    # Archive press and chat (carry forward from `state`, append new round).
    new_press_history = list(state.press_history)
    new_press_history.append(locked_press)
    new_chat_history = list(state.chat_history)
    new_chat_history.append(locked_chat)

    return replace(
        s_after,
        scores=new_scores,
        mutual_ally_streak=new_streak,
        press_history=new_press_history,
        chat_history=new_chat_history,
        betrayals=merged_betrayals,
        support_ledger=new_support_ledger,
        last_turn_score_delta=new_score_delta,
        # F5: carry forward pact state (s_after has empty defaults for these
        # since _resolve_orders builds a fresh GameState). Accepted pacts were
        # consumed; only this-round proposals survive.
        pacts=surviving_pacts,
        next_pact_id=state.next_pact_id,
        pact_breaches=merged_pact_breaches,
        # F6: public cumulative breach tally by breacher (see
        # ReputationTally). Already carries forward state.reputation via
        # new_reputation's dict(state.reputation) base.
        reputation=new_reputation,
        # Reset round scratch fields for next turn.
        phase=Phase.NEGOTIATION,
        round_chat=[],
        round_press_pending={},
        round_done=set(),
        chat_done=set(),
        intent_revisions=[],
        done_clears=[],
    )


def advance_turn(state: GameState,
                 orders_by_player: dict[PlayerId, dict[UnitId, Order]]
                 ) -> GameState:
    """Convenience wrapper for the no-press / training path:
    submit empty press from each survivor, signal-done all, then finalize.
    """
    s = state
    survivors = [
        p for p in range(s.config.num_players) if p not in s.eliminated
    ]
    for p in survivors:
        s = submit_press_tokens(s, p, Press(stance={}, intents=[]))
        s = signal_done(s, p)
    return finalize_round(s, orders_by_player)


def _all_pairs_mutual_ally(state: GameState) -> bool:
    """True iff every ordered pair (i, j) of distinct survivors has
    state.round_press_pending[i].stance.get(j, NEUTRAL) == ALLY.

    Returns False for fewer than 2 survivors (détente requires multiple).
    """
    survivors = [
        p for p in range(state.config.num_players) if p not in state.eliminated
    ]
    if len(survivors) < 2:
        return False
    for i in survivors:
        press_i = state.round_press_pending.get(i, Press(stance={}, intents=[]))
        for j in survivors:
            if i == j:
                continue
            if press_i.stance.get(j, Stance.NEUTRAL) != Stance.ALLY:
                return False
    return True
