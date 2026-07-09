"""Punishment-stage classifier for the S1 corpus autopsy
(M-foedus-s1-corpus-autopsy).

The canonical campaign (docs/research/2026-07-04-canonical-campaign-v1) asks a
narrower, more mechanistic question than the top-line scorecard
(`foedus.eval.memory_metrics`): when the table *does* react to the freerider,
where does the reaction break down? This module classifies, per game/turn/
seat, whether punishing the freerider was ever:

  (a) PROPOSED in press -- a hostile stance declaration, a declared attack-move
      intent (a Move onto a node the freerider currently occupies), or an
      attack-shaped pact proposal between two non-freerider parties;
  (b) EXECUTED as a real order -- an attack Move actually submitted in the
      orders phase, or a Support of one (by any seat, not just the mover's);
  (c) PAID -- the freerider's own per-turn income (carried in every negotiate
      prompt's public `Scores` dict) actually dropped after an execution,
      i.e. a center was captured away from it.

Everything here is derived from the same self-contained JSON the harness
already emits (`raw_response` + `prompt.user`) -- no live GameState needed, so
it is directly testable against scripted records and safe to run read-only
over the sealed corpus.

Node occupancy for "is this Move/Support an attack on the freerider" is judged
from the ACTING seat's OWN visible-units snapshot at decision time (not a
merged, all-seeing view) -- a seat can only deliberately target what it can
see. Cross-seat coordination (seat B supporting seat A's attacking unit) is
resolved by unit id, which is global and stable across all seats' logs.
"""

from __future__ import annotations

import re

from foedus.agents.llm.parse import coerce_id, extract_json_with_recovery

_VISIBLE_UNIT_RE = re.compile(
    r"u(\d+) at node (\d+)\S* \((?:YOURS|p(?:layer )?(\d+))"
)
_SCORES_RE = re.compile(r"Scores: (\{[^}]*\})")


def _extract(raw: str):
    """Parse a decision's raw_response the same way the diplomat does; None if
    it isn't JSON (e.g. a `<client error: ...>` fallback record)."""
    try:
        data, _ = extract_json_with_recovery(raw or "")
    except Exception:  # noqa: BLE001 - untrusted logged text, never crash a report
        return None
    return data


def parse_visible_units(prompt_user: str, me_seat: int) -> dict[int, dict]:
    """Map unit_id -> {"owner": seat, "node": node_id} from a prompt's VISIBLE
    UNITS block. A "(YOURS)" unit is owned by `me_seat`."""
    units: dict[int, dict] = {}
    for m in _VISIBLE_UNIT_RE.finditer(prompt_user or ""):
        uid = int(m.group(1))
        node = int(m.group(2))
        owner = int(m.group(3)) if m.group(3) is not None else me_seat
        units[uid] = {"owner": owner, "node": node}
    return units


def golf_occupied_nodes(visible_units: dict[int, dict], freerider_seats: set[int]) -> set[int]:
    """Nodes, among those visible, currently occupied by a freerider unit."""
    return {u["node"] for u in visible_units.values() if u["owner"] in freerider_seats}


def parse_scores(prompt_user: str) -> dict[int, float] | None:
    """The public per-seat cumulative `Scores` dict rendered in every negotiate
    prompt (unfogged -- identical across all seats' prompts the same turn).
    None if absent."""
    m = _SCORES_RE.search(prompt_user or "")
    if not m:
        return None
    out: dict[int, float] = {}
    for entry in m.group(1).strip("{}").split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        k, v = entry.split(":", 1)
        try:
            out[int(k.strip())] = float(v.strip())
        except ValueError:
            continue
    return out


def _is_require_dest_support(order: object) -> bool:
    return (
        isinstance(order, dict) and order.get("type") == "Support"
        and order.get("require_dest") is not None
    )


