"""Scorecard extractor for the reciprocation-memory experiment.

Reads a run out-dir (as written by scripts/foedus_llm_diplomat_run.py) and
produces a per-game + aggregate scorecard measuring whether an LLM table
resists a scripted freerider:

  * margin / winner — freerider final score vs. the mean LLM score.
  * subsidy — LLM `Support` orders whose target is a freerider unit (the LLM
    table spending its own actions to help the freerider).
  * stance-toward-freerider trajectory — per turn, how many LLM seats declared
    the freerider ally / neutral / hostile (does suspicion HOLD?).
  * per-seat parse-fail — from existing telemetry.

Everything is derived from self-contained JSON the harness already emits: each
decision's `raw_response` (the model's own JSON, parsed with the diplomat's own
extractor — no game state needed for stance/target ids) and its prompt (for unit
ownership), plus the sweep/telemetry records. So the extractor is decoupled from
the engine and testable against scripted records.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from foedus.agents.llm.parse import coerce_id, extract_json_with_recovery

_VISIBLE_UNIT_RE = re.compile(
    r"u(\d+) at node \d+ \((?:player (\d+)|YOURS)\)"
)


def _extract(raw: str):
    """Parse a decision's raw_response the same way the diplomat does; None if
    it isn't JSON (e.g. a `<client error: ...>` fallback record)."""
    try:
        data, _ = extract_json_with_recovery(raw or "")
    except Exception:  # noqa: BLE001 - untrusted logged text, never crash a report
        return None
    return data


def parse_visible_owners(prompt_user: str, me_seat: int) -> dict[int, int]:
    """Map unit_id -> owner seat from a prompt's VISIBLE UNITS block. A
    "(YOURS)" unit is owned by `me_seat` (the seat whose prompt this is)."""
    owners: dict[int, int] = {}
    for m in _VISIBLE_UNIT_RE.finditer(prompt_user or ""):
        uid = int(m.group(1))
        owners[uid] = int(m.group(2)) if m.group(2) is not None else me_seat
    return owners


def supports_targeting_freerider(
    raw_response: str, visible_owners: dict[int, int], freerider_seats: set[int]
) -> int:
    """Count `Support` orders in a raw orders response whose target unit is
    owned by a freerider seat (the subsidy metric)."""
    data = _extract(raw_response)
    if not isinstance(data, dict):
        return 0
    orders = data.get("orders")
    if not isinstance(orders, dict):
        return 0
    count = 0
    for od in orders.values():
        if isinstance(od, dict) and od.get("type") == "Support":
            target = coerce_id(od.get("target"))
            if target is not None and visible_owners.get(target) in freerider_seats:
                count += 1
    return count


