"""G2 Phase B — constrained-decoding decomposition over the sealed campaign.

Reads a completed Phase B run dir that banked per-game MODEL decision logs
(``decisions/decisions_seed{i}_{arm}.jsonl``, written by
``foedus_phaseb_paired_eval.py``) and reports, PER ARM, the two confound
metrics the G2 prereg requires over the sealed campaign itself (not just the
G2a probe):

* **structural fallback** — decisions whose raw output is NOT a schema-valid
  full decision (per-phase schema, checked through the parser's own extractor).
  Under constrained decoding this is expected ~0 for BOTH arms; a non-zero
  count here means the grammar constraint failed somewhere and the B1 verdict
  is NOT purely strategic.
* **residual semantic illegality** — decisions that are schema-VALID yet the
  parser still fell back (a geometrically-illegal order/intent coerced to
  Hold), plus the per-emitted-order illegality rate for the orders phase.
  This is the channel constrained decoding deliberately does NOT fix; parity
  across arms is what keeps the placement gap a strategy measurement.

Also re-asserts training-corpus seed-disjointness from the REVEALED manifest
(public + reproducible, unlike the seal-time check that reads the secret).

Coverage-guarded: refuses to report unless every (seed, arm) decisions file is
present and its row count matches the banked sweep row's ``n_decisions``.

    PYTHONPATH=. python3 scripts/foedus_g2_residual_analysis.py \
        --run-dir docs/research/2026-07-11-gym-g2/phase-b/run \
        --corpus-manifest docs/research/2026-07-04-canonical-campaign-v1/run/seed_manifest.revealed.json \
        --corpus-manifest docs/research/2026-07-10-canonical-sonnet-arm/run/seed_manifest.revealed.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import jsonschema

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from foedus.agents.llm.parse import extract_json_with_recovery   # noqa: E402
from foedus.agents.llm.schema import (                            # noqa: E402
    negotiation_decision_schema,
    orders_decision_schema,
)
from foedus.eval._coverage import assert_coverage                 # noqa: E402

ARMS = ("trained", "base")

_SCHEMA_BY_PHASE = {
    "negotiate": negotiation_decision_schema(),
    "orders": orders_decision_schema(),
}


def _decision_valid(raw: str, phase: str) -> bool:
    data, _ = extract_json_with_recovery(raw)
    if not isinstance(data, dict):
        return False
    try:
        jsonschema.validate(data, _SCHEMA_BY_PHASE[phase])
        return True
    except jsonschema.ValidationError:
        return False


def _orders_emitted(raw: str) -> int:
    data, _ = extract_json_with_recovery(raw)
    if isinstance(data, dict) and isinstance(data.get("orders"), dict):
        return len(data["orders"])
    return 0


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def analyze(run_dir: Path, corpus_manifests: list[str]) -> dict:
    sweep = _read_jsonl(run_dir / "sweep.jsonl")
    plan = json.loads((run_dir / "phaseb_plan.json").read_text())
    num_seeds = plan["num_seeds"]
    assert_coverage(len(sweep), 2 * num_seeds, "sweep rows", 1.0)
    by_key = {(r["seed_index"], r["arm"]): r for r in sweep}

    # --- seed-disjointness, re-asserted from the PUBLIC revealed manifest ----
    revealed = json.loads((run_dir / "seed_manifest.revealed.json").read_text())
    eval_seeds = set(revealed["seeds"])
    assert_coverage(len(eval_seeds), num_seeds, "revealed seeds", 1.0)
    disjoint_record = []
    for mpath in corpus_manifests:
        corpus_seeds = json.loads(Path(mpath).read_text())["seeds"]
        if not corpus_seeds:
            raise SystemExit(f"{mpath}: empty seeds list — cannot assert "
                             "disjointness against nothing.")
        overlap = eval_seeds & set(corpus_seeds)
        if overlap:
            raise SystemExit(
                f"DISJOINTNESS VIOLATED: eval seeds {sorted(overlap)} appear "
                f"in training-corpus source {mpath}")
        disjoint_record.append({"path": mpath, "n_seeds": len(corpus_seeds)})

    # --- per-arm decomposition ------------------------------------------------
    out: dict = {
        "run_dir": str(run_dir),
        "constrained": plan.get("constrained", False),
        "num_seeds": num_seeds,
        "seed_disjointness": {
            "eval_seeds": len(eval_seeds),
            "checked_sources": disjoint_record,
            "disjoint": True,
        },
        "per_arm": {},
    }
    for arm in ARMS:
        agg = {
            "n_decisions": 0,
            "decision_valid": 0,
            "structural_fallback": 0,
            "total_parse_fallback": 0,
            "residual_illegal_decisions": 0,
            "orders_emitted": 0,
            "orders_illegal_coerced": 0,
            "by_phase": {"negotiate": 0, "orders": 0},
        }
        files_read = 0
        for i in range(num_seeds):
            path = run_dir / "decisions" / f"decisions_seed{i}_{arm}.jsonl"
            if not path.exists():
                raise SystemExit(f"missing decisions file: {path}")
            rows = _read_jsonl(path)
            files_read += 1
            banked = by_key[(i, arm)]
            if len(rows) != banked["n_decisions"]:
                raise SystemExit(
                    f"{path.name}: {len(rows)} decision rows != banked "
                    f"n_decisions {banked['n_decisions']} — decisions file is "
                    "not a faithful copy of the game, refusing to report.")
            for rec in rows:
                phase = rec["phase"]
                raw = rec["raw_response"]
                valid = _decision_valid(raw, phase)
                fell_back = bool(rec["fell_back"])
                agg["n_decisions"] += 1
                agg["by_phase"][phase] += 1
                if valid:
                    agg["decision_valid"] += 1
                    if fell_back:
                        agg["residual_illegal_decisions"] += 1
                else:
                    agg["structural_fallback"] += 1
                if fell_back:
                    agg["total_parse_fallback"] += 1
                if phase == "orders":
                    agg["orders_emitted"] += _orders_emitted(raw)
                    agg["orders_illegal_coerced"] += int(rec["n_coerced"])
        assert_coverage(files_read, num_seeds, f"decisions files [{arm}]", 1.0)
        n = agg["n_decisions"]
        assert_coverage(n, n or 1, f"decisions [{arm}]", 1.0)
        dv, oe = agg["decision_valid"], agg["orders_emitted"]
        agg["structural_fallback_rate"] = agg["structural_fallback"] / n
        agg["total_parse_fallback_rate"] = agg["total_parse_fallback"] / n
        agg["residual_illegal_decision_rate"] = (
            agg["residual_illegal_decisions"] / dv if dv else 0.0)
        agg["order_illegality_rate"] = (
            agg["orders_illegal_coerced"] / oe if oe else 0.0)
        out["per_arm"][arm] = agg
        print(f"[{arm:8s}] n {n}  "
              f"structural {agg['structural_fallback']}/{n} "
              f"({agg['structural_fallback_rate']:.1%})  "
              f"parse_fb {agg['total_parse_fallback']}/{n} "
              f"({agg['total_parse_fallback_rate']:.1%})  "
              f"residual_illegal(valid) {agg['residual_illegal_decisions']}/{dv} "
              f"({agg['residual_illegal_decision_rate']:.1%})  "
              f"order_illegal {agg['orders_illegal_coerced']}/{oe} "
              f"({agg['order_illegality_rate']:.1%})")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--corpus-manifest", action="append", default=[],
                   help="Training-corpus source seed manifest (revealed) to "
                        "re-assert disjointness against. May repeat.")
    p.add_argument("--out", type=Path, default=None,
                   help="Write the JSON report here (default: "
                        "<run-dir>/residual_illegality.json)")
    args = p.parse_args(argv)
    run_dir = Path(args.run_dir)
    res = analyze(run_dir, args.corpus_manifest)
    out = args.out or (run_dir / "residual_illegality.json")
    out.write_text(json.dumps(res, indent=2) + "\n")
    print(f"\n[residual-analysis] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
