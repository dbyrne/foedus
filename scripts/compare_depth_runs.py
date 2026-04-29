"""Diff two depth-eval JSON artifacts.

Usage:
    python3 scripts/compare_depth_runs.py before.json after.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def _engagement_rows(art: dict) -> dict[str, float]:
    eng = (art.get("tier1_random_pool") or {}).get("engagement", {})
    return {f"tier1.engagement.{k}": float(v) for k, v in eng.items()}


def _probe_rows(art: dict) -> dict[str, float]:
    out = {}
    for p in art.get("tier2_probes", []):
        out[f"probe.{p['name']}.score_diff"] = float(p["score_diff"])
        for k, v in (p.get("engagement") or {}).items():
            out[f"probe.{p['name']}.engagement.{k}"] = float(v)
    return out


def _collect_metrics(art: dict) -> dict[str, float]:
    metrics = {}
    metrics.update(_engagement_rows(art))
    metrics.update(_probe_rows(art))
    return metrics


def _is_significant(key: str, before: float, after: float,
                    eps_rate: float, eps_score: float) -> bool:
    delta = abs(after - before)
    if "score_diff" in key or "score" in key:
        return delta >= eps_score
    return delta >= eps_rate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--full", action="store_true",
                        help="Print all metrics, not just changed ones.")
    parser.add_argument("--eps-rate", type=float, default=0.05)
    parser.add_argument("--eps-score", type=float, default=0.5)
    args = parser.parse_args()

    a = json.loads(args.before.read_text())
    b = json.loads(args.after.read_text())
    ma = _collect_metrics(a)
    mb = _collect_metrics(b)
    keys = sorted(set(ma.keys()) | set(mb.keys()))
    rows = []
    for k in keys:
        va = ma.get(k)
        vb = mb.get(k)
        if va is None or vb is None:
            rows.append((k, va, vb, None))
            continue
        if args.full or _is_significant(
            k, va, vb, args.eps_rate, args.eps_score
        ):
            rows.append((k, va, vb, vb - va))
    if not rows:
        print("no significant changes (use --full to see all metrics)")
        return 0
    width = max(len(r[0]) for r in rows)
    print(f"{'metric'.ljust(width)}    before     after        Δ")
    for k, va, vb, d in rows:
        va_s = "—" if va is None else f"{va:>+8.3f}"
        vb_s = "—" if vb is None else f"{vb:>+8.3f}"
        d_s = "—" if d is None else f"{d:>+8.3f}"
        print(f"{k.ljust(width)} {va_s} {vb_s} {d_s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