def count_require_dest_declarations(decisions_by_seat: dict[int, list[dict]]) -> dict[str, int]:
    """Corpus-wide sweep (freerider-agnostic, unlike the rest of this module)
    for how many Support orders anywhere in the LOGGED decisions used the
    `require_dest` pin variant: orders-phase submissions, negotiate-phase
    declared Intents, and negotiate-phase pact-proposal terms.

    M-foedus-s1-5-confound-check Check 3: every one of these three surfaces
    is routed through `foedus.agents.llm.parse.parse_order`'s legality gate
    (`parse_orders_response` for orders; `parse_intent`/`parse_pact_term` for
    negotiate) -- which never accepts a `require_dest` Support, regardless of
    geometry, because `foedus.legal.legal_orders_for_unit` never enumerates
    that variant as a candidate (see
    `foedus.eval.resolution_replay.geometric_legality`'s docstring). This is
    the TRUE denominator for "how many declared orders this bug silently
    discards" -- not just the subset that happened to target the freerider,
    which is all `classify_orders_execution`/`classify_negotiate_proposal`
    see.
    """
    counts = {"orders_phase": 0, "negotiate_intents": 0, "negotiate_pact_terms": 0}
    for records in decisions_by_seat.values():
        for rec in records:
            data = _extract(rec.get("raw_response") or "")
            if not isinstance(data, dict):
                continue
            if rec.get("phase") == "orders":
                orders = data.get("orders")
                if isinstance(orders, dict):
                    counts["orders_phase"] += sum(
                        1 for o in orders.values() if _is_require_dest_support(o)
                    )
            elif rec.get("phase") == "negotiate":
                press = data.get("press")
                if isinstance(press, dict):
                    for it in press.get("intents") or []:
                        if isinstance(it, dict) and _is_require_dest_support(it.get("declared_order")):
                            counts["negotiate_intents"] += 1
                pacts = data.get("pacts")
                if isinstance(pacts, dict):
                    for prop in pacts.get("propose") or []:
                        if not isinstance(prop, dict):
                            continue
                        for term in prop.get("terms") or []:
                            if isinstance(term, dict) and _is_require_dest_support(term.get("declared_order")):
                                counts["negotiate_pact_terms"] += 1
    return counts


def classify_negotiate_proposal(
    raw_response: str, freerider_seats: set[int], golf_nodes: set[int]
) -> dict:
    """Classify one seat's negotiate-phase raw_response for punishment
    proposals against the freerider.

    Returns:
        hostile_toward_freerider: bool -- declared HOSTILE stance toward any
            freerider seat this turn.
        attack_move_units: list[int] -- this seat's own unit ids whose
            declared intent is a Move onto a freerider-occupied node.
        support_intents: list[(unit_id, target_unit_id)] -- declared Support
            intents, for the caller to cross-reference against other seats'
            attacking units (coordination need not be visible within one
            seat's own press).
        attack_pact_proposals: list[dict] -- pact proposals (to a non-
            freerider counterparty) containing at least one attack-move term;
            each entry flags `coordinated` when the SAME proposal also
            contains a Support term targeting the attacking unit.
    """
    empty = {
        "hostile_toward_freerider": False,
        "attack_move_units": [],
        "support_intents": [],
        "attack_pact_proposals": [],
    }
    data = _extract(raw_response)
    if not isinstance(data, dict):
        return empty

    hostile = False
    attack_move_units: list[int] = []
    support_intents: list[tuple[int, int]] = []

    press = data.get("press")
    if isinstance(press, dict):
        stance = press.get("stance")
        if isinstance(stance, dict):
            for k, v in stance.items():
                if coerce_id(k) in freerider_seats and v == "hostile":
                    hostile = True
        for intent in press.get("intents") or []:
            if not isinstance(intent, dict):
                continue
            uid = coerce_id(intent.get("unit_id"))
            order = intent.get("declared_order")
            if uid is None or not isinstance(order, dict):
                continue
            if order.get("type") == "Move" and coerce_id(order.get("dest")) in golf_nodes:
                attack_move_units.append(uid)
            elif order.get("type") == "Support":
                target = coerce_id(order.get("target"))
                if target is not None:
                    support_intents.append((uid, target))

    attack_pact_proposals = []
    pacts = data.get("pacts")
    if isinstance(pacts, dict):
        for prop in pacts.get("propose") or []:
            if not isinstance(prop, dict):
                continue
            counterparty = coerce_id(prop.get("counterparty"))
            if counterparty in freerider_seats:
                continue  # a pact WITH the freerider isn't coordination against it
            move_units: set[int] = set()
            support_targets: set[int] = set()
            for term in prop.get("terms") or []:
                if not isinstance(term, dict):
                    continue
                order = term.get("declared_order")
                uid = coerce_id(term.get("unit_id"))
                if uid is None or not isinstance(order, dict):
                    continue
                if order.get("type") == "Move" and coerce_id(order.get("dest")) in golf_nodes:
                    move_units.add(uid)
                elif order.get("type") == "Support":
                    target = coerce_id(order.get("target"))
                    if target is not None:
                        support_targets.add(target)
            if move_units:
                attack_pact_proposals.append({
                    "counterparty": counterparty,
                    "attacking_units": sorted(move_units),
                    "coordinated": bool(move_units & support_targets),
                })

    return {
        "hostile_toward_freerider": hostile,
        "attack_move_units": attack_move_units,
        "support_intents": support_intents,
        "attack_pact_proposals": attack_pact_proposals,
    }


