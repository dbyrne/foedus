"""Read-only loaders over a campaign run-dir.

Every function tolerates missing/empty files: the run dir this reads from is
UNTOUCHABLE and may be observed mid-flight (a fresh campaign has empty
sweep.jsonl/telemetry.jsonl and zero decision logs until its first game
finishes). Nothing here ever writes into the run dir.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_TIMING_START_RE = re.compile(r"^CAMPAIGN START: (\S+)")
_TIMING_END_RE = re.compile(r"^CAMPAIGN END: (\S+) rc=(-?\d+) elapsed=([\d.]+)")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_campaign_plan(run_dir: str | Path) -> dict | None:
    return _load_json(Path(run_dir) / "campaign_plan.json")


def load_seed_manifest(run_dir: str | Path) -> dict | None:
    return _load_json(Path(run_dir) / "seed_manifest.sealed.json")


def load_sweep(run_dir: str | Path) -> list[dict]:
    return _load_jsonl(Path(run_dir) / "sweep.jsonl")


def load_telemetry(run_dir: str | Path) -> list[dict]:
    return _load_jsonl(Path(run_dir) / "telemetry.jsonl")


def load_spectate_stream(run_dir: str | Path, game_id: int) -> list[dict]:
    """The opt-in live per-turn stream (see foedus/spectate/emit.py), if a
    harness run had FOEDUS_SPECTATE_DIR pointed at this run_dir. Empty for
    any game that either finished normally (no live stream needed) or was
    never run with the emitter enabled."""
    return _load_jsonl(Path(run_dir) / f"spectate_game{game_id}.jsonl")


def seating_for_game(plan: dict | None, game_index: int) -> dict:
    """The campaign_plan.json seating entry for one game_index, or {} if the
    plan is absent or has no matching entry (e.g. a non-campaign run)."""
    for seating in (plan or {}).get("seatings") or []:
        if seating.get("game_index") == game_index:
            return seating
    return {}


def load_timing(run_dir: str | Path) -> dict:
    result = {"started_at": None, "ended_at": None, "rc": None, "elapsed_s": None}
    path = Path(run_dir) / "timing.log"
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        m = _TIMING_START_RE.match(line)
        if m:
            result["started_at"] = m.group(1)
            continue
        m = _TIMING_END_RE.match(line)
        if m:
            result["ended_at"] = m.group(1)
            result["rc"] = int(m.group(2))
            result["elapsed_s"] = float(m.group(3))
    return result


def load_decisions(
    run_dir: str | Path, game_id: int, llm_seats: list[int]
) -> dict[int, list[dict]]:
    """Per-seat decision logs, tolerating both the multi-seat
    (decisions_game{g}_seat{s}.jsonl) and single-seat
    (decisions_game{g}.jsonl) naming the harness uses."""
    out = Path(run_dir)
    by_seat: dict[int, list[dict]] = {}
    for seat in llm_seats:
        multi = out / f"decisions_game{game_id}_seat{seat}.jsonl"
        single = out / f"decisions_game{game_id}.jsonl"
        if multi.exists():
            by_seat[seat] = _load_jsonl(multi)
        elif single.exists() and len(llm_seats) == 1:
            by_seat[seat] = _load_jsonl(single)
        else:
            by_seat[seat] = []
    return by_seat


def load_self_notes(run_dir: str | Path) -> list[dict]:
    """Verbatim self-notes from every campaign_memory_game{g}_seat{s}.json
    found in the run dir, newest game first. Blank notes are omitted."""
    out = Path(run_dir)
    notes: list[dict] = []
    seen: set[tuple] = set()
    for path in sorted(out.glob("campaign_memory_game*_seat*.json")):
        payload = _load_json(path)
        if not payload:
            continue
        entrant_identity = payload.get("entrant_identity")
        seat = payload.get("seat")
        for record in payload.get("records") or []:
            self_note = (record.get("self_note") or "").strip()
            if not self_note:
                continue
            game_index = (record.get("facts") or {}).get("game_index", payload.get("game_index"))
            # Campaign-memory files are cumulative (a seat's file at game N
            # carries records for games 0..N), so the same (seat, game_index)
            # note reappears across multiple files -- dedupe.
            key = (seat, game_index)
            if key in seen:
                continue
            seen.add(key)
            notes.append({
                "game_index": game_index,
                "seat": seat,
                "entrant_identity": entrant_identity,
                "self_note": self_note,
            })
    notes.sort(key=lambda n: n["game_index"], reverse=True)
    return notes
