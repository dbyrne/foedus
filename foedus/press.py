"""Round-lifecycle engine functions for Press v0.

The engine never holds a timer or async event loop. These are pure
state-transition functions; drivers (CLI, web UI, training harness) call
them as events arrive.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from foedus.core import (
    AidSpend,
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
    Phase,
    PlayerId,
    Press,
    Stance,
    Support,
    UnitId,
)


def intent_dependencies(
    state: GameState,
) -> dict[PlayerId, frozenset[tuple[PlayerId, UnitId]]]:
    """Return per-player set of (other_player, unit) pairs whose intents/orders
    that player's pending plans mechanically depend on.

    A player P depends on (Q, U) iff P has at least one of:
      - A declared Intent for one of P's units whose order is Support(target=U)
        where state.units[U].owner == Q.
      - A pending AidSpend with target_unit=U where state.units[U].owner == Q.
      - A declared Intent whose order is Support(target=U, require_dest=X)
        (the pin variant — same dependency rule, since the pin's viability
        hinges on Q's choice for U).

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
    # Walk pending aid spends.
    for spender, spends in state.round_aid_pending.items():
        for spend in spends:
            target_unit = state.units.get(spend.target_unit)
            if target_unit is None or target_unit.owner == spender:
                continue
            out.setdefault(spender, set()).add(
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


def submit_aid_spends(state: GameState, player: PlayerId,
                      spends: list[AidSpend]) -> GameState:
    """Set/replace `player`'s pending aid spends for the current round.

    Each spend pays one aid token to add +1 strength to the named ally unit's
    canon order this turn (reactive — lands on whatever the recipient does).
    Spends are filtered:
    - target_unit unknown or eliminated-player-owned → dropped
    - target_unit owned by spender → dropped (can't aid self)
    - recipient not mutual ALLY in previous turn's locked press → dropped

    Token balance capped at submit time. Multiple calls overwrite.
    Returns state unchanged if phase != NEGOTIATION, player eliminated, or
    player has signaled done.
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if player in state.eliminated:
        return state
    if player in state.round_done:
        return state

    cleaned: list[AidSpend] = []
    survivors = {
        p for p in range(state.config.num_players) if p not in state.eliminated
    }
    last_press = state.press_history[-1] if state.press_history else {}
    for spend in spends:
        target = state.units.get(spend.target_unit)
        if target is None:
            continue
        if target.owner == player:
            continue
        if target.owner not in survivors:
            continue
        # Mutual-ALLY gate from previous turn's locked press.
        my_prev = last_press.get(player)
        their_prev = last_press.get(target.owner)
        if my_prev is None or their_prev is None:
            # No archived press yet (turn 0): allow, since there's no prior
            # stance to gate on. Players can establish initial alliances.
            cleaned.append(spend)
            continue
        if my_prev.stance.get(target.owner, Stance.NEUTRAL) != Stance.ALLY:
            continue
        if their_prev.stance.get(player, Stance.NEUTRAL) != Stance.ALLY:
            continue
        cleaned.append(spend)

    # Cap by token balance. Tokens are consumed at finalize regardless of
    # whether the aid "lands" (recipient may not follow through), so we cap
    # the COMMITMENT here rather than refunding wasted aid later.
    balance = state.aid_tokens.get(player, 0)
    if len(cleaned) > balance:
        cleaned = cleaned[:balance]

    new_pending = dict(state.round_aid_pending)
    prev_spends = state.round_aid_pending.get(player, [])
    prev_targets = {s.target_unit for s in prev_spends}
    new_targets = {s.target_unit for s in cleaned}
    # E3: only retractions (prev_targets - new_targets) trigger auto-clear.
    # Freshly added aid spends do not, matching the press-intent rule.
    revised_unit_keys = {(player, u) for u in (prev_targets - new_targets)}

    new_pending[player] = cleaned
    s_pending = replace(state, round_aid_pending=new_pending)
    deps = intent_dependencies(s_pending)

    new_done = set(state.round_done)
    new_clears = list(state.done_clears)
    for dependent_player, dep_set in deps.items():
        if dependent_player == player:
            continue
        for revised_key in revised_unit_keys:
            if revised_key in dep_set and dependent_player in new_done:
                new_done.discard(dependent_player)
                new_clears.append(DoneCleared(
                    turn=state.turn + 1,
                    player=dependent_player,
                    source_player=player,
                    source_unit=revised_key[1],
                ))
                break

    return replace(
        s_pending,
        round_done=new_done,
        done_clears=new_clears,
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


def _verify_intents(
    flat: dict[UnitId, Order],
    state: GameState,
) -> dict[PlayerId, list[BetrayalObservation]]:
    """For each (sender, intent) tuple in the locked round press, check whether
    sender's RAW submitted order for the intent's unit matches the declared
    order. Mismatches emit BetrayalObservation to each player in the intent's
    visible_to set (or all surviving non-senders if visible_to is None).
    """
    out: dict[PlayerId, list[BetrayalObservation]] = defaultdict(list)
    survivors = {
        p for p in range(state.config.num_players) if p not in state.eliminated
    }
    for sender, press in state.round_press_pending.items():
        for intent in press.intents:
            unit = state.units.get(intent.unit_id)
            if unit is None or unit.owner != sender:
                continue  # void: unit dead or never owned by sender

            submitted = flat.get(intent.unit_id, Hold())

            if submitted != intent.declared_order:
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

    # Verify intents BEFORE running _resolve_orders so we can compare against
    # raw input. (The verifier inspects state.round_press_pending.)
    new_betrayals = _verify_intents(flat, state)

    # Build a parallel canon dict for stagnation cost evaluation.
    from foedus.resolve import _normalize
    canon = {u_id: _normalize(state, u_id, o, flat) for u_id, o in flat.items()}

    # Compute stance-matrix update against locked press.
    streak_increment = _all_pairs_mutual_ally(state)

    # Run the order resolution.
    from foedus.resolve import _resolve_orders
    s_after = _resolve_orders(state, orders_by_player)

    # Apply stagnation cost deltas using the (post-normalization) canon.
    deltas = _stagnation_cost_deltas(canon, state)
    new_scores = dict(s_after.scores)
    for p, delta in deltas.items():
        new_scores[p] = new_scores.get(p, 0.0) + delta

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

    # Bundle 4: update aid_given ledger and aid_tokens balances.
    # _resolve_orders already applied combat reward, alliance bonus gating,
    # and aid-strength bonuses to s_after.scores. Here we just propagate the
    # bookkeeping that lives outside the order-resolution loop.
    new_aid_given = dict(state.aid_given)
    new_aid_tokens = dict(state.aid_tokens)
    survivors_post = [
        p for p in range(state.config.num_players) if p not in s_after.eliminated
    ]

    # Determine which spends "landed" (reactive: recipient's unit survived).
    for spender, spends in state.round_aid_pending.items():
        if spender in s_after.eliminated:
            # Spender eliminated mid-turn: their spends are still consumed
            # token-wise but treat as non-landing (no leverage gained).
            continue
        balance = new_aid_tokens.get(spender, 0)
        # Tokens are consumed regardless of landing.
        new_aid_tokens[spender] = max(0, balance - len(spends))
        for spend in spends:
            target_unit = state.units.get(spend.target_unit)
            if target_unit is None:
                continue
            recipient = target_unit.owner
            if recipient in state.eliminated:
                continue
            # Reactive aid: lands iff recipient's unit had any canon order
            # this turn. Ownership and survival are sufficient.
            if spend.target_unit not in canon:
                continue
            key = (spender, recipient)
            new_aid_given[key] = new_aid_given.get(key, 0) + 1

    # Token regeneration: floor(supply_count / divisor), capped.
    divisor = max(1, state.config.aid_generation_divisor)
    cap = state.config.aid_token_cap
    for p in survivors_post:
        # supply_count uses ownership; s_after has the new ownership.
        gen = s_after.supply_count(p) // divisor
        new_aid_tokens[p] = min(cap, new_aid_tokens.get(p, 0) + gen)

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
        aid_tokens=new_aid_tokens,
        aid_given=new_aid_given,
        # Reset round scratch fields for next turn.
        phase=Phase.NEGOTIATION,
        round_chat=[],
        round_press_pending={},
        round_done=set(),
        chat_done=set(),
        round_aid_pending={},
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
