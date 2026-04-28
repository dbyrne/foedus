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
    GameState,
    Hold,
    Intent,
    Move,
    Order,
    Phase,
    PlayerId,
    Press,
    Stance,
    SupportMove,
    UnitId,
)


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

    return replace(state, round_press_pending=new_pending)


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
    Hold or SupportHold (no Move, no SupportMove). Such players pay
    `config.stagnation_cost`. Eliminated and unit-less players are exempt.

    If config.stagnation_cost == 0, returns an empty dict (disabled).

    Known interaction with Bundle 2 (mechanic A — supply ownership
    cadence): under that rule, a player who walks into an empty supply
    must HOLD on it for the next full turn to lock in ownership. If
    that hold is the player's only order (e.g. single-unit player), the
    stagnation cost penalizes that hold (-1.0 by default), exactly
    canceling the +1 score from the newly-owned supply. Net 0 for the
    capture turn. This catch-22 is a known design tension; revisit if
    playtest data shows it disincentivizes commitment-to-hold beyond
    the intent. Possible future tuning: exempt holds-on-recently-walked-
    into-supplies, or shrink stagnation_cost magnitude.
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
        if not any(isinstance(o, (Move, SupportMove)) for o in p_orders):
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

    # Update mutual_ally_streak.
    new_streak = state.mutual_ally_streak + 1 if streak_increment else 0

    # Merge betrayals into the persistent dict. Carry forward from the
    # PRE-resolution state, not s_after — _resolve_orders constructs a fresh
    # GameState and doesn't propagate the new Press v0 fields, so s_after
    # has empty defaults for these.
    merged_betrayals = {p: list(v) for p, v in state.betrayals.items()}
    for p, obs_list in new_betrayals.items():
        merged_betrayals.setdefault(p, []).extend(obs_list)

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
        # Reset round scratch fields for next turn.
        phase=Phase.NEGOTIATION,
        round_chat=[],
        round_press_pending={},
        round_done=set(),
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