def stance_toward_targets(raw_response: str, targets: set[int]) -> dict[int, str]:
    """Extract the declared stance toward each target seat from a raw negotiate
    response. Only explicit stances are returned; a missing target is omitted
    (the caller decides how to treat the game default)."""
    data = _extract(raw_response)
    out: dict[int, str] = {}
    if not isinstance(data, dict):
        return out
    press = data.get("press")
    if not isinstance(press, dict):
        return out
    stance = press.get("stance")
    if not isinstance(stance, dict):
        return out
    for k, v in stance.items():
        pid = coerce_id(k)
        if pid in targets and isinstance(v, str):
            out[pid] = v
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def game_scorecard(
    sweep: dict,
    telemetry: dict,
    decisions_by_seat: dict[int, list[dict]],
    freerider_names: set[str],
) -> dict:
    """Per-game scorecard from one sweep record, its telemetry record, and each
    LLM seat's decision log."""
    agents = sweep.get("agents", [])
    llm_seats = list(sweep.get("llm_seats") or [])
    freerider_seats = [i for i, name in enumerate(agents) if name in freerider_names]
    fr_set = set(freerider_seats)
    final_scores = sweep.get("final_scores", [])
    winners = set(sweep.get("winners") or [])

    freerider_score = _mean([final_scores[i] for i in freerider_seats])
    llm_mean = _mean([final_scores[i] for i in llm_seats])

    subsidy = 0
    per_turn: dict[int, dict] = {}
    for seat in llm_seats:
        for rec in decisions_by_seat.get(seat, []):
            phase = rec.get("phase")
            raw = rec.get("raw_response", "")
            if phase == "orders":
                owners = parse_visible_owners(rec.get("prompt", {}).get("user", ""), seat)
                subsidy += supports_targeting_freerider(raw, owners, fr_set)
            elif phase == "negotiate":
                turn = rec.get("turn")
                bucket = per_turn.setdefault(
                    turn,
                    {"turn": turn, "ally": 0, "neutral": 0, "hostile": 0, "unknown": 0},
                )
                fell_back = rec.get("fell_back", False)
                stances = stance_toward_targets(raw, fr_set)
                for fs in freerider_seats:
                    if fell_back:
                        bucket["unknown"] += 1
                        continue
                    # Explicit stance, else the game default (NEUTRAL).
                    st = stances.get(fs, "neutral")
                    if st in ("ally", "neutral", "hostile"):
                        bucket[st] += 1
                    else:
                        bucket["unknown"] += 1
    stance_trajectory = [per_turn[t] for t in sorted(per_turn)]

    per_seat = telemetry.get("per_seat", {})
    parse_fail: dict[int, dict] = {}
    for seat in llm_seats:
        s = per_seat.get(str(seat)) or per_seat.get(seat) or {}
        parse_fail[seat] = {
            "n": s.get("n_decisions", 0),
            "fails": s.get("parse_fail_count", 0),
        }

    return {
        "game_id": sweep.get("game_id"),
        "seed": sweep.get("seed"),
        "freerider_seats": freerider_seats,
        "llm_seats": llm_seats,
        "freerider_score": freerider_score,
        "llm_mean_score": llm_mean,
        "margin": freerider_score - llm_mean,
        "winner_seats": sorted(winners),
        "freerider_won": any(fs in winners for fs in freerider_seats),
        "subsidy": subsidy,
        "stance_trajectory": stance_trajectory,
        "parse_fail": parse_fail,
    }


def aggregate_scorecard(games: list[dict]) -> dict:
    """Aggregate per-game scorecards into the arm-level summary."""
    n = len(games)
    won = sum(1 for g in games if g.get("freerider_won"))
    total_subsidy = sum(g.get("subsidy", 0) for g in games)
    total_decisions = sum(
        pf.get("n", 0) for g in games for pf in g.get("parse_fail", {}).values()
    )
    total_fails = sum(
        pf.get("fails", 0) for g in games for pf in g.get("parse_fail", {}).values()
    )
    return {
        "n_games": n,
        "freerider_win_rate": (won / n) if n else 0.0,
        "freerider_wins": won,
        "mean_margin": _mean([g.get("margin", 0.0) for g in games]),
        "total_subsidy": total_subsidy,
        "mean_subsidy_per_game": (total_subsidy / n) if n else 0.0,
        "parse_fail_rate": (total_fails / total_decisions) if total_decisions else 0.0,
        "per_game": games,
    }


# --- file-level reading (for the CLI) ----------------------------------------


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_decisions(out_dir: Path, game_id: int, llm_seats: list[int]) -> dict[int, list[dict]]:
    """Load per-seat decision logs, tolerating both the multi-seat
    (`decisions_game{g}_seat{s}.jsonl`) and single-seat
    (`decisions_game{g}.jsonl`) naming the harness uses."""
    by_seat: dict[int, list[dict]] = {}
    for seat in llm_seats:
        multi = out_dir / f"decisions_game{game_id}_seat{seat}.jsonl"
        single = out_dir / f"decisions_game{game_id}.jsonl"
        if multi.exists():
            by_seat[seat] = _load_jsonl(multi)
        elif single.exists() and len(llm_seats) == 1:
            by_seat[seat] = _load_jsonl(single)
        else:
            by_seat[seat] = []
    return by_seat


def scorecard(out_dir: str | Path, freerider_names: set[str]) -> dict:
    """Read a full run out-dir and return the aggregate scorecard."""
    out = Path(out_dir)
    sweeps = _load_jsonl(out / "sweep.jsonl")
    telemetry_by_game = {t.get("game_id"): t for t in _load_jsonl(out / "telemetry.jsonl")}
    games = []
    for sweep in sweeps:
        gid = sweep.get("game_id")
        llm_seats = list(sweep.get("llm_seats") or [])
        decisions = _load_decisions(out, gid, llm_seats)
        telemetry = telemetry_by_game.get(gid, {})
        games.append(game_scorecard(sweep, telemetry, decisions, freerider_names))
    return aggregate_scorecard(games)
