"""View 2: the per-game replay theater data model.

Merges transcript.py's per-turn stance/intent structures (all seats, when a
transcript_game{g}.md exists -- only the harness's `--transcripts` first N
games get one) with board.py's decision-log-derived orders/subsidy layer
(LLM seats only), plus that specific game's self-notes.
"""

from __future__ import annotations

from pathlib import Path

from foedus.spectate.board import build_turn_frames
from foedus.spectate.readers import load_decisions, load_self_notes, load_sweep


def build_replay(run_dir: str | Path, game_id: int) -> dict | None:
    run_dir = Path(run_dir)
    sweep_record = next(
        (r for r in load_sweep(run_dir) if r.get("game_id") == game_id), None
    )
    if sweep_record is None:
        return None

    identity_by_seat = sweep_record.get("identity_by_seat") or []
    freerider_seats = sweep_record.get("freerider_seats") or []
    llm_seats = sweep_record.get("llm_seats") or []
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
    turns: list[dict] = []
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

    for turn in turn_numbers:
        frame = order_frames.get(turn, {})
        turns.append({
            "turn": turn,
            "declarations": declarations_by_turn.get(turn, {}),
            "orders": frame.get("orders", {}),
            "fell_back": frame.get("fell_back", {}),
            "subsidy": frame.get("subsidy", 0),
            "llm_llm_supports": frame.get("llm_llm_supports", 0),
        })

    self_notes = [
        n for n in load_self_notes(run_dir)
        if n.get("game_index") == sweep_record.get("game_index")
    ]

    return {
        "game_id": game_id,
        "game_index": sweep_record.get("game_index"),
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
    }
