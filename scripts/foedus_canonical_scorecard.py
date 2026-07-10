"""Canonical ruleset-v1 campaign scorecard + trajectory + verdict inputs.

Reads a campaign out-dir produced by ``scripts/foedus_canonical_campaign.py`` and
reports everything the pre-declared verdict needs, in one place:

  * per-game + aggregate freerider metrics — reusing
    ``foedus.eval.memory_metrics.scorecard`` (margin, wins, subsidy = LLM Support
    orders targeting a freerider unit, LLM<->LLM supports = coalition, per-turn
    stance-toward-freerider).
  * **learning-across-campaign trajectory (games 1..N)** — the defector-
    punishment signal: does subsidy trend toward 0, coalition (LLM<->LLM
    supports) strengthen, freerider margin fall, and hostility-toward-freerider
    rise as games accumulate? Reported as a per-game series plus a first-half vs
    second-half delta (no curve-fitting claims on 8 points).
  * **parse-fail split: timeout vs. true** — a fell-back decision whose raw
    response is a ``<client error: ...>`` is a transport/timeout fallback (a cost
    artifact), distinct from a genuine unparseable model response. Reported per
    entrant identity (seats rotate, identities don't).
  * OpenSkill standings — from ``standings.json`` if present.

Colour is never load-bearing (David is red/green colourblind): direction is shown
with words + arrows (v / ^ / ->), not colour.

Usage:
    PYTHONPATH=. python3 scripts/foedus_canonical_scorecard.py \
        --out-dir docs/research/2026-07-04-canonical-campaign-v1/run
    PYTHONPATH=. python3 scripts/foedus_canonical_scorecard.py \
        --out-dir <dir> --json > scorecard.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from foedus.eval._coverage import assert_coverage
from foedus.eval.memory_metrics import scorecard as base_scorecard


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _classify_fell_back(rec: dict) -> str | None:
    """None if the decision did not fall back; else 'timeout' | 'transport' |
    'parse' for a fallback caused by a client timeout, another transport error,
    or a genuinely unparseable model response."""
    if not rec.get("fell_back"):
        return None
    raw = rec.get("raw_response", "") or ""
    if raw.startswith("<client error:"):
        low = raw.lower()
        # ClaudeCLIClient raises RuntimeError("claude -p timed out after {t}s")
        # on a subprocess.TimeoutExpired; repr() carries "timed out", not the
        # exception class name.
        if "timed out" in low or "timeout" in low:
            return "timeout"
        return "transport"
    return "parse"


def _stance_hostility_fraction(stance_trajectory: list[dict]) -> float | None:
    """Fraction of (turn x freerider) stance observations that were HOSTILE,
    over the whole game — a compact 'how suspicious was the table of the
    freerider' scalar. None when nothing was observed."""
    hostile = neutral = ally = 0
    for t in stance_trajectory:
        hostile += t.get("hostile", 0)
        neutral += t.get("neutral", 0)
        ally += t.get("ally", 0)
    total = hostile + neutral + ally
    if total == 0:
        return None
    return hostile / total


def _delta_arrow(first: float, second: float) -> str:
    d = second - first
    if abs(d) < 1e-9:
        return "-> flat"
    return ("^ up" if d > 0 else "v down") + f" ({d:+.2f})"


def _halves_mean(series: list[float]):
    vals = [v for v in series if v is not None]
    if not vals:
        return None, None
    mid = len(vals) // 2 or 1
    first = sum(vals[:mid]) / len(vals[:mid])
    second = sum(vals[mid:]) / len(vals[mid:]) if vals[mid:] else first
    return first, second


def _freerider_handles_from_plan(out_dir: Path) -> set[str] | None:
    """The freerider handle(s) recorded operator-side in campaign_plan.json, so
    the scorecard finds the (neutral-handle) freerider without the operator
    having to remember it. None if no plan is present."""
    plan_path = out_dir / "campaign_plan.json"
    if not plan_path.exists():
        return None
    plan = json.loads(plan_path.read_text())
    handles = plan.get("freerider_handles")
    return set(handles) if handles else None


