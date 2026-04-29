"""Render a depth-eval JSON artifact as a Markdown report."""
from __future__ import annotations
from typing import Any


def render_markdown(artifact: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Depth Eval Report — {artifact['run_id']}")
    lines.append("")
    lines.append(f"- **Git:** `{artifact.get('git_branch','?')}` @ "
                 f"`{artifact.get('git_sha','?')}`")
    lines.append(f"- **Timestamp:** {artifact.get('timestamp','?')}")
    lines.append(f"- **Stat rigor:** {artifact.get('stat_rigor','point')}")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    for k, v in (artifact.get("config") or {}).items():
        lines.append(f"- `{k}` = {v}")
    lines.append("")

    t1 = artifact.get("tier1_random_pool") or {}
    if t1:
        lines.append("## Tier 1 — Random pool")
        lines.append("")
        lines.append(f"n_games = {t1.get('n_games', '?')}, "
                     f"seed = {t1.get('seed', '?')}")
        lines.append("")
        lines.append("### Rankings")
        lines.append("")
        lines.append("| # | Agent | Mean | CI95 | N |")
        lines.append("|---|---|---|---|---|")
        for i, row in enumerate(t1.get("rankings", []), 1):
            ci = row.get("ci95")
            ci_s = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "—"
            lines.append(f"| {i} | {row['agent']} | "
                         f"{row['mean_score']:.2f} | {ci_s} | "
                         f"{row['n_appearances']} |")
        lines.append("")
        lines.append("### Engagement")
        lines.append("")
        lines.append("| Metric | Per-game mean |")
        lines.append("|---|---|")
        for k, v in (t1.get("engagement") or {}).items():
            if isinstance(v, float):
                lines.append(f"| `{k}` | {v:.4f} |")
            else:
                lines.append(f"| `{k}` | {v} |")
        lines.append("")
        lines.append("### Pairwise winrate (row beats column)")
        lines.append("")
        pw = t1.get("pairwise_winrate") or {}
        if pw:
            cols = pw.get("col_agents", [])
            lines.append("| | " + " | ".join(cols) + " |")
            lines.append("|" + "---|" * (len(cols) + 1))
            for ra, mrow in zip(pw.get("row_agents", []),
                                pw.get("matrix", [])):
                cells = []
                for v in mrow:
                    cells.append("—" if v is None else f"{v:.2f}")
                lines.append(f"| **{ra}** | " + " | ".join(cells) + " |")
        lines.append("")

    probes = artifact.get("tier2_probes") or []
    if probes:
        lines.append("## Tier 2 — Fixed-seat probes")
        lines.append("")
        lines.append("| Probe | Seats | n | Score diff | CI95 |")
        lines.append("|---|---|---|---|---|")
        for p in probes:
            ci = p.get("ci95")
            ci_s = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "—"
            seats_s = ", ".join(p.get("seats", []))
            lines.append(f"| `{p['name']}` | {seats_s} | "
                         f"{p.get('n','?')} | {p['score_diff']:+.2f} | "
                         f"{ci_s} |")
        lines.append("")

    sweep = artifact.get("tier3_knob_sweep")
    if sweep:
        lines.append("## Tier 3 — Knob sweep")
        lines.append("")
        lines.append(f"Knob: `{sweep.get('knob','?')}`")
        lines.append("")

    return "\n".join(lines) + "\n"