def classify_orders_execution(raw_response: str, golf_nodes: set[int]) -> dict:
    """Classify one seat's orders-phase raw_response.

    Returns:
        attack_moves: list[int] -- unit ids submitting a Move onto a
            freerider-occupied node (per the ACTING seat's own view).
        supports: list[(unit_id, target_unit_id)] -- all submitted Support
            orders, for the caller to cross-reference against every seat's
            attack_moves this turn (the supporter need not itself see the
            freerider to be supporting an attack on it).
    """
    empty = {"attack_moves": [], "supports": []}
    data = _extract(raw_response)
    if not isinstance(data, dict):
        return empty
    orders = data.get("orders")
    if not isinstance(orders, dict):
        return empty

    attack_moves: list[int] = []
    supports: list[tuple[int, int]] = []
    for uid_raw, order in orders.items():
        if not isinstance(order, dict):
            continue
        uid = coerce_id(uid_raw)
        if uid is None:
            continue
        if order.get("type") == "Move" and coerce_id(order.get("dest")) in golf_nodes:
            attack_moves.append(uid)
        elif order.get("type") == "Support":
            target = coerce_id(order.get("target"))
            if target is not None:
                supports.append((uid, target))
    return {"attack_moves": attack_moves, "supports": supports}


def income_series(scores_by_turn: dict[int, dict[int, float]], freerider_seat: int) -> dict[int, float]:
    """turn -> the freerider's income realized ENTERING that turn (its public
    cumulative score at `turn` minus at `turn - 1`, using only turns where
    both are observed)."""
    turns = sorted(scores_by_turn)
    out: dict[int, float] = {}
    prev_turn = prev_val = None
    for t in turns:
        cur = scores_by_turn[t].get(freerider_seat)
        if cur is not None:
            if prev_val is not None and t == prev_turn + 1:
                out[t] = cur - prev_val
            prev_turn, prev_val = t, cur
        # a turn with no observation neither extends nor breaks the chain
        # strictly -- but conservatively, only compute deltas across turns we
        # actually saw and that are adjacent (t == prev_turn + 1); anything
        # else simply yields no delta for that turn (see test coverage).
    return out


def income_drop_turns(series: dict[int, float]) -> list[int]:
    """Turns where the freerider's income DECREASED relative to the prior
    recorded income -- a center was captured away from it."""
    turns = sorted(series)
    drops = []
    prev = None
    for t in turns:
        v = series[t]
        if prev is not None and v < prev - 1e-9:
            drops.append(t)
        prev = v
    return drops


def match_paid_execution_turns(
    drop_turns: list[int], exec_turns: list[int]
) -> tuple[set[int], set[int]]:
    """Pair each income-drop turn with the LATEST qualifying execution turn
    (an execution 1-2 turns before the drop). Returns (paid_drop_turns,
    paid_execution_turns).

    Each DROP is credited to at most one execution turn (the latest
    qualifying one), not the other way around -- otherwise a single capture
    with two nearby execution turns in its window would be double-counted as
    two "paid" events. Shared by `classify_game_punishment` (the full
    executed set) and `clean_call_subset` (M-foedus-s1-5-confound-check's
    Check 2, the same pairing rule re-applied to a turn-filtered subset).
    """
    paid_drop_turns: set[int] = set()
    paid_turns: set[int] = set()
    for dt in drop_turns:
        candidates = [et for et in exec_turns if dt in (et + 1, et + 2)]
        if not candidates:
            continue
        paid_drop_turns.add(dt)
        paid_turns.add(max(candidates))
    return paid_drop_turns, paid_turns


def fell_back_by_seat_turn(decisions_by_seat: dict[int, list[dict]]) -> dict[tuple[int, int], bool]:
    """(seat, turn) -> True if EITHER that seat's negotiate OR orders call
    that turn fell back (client error / timeout / parse-fail -- the
    `fell_back` flag `LLMDiplomat._log` already records per decision). A
    (seat, turn) with no logged phase at all is simply absent."""
    out: dict[tuple[int, int], bool] = {}
    for seat, records in decisions_by_seat.items():
        for rec in records:
            key = (seat, rec["turn"])
            out[key] = out.get(key, False) or bool(rec.get("fell_back"))
    return out