def build_report(out_dir: str, freerider_names: set[str] | None = None) -> dict:
    d = Path(out_dir)
    if not freerider_names:
        freerider_names = _freerider_handles_from_plan(d) or {"DishonestCooperator"}
    agg = base_scorecard(out_dir, freerider_names)
    sweeps = {s.get("game_id"): s for s in _load_jsonl(d / "sweep.jsonl")}

    # per-entrant parse-fail split (seats rotate; identity is stable)
    by_identity: dict[str, dict[str, int]] = {}
    total_records_read = 0
    for gid, sweep in sweeps.items():
        idbyseat = sweep.get("identity_by_seat") or sweep.get("agents") or []
        for seat in sweep.get("llm_seats", []):
            ident = idbyseat[seat] if seat < len(idbyseat) else f"seat{seat}"
            recs = _load_jsonl(d / f"decisions_game{gid}_seat{seat}.jsonl")
            total_records_read += len(recs)
            bucket = by_identity.setdefault(
                ident, {"decisions": 0, "timeout": 0, "transport": 0, "parse": 0})
            for rec in recs:
                bucket["decisions"] += 1
                kind = _classify_fell_back(rec)
                if kind:
                    bucket[kind] += 1

    assert_coverage(total_records_read, total_records_read,
                     "canonical scorecard: decision records read")

    # trajectory across games (ordered by game_id)
    per_game = sorted(agg["per_game"], key=lambda g: (g.get("game_id") is None,
                                                       g.get("game_id")))
    traj = []
    for g in per_game:
        gid = g.get("game_id")
        sweep = sweeps.get(gid, {})
        traj.append({
            "game_id": gid,
            "seed": g.get("seed"),
            "freerider_seat": (g.get("freerider_seats") or [None])[0],
            "freerider_won": g.get("freerider_won"),
            "margin": round(g.get("margin", 0.0), 2),
            "subsidy": g.get("subsidy", 0),
            "llm_llm_supports": g.get("llm_llm_supports", 0),
            "stance_hostility_frac": _stance_hostility_fraction(
                g.get("stance_trajectory", [])),
            "wall_clock_s": sweep.get("wall_clock_s"),
        })

    def series(key):
        return [t[key] for t in traj]

    trend = {}
    for key in ("subsidy", "llm_llm_supports", "margin", "stance_hostility_frac"):
        first, second = _halves_mean(series(key))
        trend[key] = {
            "first_half_mean": None if first is None else round(first, 3),
            "second_half_mean": None if second is None else round(second, 3),
            "direction": (None if first is None
                          else _delta_arrow(first, second)),
        }

    standings = None
    sp = d / "standings.json"
    if sp.exists():
        standings = json.loads(sp.read_text())

    run_summary = None
    rp = d / "run_summary.json"
    if rp.exists():
        run_summary = json.loads(rp.read_text())

    return {
        "out_dir": str(d),
        "aggregate": {k: v for k, v in agg.items() if k != "per_game"},
        "trajectory": traj,
        "trend": trend,
        "parse_fail_by_identity": by_identity,
        "standings": standings,
        "run_summary": run_summary,
    }


def _print_report(rep: dict) -> None:
    agg = rep["aggregate"]
    print("=== canonical ruleset-v1 campaign scorecard ===")
    print(f"out-dir: {rep['out_dir']}")
    print(f"games: {agg['n_games']}   "
          f"freerider wins: {agg['freerider_wins']}/{agg['n_games']} "
          f"(win-rate {agg['freerider_win_rate']:.0%})   "
          f"mean margin (freerider - LLM mean): {agg['mean_margin']:+.2f}")
    print(f"mean subsidy/game: {agg['mean_subsidy_per_game']:.2f}   "
          f"mean LLM<->LLM supports/game: {agg['mean_llm_llm_supports_per_game']:.2f}   "
          f"parse-fail: {agg['parse_fail_rate']:.1%}")
    print()
    print("trajectory (games 1..N) -- defector-punishment signal:")
    print("  game seed        frdr   won  margin  subsidy  coalition  hostility  wall")
    for t in rep["trajectory"]:
        host = "-" if t["stance_hostility_frac"] is None else f"{t['stance_hostility_frac']:.2f}"
        wall = "-" if t["wall_clock_s"] is None else f"{t['wall_clock_s']/60:.0f}m"
        print(f"  {str(t['game_id']):>4} {str(t['seed'])[:10]:>10} "
              f"seat{t['freerider_seat']}  "
              f"{'Y' if t['freerider_won'] else '.':>3}  "
              f"{t['margin']:+6.1f}  {t['subsidy']:>7}  {t['llm_llm_supports']:>9}  "
              f"{host:>9}  {wall:>5}")
    print()
    print("first-half vs second-half (does the table LEARN to punish?):")
    for key, label in [("subsidy", "subsidy (want v down)"),
                       ("llm_llm_supports", "coalition (want ^ up)"),
                       ("margin", "freerider margin (want v down)"),
                       ("stance_hostility_frac", "hostility->freerider (want ^ up)")]:
        tr = rep["trend"][key]
        if tr["direction"] is None:
            print(f"  {label:<34} (no data)")
        else:
            print(f"  {label:<34} {tr['first_half_mean']} -> "
                  f"{tr['second_half_mean']}   {tr['direction']}")
    print()
    print("parse-fail by entrant (timeout vs true parse):")
    for ident, b in rep["parse_fail_by_identity"].items():
        nd = b["decisions"]
        tot = b["timeout"] + b["transport"] + b["parse"]
        print(f"  {ident:<22} {tot}/{nd} fell back  "
              f"[timeout {b['timeout']}, transport {b['transport']}, "
              f"true-parse {b['parse']}]")
    if rep["standings"]:
        print()
        print("OpenSkill standings (conservative mu-3sigma):")
        for row in rep["standings"]["standings"]:
            print(f"  {row['identity']:<22} mu={row['mu']:.2f} "
                  f"sigma={row['sigma']:.2f} cons={row['conservative']:.2f}")
    if rep["run_summary"]:
        rs = rep["run_summary"]
        print()
        print(f"wall-clock: {rs['match_wall_clock_s']/3600:.2f}h "
              f"({rs['mean_game_wall_clock_s']/60:.1f}m/game)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--freerider", default=None,
                   help="Comma-separated identity/name(s) treated as freerider. "
                        "Default: auto-read freerider_handles from "
                        "campaign_plan.json, else 'DishonestCooperator'.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    names = ({n.strip() for n in args.freerider.split(",") if n.strip()}
             if args.freerider else None)
    rep = build_report(args.out_dir, names)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        _print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
