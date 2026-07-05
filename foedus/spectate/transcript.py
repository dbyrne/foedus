"""Parse transcript_game{g}.md (scripts/foedus_llm_diplomat_run.py's
render_transcript output) into a structured per-turn dict for the replay
theater (View 2). Regex-based against the fixed line formats render_transcript
emits -- see order_to_str (foedus/render_common.py) for the exact order-string
grammar this mirrors.
"""

from __future__ import annotations

import ast
import re

_ORDER_RE = re.compile(
    r"^(?:Hold|Move\(dest=(?P<move_dest>\d+)\)|"
    r"Support\(target=u(?P<support_target>\d+)"
    r"(?:, require_dest=(?P<require_dest>\d+))?\))$"
)

_STANCE_LINE_RE = re.compile(r"^- p(\d+) stance: (.+)$")
_STANCE_ENTRY_RE = re.compile(r"p(\d+)=(\w+)")
_INTENT_LINE_RE = re.compile(
    r"^  - declared u(\d+) -> (.+?) \(visible_to=(public|\[.*\])\)$"
)
_TURN_HEADER_RE = re.compile(r"^## Turn (\d+)$")
_BETRAYAL_RE = re.compile(
    r"^- turn (\d+): p(\d+) declared u(\d+) -> (.+?), actually (.+)$"
)
_PACT_BREACH_RE = re.compile(
    r"^- turn (\d+): p(\d+) broke pact #(\d+) "
    r"\(pledged u(\d+) -> (.+?), actually (.+?)\)$"
)
_REPUTATION_RE = re.compile(
    r"^- p(\d+): (\d+) intent / (\d+) pact / (\d+) total$"
)


def _parse_order(text: str) -> dict:
    m = _ORDER_RE.match(text.strip())
    if not m:
        raise ValueError(f"unrecognized order string: {text!r}")
    if text == "Hold":
        return {"type": "Hold"}
    if m.group("move_dest") is not None:
        return {"type": "Move", "dest": int(m.group("move_dest"))}
    order: dict = {"type": "Support", "target": int(m.group("support_target"))}
    require_dest = m.group("require_dest")
    order["require_dest"] = int(require_dest) if require_dest is not None else None
    return order


def _parse_stance(rest: str) -> dict[int, str]:
    if rest.strip() == "(none)":
        return {}
    return {int(pid): stance for pid, stance in _STANCE_ENTRY_RE.findall(rest)}


def _parse_visible_to(raw: str) -> list[int] | None:
    if raw == "public":
        return None
    return [int(x) for x in ast.literal_eval(raw)]


def parse_transcript(text: str) -> dict:
    """Parse a render_transcript() markdown document.

    Returns a dict with: final_scores (dict[int, float]), eliminated (list),
    winners (list), detente_reached (bool), turns (list of
    {"turn": int, "declarations": {seat: {"stance": {...}, "intents": [...]}}}),
    betrayals (list), pact_breaches (list), reputation (dict[int, dict]).
    """
    lines = text.splitlines()
    result: dict = {
        "final_scores": {},
        "eliminated": [],
        "winners": [],
        "detente_reached": False,
        "turns": [],
        "betrayals": [],
        "pact_breaches": [],
        "reputation": {},
    }

    section = None
    current_turn: dict | None = None
    current_seat: int | None = None

    for line in lines:
        if line.startswith("Final scores: "):
            raw = ast.literal_eval(line[len("Final scores: "):])
            result["final_scores"] = {int(k): v for k, v in raw.items()}
            continue
        if line.startswith("Eliminated: "):
            result["eliminated"] = ast.literal_eval(line[len("Eliminated: "):])
            continue
        if line.startswith("Winners: "):
            result["winners"] = ast.literal_eval(line[len("Winners: "):])
            continue
        if line.startswith("Détente reached: "):
            result["detente_reached"] = line[len("Détente reached: "):] == "True"
            continue

        m = _TURN_HEADER_RE.match(line)
        if m:
            current_turn = {"turn": int(m.group(1)), "declarations": {}}
            result["turns"].append(current_turn)
            section = "turn"
            current_seat = None
            continue

        if line == "## Betrayals observed":
            section = "betrayals"
            continue
        if line == "## Pact breaches observed":
            section = "pact_breaches"
            continue
        if line == "## Final reputation (public)":
            section = "reputation"
            continue

        if not line.strip() or line == "(none)":
            continue

        if section == "turn":
            m = _STANCE_LINE_RE.match(line)
            if m:
                current_seat = int(m.group(1))
                current_turn["declarations"][current_seat] = {
                    "stance": _parse_stance(m.group(2)),
                    "intents": [],
                }
                continue
            m = _INTENT_LINE_RE.match(line)
            if m and current_seat is not None:
                unit_id, order_str, visible_raw = m.groups()
                current_turn["declarations"][current_seat]["intents"].append({
                    "unit_id": int(unit_id),
                    "order": _parse_order(order_str),
                    "visible_to": _parse_visible_to(visible_raw),
                })
                continue
        elif section == "betrayals":
            m = _BETRAYAL_RE.match(line)
            if m:
                turn, betrayer, unit_id, declared, actual = m.groups()
                result["betrayals"].append({
                    "turn": int(turn),
                    "betrayer": int(betrayer),
                    "unit_id": int(unit_id),
                    "declared_order": _parse_order(declared),
                    "actual_order": _parse_order(actual),
                })
                continue
        elif section == "pact_breaches":
            m = _PACT_BREACH_RE.match(line)
            if m:
                turn, breacher, pact_id, unit_id, pledged, actual = m.groups()
                result["pact_breaches"].append({
                    "turn": int(turn),
                    "breacher": int(breacher),
                    "pact_id": int(pact_id),
                    "pledged_unit": int(unit_id),
                    "pledged_order": _parse_order(pledged),
                    "actual_order": _parse_order(actual),
                })
                continue
        elif section == "reputation":
            m = _REPUTATION_RE.match(line)
            if m:
                seat, ib, pb, tot = m.groups()
                result["reputation"][int(seat)] = {
                    "intent_breaches": int(ib),
                    "pact_breaches": int(pb),
                    "total": int(tot),
                }
                continue

    return result
