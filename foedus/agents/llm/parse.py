"""Robust JSON extraction + order/press/pact parsing for LLM output.

LLM responses are untrusted free text: they may wrap JSON in prose or
markdown fences, use string ids where ints are expected (or prefix them,
e.g. "u2" for unit 2), or omit required fields. Every parse function here
degrades to a safe fallback (Hold orders / empty press) instead of
raising -- callers get back a `fell_back` flag (and an `n_coerced`
count) so parse quality is a measured metric, never a silent failure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from foedus.core import (
    GameState,
    Hold,
    Intent,
    Move,
    Order,
    PactProposal,
    PactTerm,
    PlayerId,
    Press,
    Stance,
    Support,
    UnitId,
)
from foedus.legal import legal_orders_for_unit

_ID_RE = re.compile(r"^[a-zA-Z]?(\d+)$")


def _as_list(raw: object) -> list:
    """Coerce an optional-list JSON field to a Python list.

    An LLM may emit a non-list truthy value ("propose": 42, "accept":
    true) where a list is expected -- `raw or []` would then try to
    iterate that scalar and crash. Only a real list (or None/missing,
    which map to "no entries") is accepted; anything else is treated
    as absent.
    """
    return raw if isinstance(raw, list) else []


def coerce_id(raw: object) -> int | None:
    """Coerce a possibly letter-prefixed id ("u2", "p1", "2", 2) to an int.

    LLMs commonly prefix ids with a letter matching the domain noun
    (unit "u2", player "p1"). Accepts a bare digit string or a real int
    too. Returns None if `raw` can't be read as an id (including bools,
    which are technically `int` in Python but never a valid id here).
    A degenerate model output (e.g. a repetition-loop id thousands of
    digits long) hits CPython's int-string conversion length guard
    (ValueError) -- caught here rather than left to crash the caller.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if not isinstance(raw, str):
        return None
    m = _ID_RE.match(raw.strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _try_json(candidate: str):
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_json_stages(text: str, *, sanitize: bool = False) -> tuple[object, bool]:
    """The parse attempts shared by `extract_json` and
    `extract_json_with_recovery`: the whole text as-is; the first fenced
    code block; the first balanced top-level `{...}` substring
    (brace-depth scan that ignores braces inside string literals).

    `sanitize=True` retries each of those three candidates through
    `_sanitize_node_labels` before moving on to the next one -- e.g. if
    the whole-text candidate fails only because of a stray `7$1`/`2H`/`u5`
    token, it's repaired and re-parsed *before* the balanced-brace scan
    would otherwise wander into a smaller, spuriously-valid inner
    substring (a nested `{"type": "Hold"}` two levels down, say) and
    silently return the wrong object.

    Returns `(data, used_sanitizer)`; `data` is None if nothing parses.
    """
    def parse_candidate(candidate: str):
        data = _try_json(candidate)
        if data is not None:
            return data, False
        if sanitize:
            sanitized = _sanitize_node_labels(candidate)
            if sanitized != candidate:
                data = _try_json(sanitized)
                if data is not None:
                    return data, True
        return None, False

    data, used = parse_candidate(text)
    if data is not None:
        return data, used

    m = _FENCE_RE.search(text)
    if m:
        data, used = parse_candidate(m.group(1).strip())
        if data is not None:
            return data, used

    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    data, used = parse_candidate(candidate)
                    if data is not None:
                        return data, used
                    break
        start = text.find("{", start + 1)
    return None, False


def extract_json(text: str):
    """Extract and parse the first JSON object found in `text`.

    Tries, in order: the whole text as-is; the first fenced code block;
    the first balanced top-level `{...}` substring. Returns None if
    nothing parses. See `extract_json_with_recovery` for a variant that
    also recovers node/unit labels copied verbatim from the prompt.
    """
    data, _ = _extract_json_stages(text.strip())
    return data


_NODE_LABEL_RE = re.compile(r"(\d+)\$\d+|(\d+)H\b|\bu(\d+)\b")


def _sanitize_node_labels(text: str) -> str:
    """Rewrite value-annotated node/unit labels (7$1, 2H, u5) copied
    verbatim from the prompt's human-readable map/legal-orders text into
    JSON values, back to their bare integer id -- e.g. `"dest": 7$1` ->
    `"dest": 7`, `"unit_id": 2H` -> `"unit_id": 2`, `"target": u5` ->
    `"target": 5`. These are otherwise invalid JSON tokens that abort
    `json.loads` entirely (diagnosed root cause of ~42% of LLMDiplomat
    parse failures).

    Scans outside string literals only (mirrors the brace-depth scan in
    `_extract_json_stages`), so legitimate quoted string content (e.g. a
    stance rationale mentioning "7$1") is never touched.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    esc = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        m = _NODE_LABEL_RE.match(text, i)
        if m:
            out.append(m.group(1) or m.group(2) or m.group(3))
            i = m.end()
            continue
        out.append(c)
        i += 1
    return "".join(out)


def extract_json_with_recovery(text: str) -> tuple[object, bool]:
    """`extract_json`, plus a sanitizer-fallback retry.

    If a candidate doesn't parse as-is, retries after rewriting
    model-copied node/unit labels that are invalid JSON tokens (see
    `_sanitize_node_labels`). Returns `(data, used_fallback)` so callers
    can count sanitizer use as a parse-quality signal even when it
    successfully recovers a decision -- per this module's contract, parse
    quality is measured, never silently fixed.
    """
    return _extract_json_stages(text.strip(), sanitize=True)


def parse_order(d: object, legal: list[Order]) -> tuple[Order, bool]:
    """Parse one order dict, legality-gated against `legal`.

    Returns (order, was_legal). An unparseable or geometrically illegal
    order coerces to Hold() with was_legal=False -- the engine already
    normalizes illegal orders silently, but coercing here lets the
    caller report it instead of the failure vanishing at finalize time.
    """
    if not isinstance(d, dict):
        return Hold(), False
    t = d.get("type")
    order: Order | None = None
    if t == "Hold":
        order = Hold()
    elif t == "Move":
        dest = coerce_id(d.get("dest"))
        if dest is not None:
            order = Move(dest=dest)
    elif t == "Support":
        target = coerce_id(d.get("target"))
        if target is not None:
            require_dest_raw = d.get("require_dest")
            if require_dest_raw is None:
                order = Support(target=target)
            else:
                require_dest = coerce_id(require_dest_raw)
                if require_dest is not None:
                    order = Support(target=target, require_dest=require_dest)
    if order is None or order not in legal:
        return Hold(), False
    return order, True


def parse_stance(d: object) -> dict[PlayerId, Stance]:
    out: dict[PlayerId, Stance] = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        pid = coerce_id(k)
        if pid is None:
            continue
        try:
            out[pid] = Stance(v)
        except ValueError:
            continue
    return out


def parse_intent(d: object, state: GameState, player: PlayerId) -> Intent | None:
    if not isinstance(d, dict):
        return None
    unit_id = coerce_id(d.get("unit_id"))
    if unit_id is None:
        return None
    unit = state.units.get(unit_id)
    if unit is None or unit.owner != player:
        return None
    order, _ = parse_order(
        d.get("declared_order"), legal_orders_for_unit(state, unit_id)
    )
    vt_raw = d.get("visible_to")
    if vt_raw is None:
        visible_to: frozenset[PlayerId] | None = None
    elif isinstance(vt_raw, list):
        ids = [coerce_id(x) for x in vt_raw]
        visible_to = frozenset(i for i in ids if i is not None)
    else:
        return None
    return Intent(unit_id=unit_id, declared_order=order, visible_to=visible_to)


def parse_pact_term(d: object, state: GameState) -> PactTerm | None:
    if not isinstance(d, dict):
        return None
    player = coerce_id(d.get("player"))
    unit_id = coerce_id(d.get("unit_id"))
    if player is None or unit_id is None:
        return None
    unit = state.units.get(unit_id)
    if unit is None or unit.owner != player:
        return None
    order, _ = parse_order(
        d.get("declared_order"), legal_orders_for_unit(state, unit_id)
    )
    return PactTerm(player=player, unit_id=unit_id, declared_order=order)


@dataclass
class NegotiationDecision:
    """Parsed result of one negotiation-phase LLM call.

    Shared by choose_press/choose_pacts/accept_pacts -- they all read
    the same fogged view at negotiate time, so one call answers all
    three (see LLMDiplomat._negotiate).
    """
    press: Press
    proposals: list[PactProposal] = field(default_factory=list)
    accept_ids: list[int] = field(default_factory=list)
    fell_back: bool = False
    n_coerced: int = 0


def parse_negotiation_response(
    raw: str, state: GameState, player: PlayerId
) -> NegotiationDecision:
    data, used_sanitizer = extract_json_with_recovery(raw)
    if not isinstance(data, dict):
        return NegotiationDecision(Press(stance={}, intents=[]), fell_back=True)

    fell_back = used_sanitizer
    n_coerced = 1 if used_sanitizer else 0

    press_raw = data.get("press")
    if press_raw is None:
        press_raw = {}
    elif not isinstance(press_raw, dict):
        press_raw = {}
        fell_back = True
        n_coerced += 1

    stance = parse_stance(press_raw.get("stance"))
    intents_raw = press_raw.get("intents")
    if intents_raw is not None and not isinstance(intents_raw, list):
        fell_back = True
        n_coerced += 1
    intents: list[Intent] = []
    for it_raw in _as_list(intents_raw):
        parsed = parse_intent(it_raw, state, player)
        if parsed is not None:
            intents.append(parsed)
        else:
            fell_back = True
            n_coerced += 1
    press = Press(stance=stance, intents=intents)

    pacts_raw = data.get("pacts")
    proposals: list[PactProposal] = []
    accept_ids: list[int] = []
    if pacts_raw is None:
        pacts_raw = {}
    if isinstance(pacts_raw, dict):
        propose_raw = pacts_raw.get("propose")
        if propose_raw is not None and not isinstance(propose_raw, list):
            fell_back = True
            n_coerced += 1
        for prop_raw in _as_list(propose_raw):
            if not isinstance(prop_raw, dict):
                fell_back = True
                n_coerced += 1
                continue
            counterparty = coerce_id(prop_raw.get("counterparty"))
            if counterparty is None:
                fell_back = True
                n_coerced += 1
                continue
            terms_raw = prop_raw.get("terms")
            if terms_raw is not None and not isinstance(terms_raw, list):
                fell_back = True
                n_coerced += 1
            terms: list[PactTerm] = []
            for t_raw in _as_list(terms_raw):
                term = parse_pact_term(t_raw, state)
                if term is not None:
                    terms.append(term)
                else:
                    fell_back = True
                    n_coerced += 1
            if terms:
                proposals.append(
                    PactProposal(counterparty=counterparty, terms=tuple(terms))
                )
            else:
                fell_back = True
                n_coerced += 1
        accept_raw = pacts_raw.get("accept")
        if accept_raw is not None and not isinstance(accept_raw, list):
            fell_back = True
            n_coerced += 1
        for pid_raw in _as_list(accept_raw):
            pid = coerce_id(pid_raw)
            if pid is not None:
                accept_ids.append(pid)
            else:
                fell_back = True
                n_coerced += 1
    else:
        fell_back = True
        n_coerced += 1

    return NegotiationDecision(
        press, proposals, accept_ids, fell_back=fell_back, n_coerced=n_coerced
    )


def parse_orders_response(
    raw: str, state: GameState, player: PlayerId
) -> tuple[dict[UnitId, Order], bool, int]:
    """Returns (orders, fell_back, n_coerced). Any owned unit missing from
    the response defaults to Hold WITHOUT counting as a fallback -- that's
    documented client shorthand (see foedus_press_play.py's apply_commit),
    not a parse failure.
    """
    own_units = [u for u in state.units.values() if u.owner == player]
    data, used_sanitizer = extract_json_with_recovery(raw)
    fell_back = used_sanitizer
    n_coerced = 1 if used_sanitizer else 0

    orders_raw = None
    if isinstance(data, dict):
        orders_raw = data.get("orders")
    else:
        fell_back = True
        n_coerced += 1

    if orders_raw is None:
        orders_raw = {}
    elif not isinstance(orders_raw, dict):
        orders_raw = {}
        fell_back = True
        n_coerced += 1

    parsed: dict[UnitId, Order] = {}
    for uid_key, od in orders_raw.items():
        uid = coerce_id(uid_key)
        if uid is None:
            fell_back = True
            n_coerced += 1
            continue
        unit = state.units.get(uid)
        if unit is None or unit.owner != player:
            fell_back = True
            n_coerced += 1
            continue
        legal = legal_orders_for_unit(state, uid)
        order, was_legal = parse_order(od, legal)
        if not was_legal:
            fell_back = True
            n_coerced += 1
        parsed[uid] = order

    for u in own_units:
        if u.id not in parsed:
            parsed[u.id] = Hold()

    return parsed, fell_back, n_coerced
