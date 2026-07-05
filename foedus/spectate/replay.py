"""View 2: the per-game replay theater data model.

For a FINISHED game, merges transcript.py's per-turn stance/intent structures
(all seats, when a transcript_game{g}.md exists -- only the harness's
`--transcripts` first N games get one) with board.py's decision-log-derived
orders/subsidy layer (LLM seats only), plus that specific game's self-notes.

For a game with no sweep record yet (still in flight), falls back to the
opt-in live spectate stream (foedus/spectate/emit.py) if one exists --
"the spectator server auto-upgrades to live turn-by-turn when the stream
exists". The stream is strictly richer for an in-progress game: it carries
real orders for EVERY seat (including the freerider/heuristic), not just the
LLM seats a decision log can see.
"""

from __future__ import annotations

from pathlib import Path

from foedus.spectate.board import build_turn_frames
from foedus.spectate.readers import (
    load_campaign_plan,
    load_decisions,
    load_self_notes,
    load_spectate_stream,
    load_sweep,
    seating_for_game,
)


def _seat_metadata(plan: dict | None, sweep_record: dict, game_index) -> tuple[list, list, list]:
    seating = seating_for_game(plan, game_index)
    identity_by_seat = seating.get("identity_by_seat") or sweep_record.get("identity_by_seat") or []
    freerider_seats = seating.get("freerider_seats") or sweep_record.get("freerider_seats") or []
    llm_seats = seating.get("llm_seats") or sweep_record.get("llm_seats") or []
    return identity_by_seat, freerider_seats, llm_seats


def _build_finished_replay(run_dir: Path, game_id: int, sweep_record: dict) -> dict:
    plan = load_campaign_plan(run_dir)
    game_index = sweep_record.get("game_index")
    identity_by_seat, freerider_seats, llm_seats = _seat_metadata(plan, sweep_record, game_index)
    final_scores_list = sweep_record.get("final_scores") or []

    decisions = load_decisions(run_dir, game_id, llm_seats)
    # Decision-log records are stamped with state.turn READ BEFORE
    # finalize_round increments it (0-indexed: 0 for the first turn), while
    # the transcript's turn labels and the engine's own turn-stamped events
    # (press.py's SupportRound etc, all `state.turn + 1`) are 1-indexed. +1
    # here aligns "declared this turn" with "ordered this turn".
    order_frames = {
        f["turn"] + 1: f for f in build_turn_frames(decisions, freerider_seats, llm_seats)
    }

    transcript_path = run_dir / f"transcript_game{game_id}.md"
    stance_available = transcript_path.exists()
    betrayals: list[dict] = []
    pact_breaches: list[dict] = []
    reputation: dict = {}

    if stance_available:
        from foedus.spectate.transcript import parse_transcript
        parsed = parse_transcript(transcript_path.read_text())
        betrayals = parsed["betrayals"]
        pact_breaches = parsed["pact_breaches"]
        reputation = parsed["reputation"]
        turn_numbers = sorted({t["turn"] for t in parsed["turns"]} | set(order_frames))
        declarations_by_turn = {t["turn"]: t["declarations"] for t in parsed["turns"]}
    else:
        turn_numbers = sorted(order_frames)
        declarations_by_turn = {}

    turns = []
    for turn in turn_numbers:
        frame = order_frames.get(turn, {})
        turns.append({
            "turn": turn,
            "declarations": declarations_by_turn.get(turn, {}),
            "orders": frame.get("orders", {}),
            "fell_back": frame.get("fell_back", {}),
            "subsidy": frame.get("subsidy", 0),
            "llm_llm_supports": frame.get("llm_llm_supports", 0),
            "support_targets": frame.get("support_targets", {}),
        })

    self_notes = [
        n for n in load_self_notes(run_dir) if n.get("game_index") == game_index
    ]

    return {
        "game_id": game_id,
        "game_index": game_index,
        "identity_by_seat": identity_by_seat,
        "freerider_seats": freerider_seats,
        "llm_seats": llm_seats,
        "final_scores": {i: s for i, s in enumerate(final_scores_list)},
        "eliminated": sweep_record.get("eliminated") or [],
        "winners": sweep_record.get("winners") or [],
        "detente_reached": sweep_record.get("detente_reached"),
        "stance_available": stance_available,
        "turns": turns,
        "betrayals": betrayals,
        "pact_breaches": pact_breaches,
        "reputation": reputation,
        "self_notes": self_notes,
        "live": False,
    }


def _live_declarations(rec: dict) -> dict[int, dict]:
    declarations: dict[int, dict] = {}
    for seat_str, stance in (rec.get("stances") or {}).items():
        seat = int(seat_str)
        declarations.setdefault(seat, {"stance": {}, "intents": []})
        declarations[seat]["stance"] = {int(k): v for k, v in stance.items()}
    for seat_str, intents in (rec.get("intents") or {}).items():
        seat = int(seat_str)
        declarations.setdefault(seat, {"stance": {}, "intents": []})
        declarations[seat]["intents"] = [
            {
                "unit_id": it["unit_id"],
                "order": it["declared_order"],
                "visible_to": it["visible_to"],
            }
            for it in intents
        ]
    return declarations


def _build_live_replay(run_dir: Path, game_id: int) -> dict | None:
    stream = load_spectate_stream(run_dir, game_id)
    if not stream:
        return None

    plan = load_campaign_plan(run_dir)
    seating = seating_for_game(plan, game_id)
    identity_by_seat = seating.get("identity_by_seat") or []
    freerider_seats = seating.get("freerider_seats") or []
    llm_seats = seating.get("llm_seats") or []

    turns = []
    for rec in stream:
        turns.append({
            "turn": rec["turn"],
            "declarations": _live_declarations(rec),
            "orders": {int(seat_str): orders for seat_str, orders in (rec.get("orders") or {}).items()},
            "fell_back": {},
            "subsidy": 0,
            "llm_llm_supports": 0,
            "support_targets": {},
        })

    last = stream[-1]
    final_scores = {int(k): v for k, v in (last.get("scores") or {}).items()}

    return {
        "game_id": game_id,
        "game_index": game_id,
        "identity_by_seat": identity_by_seat,
        "freerider_seats": freerider_seats,
        "llm_seats": llm_seats,
        "final_scores": final_scores,
        "eliminated": last.get("eliminated") or [],
        "winners": [],
        "detente_reached": None,
        "stance_available": True,
        "turns": turns,
        "betrayals": [],
        "pact_breaches": [],
        "reputation": {},
        "self_notes": [
            n for n in load_self_notes(run_dir) if n.get("game_index") == game_id
        ],
        "live": True,
    }


def build_replay(run_dir: str | Path, game_id: int) -> dict | None:
    run_dir = Path(run_dir)
    sweep_record = next(
        (r for r in load_sweep(run_dir) if r.get("game_id") == game_id), None
    )
    if sweep_record is not None:
        return _build_finished_replay(run_dir, game_id, sweep_record)
    return _build_live_replay(run_dir, game_id)
