"""Haiku fitness probe report (M-foedus-haiku-fitness-probe).

Reads a probe out-dir produced by ``scripts/foedus_canonical_campaign.py
--model haiku`` and reports the decision inputs the probe's pre-registered
verdict needs, per entrant identity (seats rotate, identities don't):

  * parse-fail split (timeout / transport / true-parse) -- reusing
    ``foedus_canonical_scorecard._classify_fell_back``, the same
    classification used for the Sonnet run #1 baseline (results.md §7.4), so
    the two numbers are directly comparable.
  * Support-order counts (bare + require_dest "pin"), reusing
    ``foedus.eval.punishment_metrics.classify_orders_execution`` and
    ``count_require_dest_declarations``.
  * degeneracy flags (all-Hold turns, repeated-identical-order runs) from
    ``foedus.eval.probe_metrics``.
  * the model's own verbatim cross-game self-notes, for spot-quoting.

This is a MEASUREMENT script, not a campaign tool: no seals, no leaderboard
update, no OpenSkill standings read -- see the probe report doc for the
decision itself.

Usage:
    PYTHONPATH=. python3 scripts/foedus_haiku_probe_report.py \
        --out-dir docs/research/2026-07-09-haiku-fitness-probe/run
    PYTHONPATH=. python3 scripts/foedus_haiku_probe_report.py \
        --out-dir <dir> --json > probe_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from foedus.eval.probe_metrics import (
    all_hold_turns,
    repeated_identical_order_runs,
    self_notes_for_identity,
)
from foedus.eval.punishment_metrics import (
    classify_orders_execution,
    count_require_dest_declarations,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from foedus_canonical_scorecard import _classify_fell_back  # noqa: E402


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def build_report(out_dir: str) -> dict:
    d = Path(out_dir)
    sweeps = sorted(_load_jsonl(d / "sweep.jsonl"), key=lambda s: s.get("game_id"))

    parse_fail_by_identity: dict[str, dict[str, int]] = {}
    support_orders_by_identity: dict[str, dict[str, int]] = {}
    degeneracy_by_identity: dict[str, dict[str, list]] = {}
    identities: set[str] = set()

    for sweep in sweeps:
        gid = sweep.get("game_id")
        agents = sweep.get("agents") or sweep.get("identity_by_seat") or []
        for seat in sweep.get("llm_seats", []):
            ident = agents[seat] if seat < len(agents) else f"seat{seat}"
            identities.add(ident)
            decisions = _load_jsonl(d / f"decisions_game{gid}_seat{seat}.jsonl")

            fail_bucket = parse_fail_by_identity.setdefault(
                ident, {"decisions": 0, "timeout": 0, "transport": 0, "parse": 0})
            for rec in decisions:
                fail_bucket["decisions"] += 1
                kind = _classify_fell_back(rec)
                if kind:
                    fail_bucket[kind] += 1

            support_bucket = support_orders_by_identity.setdefault(
                ident, {"bare": 0, "pin": 0, "total": 0})
            orders_decisions = [r for r in decisions if r.get("phase") == "orders"]
            for rec in orders_decisions:
                supports = classify_orders_execution(
                    rec.get("raw_response") or "", golf_nodes=set())["supports"]
                support_bucket["total"] += len(supports)
            support_bucket["pin"] += count_require_dest_declarations(
                {seat: orders_decisions})["orders_phase"]

            deg_bucket = degeneracy_by_identity.setdefault(
                ident, {"all_hold_turns": [], "repeated_order_runs": []})
            deg_bucket["all_hold_turns"].extend(all_hold_turns(decisions))
            deg_bucket["repeated_order_runs"].extend(
                repeated_identical_order_runs(decisions))

    for bucket in support_orders_by_identity.values():
        bucket["bare"] = bucket["total"] - bucket["pin"]

    self_notes_by_identity = {
        ident: self_notes_for_identity(d, ident) for ident in sorted(identities)
    }

    return {
        "out_dir": str(d),
        "n_games": len(sweeps),
        "parse_fail_by_identity": parse_fail_by_identity,
        "support_orders_by_identity": support_orders_by_identity,
        "degeneracy_by_identity": degeneracy_by_identity,
        "self_notes_by_identity": self_notes_by_identity,
    }


def _print_report(rep: dict) -> None:
    print("=== Haiku fitness probe report ===")
    print(f"out-dir: {rep['out_dir']}   games: {rep['n_games']}")
    print()
    print("-- parse-fail by identity --")
    for ident, b in sorted(rep["parse_fail_by_identity"].items()):
        rate = (b["timeout"] + b["transport"] + b["parse"]) / b["decisions"] * 100 \
            if b["decisions"] else 0.0
        print(f"  {ident}: {b['decisions']} decisions, "
              f"timeout={b['timeout']} transport={b['transport']} parse={b['parse']} "
              f"({rate:.1f}% fail)")
    print()
    print("-- Support orders (bare / pin) by identity --")
    for ident, b in sorted(rep["support_orders_by_identity"].items()):
        print(f"  {ident}: bare={b['bare']} pin={b['pin']} total={b['total']}")
    print()
    print("-- degeneracy flags by identity --")
    for ident, b in sorted(rep["degeneracy_by_identity"].items()):
        print(f"  {ident}: all-Hold turns={b['all_hold_turns']} "
              f"repeated-order runs={b['repeated_order_runs']}")
    print()
    print("-- self-notes by identity --")
    for ident, notes in sorted(rep["self_notes_by_identity"].items()):
        for n in notes:
            print(f"  {ident} (game {n['game_index']}): {n['self_note']!r}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = p.parse_args(argv)

    rep = build_report(args.out_dir)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        _print_report(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