def client_error_by_seat_turn(decisions_by_seat: dict[int, list[dict]]) -> dict[tuple[int, int], bool]:
    """(seat, turn) -> True only if a negotiate/orders call that turn was a
    genuine transport failure (`raw_response` literally the `<client error:
    ...>` fallback string LLMDiplomat._complete logs on a timeout/exception --
    see LLMDiplomat._complete). Narrower than `fell_back_by_seat_turn`: the
    corpus's `fell_back` flag ALSO covers a call that succeeded but needed
    the label sanitizer to recover otherwise-malformed JSON (e.g. a stray
    "7$1" node label copied from the prompt -- see
    foedus.agents.llm.parse._sanitize_node_labels), which is a parse-quality
    signal, not a reliability failure. `clean_call_subset` accepts either
    lookup, so pass this one for a stricter "genuinely broken call" cut of
    Check 2 alongside the broader `fell_back_by_seat_turn` one."""
    out: dict[tuple[int, int], bool] = {}
    for seat, records in decisions_by_seat.items():
        for rec in records:
            key = (seat, rec["turn"])
            is_client_error = (rec.get("raw_response") or "").startswith("<client error")
            out[key] = out.get(key, False) or is_client_error
    return out


def clean_call_subset(report: dict, fell_back: dict[tuple[int, int], bool]) -> dict:
    """Restrict a `classify_game_punishment` report to "clean-call"
    attack-turns (M-foedus-s1-5-confound-check Check 2 -- see
    docs/research/2026-07-04-canonical-campaign-v1/autopsy-s1-5-confounds.md):
    a turn is clean only if EVERY seat that appears in one of that turn's
    execution entries (mover or supporter) had NO negotiate/orders fallback
    (client error / timeout / parse-fail) that same turn.

    Restricts EXECUTED (and re-derives PAID from the restricted set);
    `proposed_count` is deliberately not restricted here -- Check 2 isolates
    whether infra failures explain the executed-but-unpaid gap, which is
    about what reached the engine, not what was declared in press.
    """
    turns_seats: dict[int, set[int]] = {}
    for e in report["executions"]:
        turns_seats.setdefault(e["game_turn"], set()).add(e["seat"])

    clean_turns = {
        turn for turn, seats in turns_seats.items()
        if not any(fell_back.get((seat, turn), False) for seat in seats)
    }
    dirty_turns = sorted(set(turns_seats) - clean_turns)
    clean_executions = [e for e in report["executions"] if e["game_turn"] in clean_turns]
    exec_turns = sorted(clean_turns)
    paid_drop_turns, paid_turns = match_paid_execution_turns(
        report["golf_income_drop_turns"], exec_turns)

    return {
        "executed_count": len(clean_executions),
        "paid_count": len(paid_drop_turns),
        "executions": clean_executions,
        "paid_execution_turns": sorted(paid_turns),
        "dirty_turns_excluded": dirty_turns,
    }


def pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r between two equal-length numeric series. None if undefined:
    fewer than 2 points, mismatched lengths, or zero variance in either
    series (a flat series has no correlation direction to report)."""
    n = len(xs)
    if n != len(ys) or n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def classify_game_punishment(
    decisions_by_seat: dict[int, list[dict]],
    llm_seats: list[int],
    freerider_seats: set[int],
) -> dict:
    """Classify one game's full punishment lifecycle: proposed -> executed ->
    paid, cross-referencing across seats and turns.

    `decisions_by_seat[seat]` is that seat's raw decision-log records (as
    written to `decisions_game{g}_seat{s}.jsonl`): each a dict with `turn`,
    `phase` ("negotiate" | "orders"), `prompt` (with a `.user` string), and
    `raw_response`.
    """
    proposals: list[dict] = []
    executions: list[dict] = []
    scores_by_turn: dict[int, dict[int, float]] = {}

    # -- negotiate phase: proposals (per seat, using that seat's own view) --
    # a first pass collects each turn's declared attack-move units and
    # declared support-intents; a second pass then flags a support-intent
    # whose target is ANY seat's declared attack-move unit that turn as an
    # "attack_support_intent" proposal -- a concrete (if informal, non-pact)
    # coordination signal, symmetric with how executed Supports are
    # cross-referenced against executed attack Moves below.
    by_turn_negotiate: dict[int, list[dict]] = {}
    for seat in llm_seats:
        for rec in decisions_by_seat.get(seat, []):
            if rec.get("phase") != "negotiate":
                continue
            turn = rec.get("turn")
            prompt_user = (rec.get("prompt") or {}).get("user", "")
            scores = parse_scores(prompt_user)
            if scores is not None:
                scores_by_turn.setdefault(turn, {}).update(scores)
            visible = parse_visible_units(prompt_user, seat)
            golf_nodes = golf_occupied_nodes(visible, freerider_seats)
            cls = classify_negotiate_proposal(
                rec.get("raw_response", ""), freerider_seats, golf_nodes)
            by_turn_negotiate.setdefault(turn, []).append({"seat": seat, **cls})

    for turn, per_seat in by_turn_negotiate.items():
        attack_move_units: set[int] = set()
        for entry in per_seat:
            for uid in entry["attack_move_units"]:
                attack_move_units.add(uid)
                proposals.append({
                    "kind": "attack_move_intent", "game_turn": turn, "seat": entry["seat"],
                    "unit_id": uid,
                })
            for prop in entry["attack_pact_proposals"]:
                proposals.append({
                    "kind": "attack_pact_proposal", "game_turn": turn, "seat": entry["seat"],
                    "counterparty": prop["counterparty"],
                    "attacking_units": prop["attacking_units"],
                    "coordinated": prop["coordinated"],
                })
        for entry in per_seat:
            for uid, target in entry["support_intents"]:
                if target in attack_move_units:
                    proposals.append({
                        "kind": "attack_support_intent", "game_turn": turn,
                        "seat": entry["seat"], "unit_id": uid, "target_unit_id": target,
                    })

    # -- orders phase: executions, cross-referenced within each turn --------
    by_turn_orders: dict[int, dict[int, dict]] = {}
    for seat in llm_seats:
        for rec in decisions_by_seat.get(seat, []):
            if rec.get("phase") != "orders":
                continue
            turn = rec.get("turn")
            prompt_user = (rec.get("prompt") or {}).get("user", "")
            visible = parse_visible_units(prompt_user, seat)
            golf_nodes = golf_occupied_nodes(visible, freerider_seats)
            cls = classify_orders_execution(rec.get("raw_response", ""), golf_nodes)
            by_turn_orders.setdefault(turn, {})[seat] = cls

    for turn, per_seat in by_turn_orders.items():
        attacking_units: set[int] = set()
        for seat, cls in per_seat.items():
            for uid in cls["attack_moves"]:
                attacking_units.add(uid)
                executions.append({
                    "kind": "attack_move", "game_turn": turn, "seat": seat, "unit_id": uid,
                })
        for seat, cls in per_seat.items():
            for uid, target in cls["supports"]:
                if target in attacking_units:
                    executions.append({
                        "kind": "attack_support", "game_turn": turn, "seat": seat,
                        "unit_id": uid, "target_unit_id": target,
                    })

    # -- direct linkage: did a declared attack-move intent actually convert
    # into that SAME (seat, turn, unit) executing an attack-move, rather than
    # inferring conversion from aggregate proposed/executed totals alone? ---
    declared_attack_moves = {
        (p["seat"], p["game_turn"], p["unit_id"])
        for p in proposals if p["kind"] == "attack_move_intent"
    }
    executed_attack_moves = {
        (e["seat"], e["game_turn"], e["unit_id"])
        for e in executions if e["kind"] == "attack_move"
    }
    attack_move_intents_matched = declared_attack_moves & executed_attack_moves

    # -- paid: did the freerider's income drop after an execution? ----------
    freerider_seat = next(iter(sorted(freerider_seats)), None)
    drop_turns: list[int] = []
    if freerider_seat is not None and scores_by_turn:
        drop_turns = income_drop_turns(income_series(scores_by_turn, freerider_seat))
    exec_turns = sorted({e["game_turn"] for e in executions})
    paid_drop_turns, paid_turns = match_paid_execution_turns(drop_turns, exec_turns)

    return {
        "proposed_count": len(proposals),
        "executed_count": len(executions),
        "paid_count": len(paid_drop_turns),
        "proposals": proposals,
        "executions": executions,
        "golf_income_drop_turns": drop_turns,
        "paid_execution_turns": sorted(paid_turns),
        "attack_move_intents_total": len(declared_attack_moves),
        "attack_move_intents_matched_by_execution": len(attack_move_intents_matched),
    }
