"""Render the ruleset-v1 evidence figures from results.json.

Colorblind-safe by construction (David is red/green colorblind): uses the
Okabe-Ito palette, never encodes meaning as red-vs-green, and backs every
color with a distinct marker / hatch and a direct text label.

    python scripts/foedus_ruleset_figures.py docs/design/2026-07-04-ruleset-v1-evidence

Requires matplotlib (dev/evidence-only; not a runtime dependency of foedus).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Okabe-Ito colorblind-safe palette.
OI = {
    "blue": "#0072B2", "orange": "#E69F00", "skyblue": "#56B4E9",
    "purple": "#CC79A7", "green": "#009E73", "vermillion": "#D55E00",
    "yellow": "#F0E442", "black": "#000000",
}


def fig_convergence(res, out_dir):
    conv = res["convergence"]
    # (label in results, legend, color, marker)
    series = [
        ("4-spread-t12", "4 entrants (spread)", OI["blue"], "o"),
        ("5-spread-t12", "5 entrants (spread)", OI["orange"], "s"),
        ("6-full-t12", "6 entrants (full ladder)", OI["purple"], "^"),
        ("4-hard-tie", "4 entrants (near-tied pair)", OI["skyblue"], "D"),
    ]
    fig, ax = plt.subplots(figsize=(8, 5))
    for key, label, color, marker in series:
        if key not in conv:
            continue
        c = conv[key]
        gs = c["game_counts"]
        ys = [c["curve"][str(g)]["frac_correct"] for g in gs]
        ax.plot(gs, ys, marker=marker, color=color, label=label, lw=2, ms=6)
    ax.axhline(0.95, ls="--", color=OI["black"], lw=1)
    ax.text(gs[-1], 0.955, "0.95 target", ha="right", va="bottom", fontsize=9)
    ax.set_xscale("log")
    ax.set_xlabel("games played in the match (log scale)")
    ax.set_ylabel("P(ladder sorted correctly)  [Kendall tau >= 0.9]")
    ax.set_title("Rating convergence: games until a match's standings sort correctly")
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", frameon=True)
    fig.tight_layout()
    p = out_dir / "fig1_convergence.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def _cell(grid, seats, turns, radius):
    return next(x for x in grid if x["seats"] == seats
               and x["turns"] == turns and x["radius"] == radius)


def fig_discrimination(res, out_dir):
    """Two panels: (A) the recovery-tau validity gate (radius 1 fails);
    (B) competitive-band discrimination D_mid ± CI at radius 2."""
    grid = res["grid"]
    seats = [4, 5, 6]
    turns = [8, 12, 15]
    hatches = {8: "///", 12: "...", 15: "xxx"}
    colors = {8: OI["blue"], 12: OI["orange"], 15: OI["purple"]}
    fig, (axA, axB) = plt.subplots(1, 2, figsize=(12, 5))

    # Panel A: recovery tau by radius (the gate), at 12 turns.
    width = 0.35
    rad_color = {1: OI["vermillion"], 2: OI["blue"]}
    rad_hatch = {1: "xxx", 2: None}
    for ri, radius in enumerate([1, 2]):
        xs = [s + (ri - 0.5) * width for s in seats]
        ys = [_cell(grid, s, 12, radius)["recovery_tau"]["mean"] for s in seats]
        es = [_cell(grid, s, 12, radius)["recovery_tau"]["std"] for s in seats]
        bars = axA.bar(xs, ys, width,
                       label=f"radius {radius} "
                             f"({'7-cell disk — cramped' if radius==1 else '19-cell disk'})",
                       color=rad_color[radius], hatch=rad_hatch[radius],
                       edgecolor=OI["black"], lw=0.6, yerr=es, capsize=3)
        for rect, y in zip(bars, ys):
            axA.text(rect.get_x() + rect.get_width()/2, max(y, 0) + 0.03,
                     f"{y:+.2f}", ha="center", va="bottom", fontsize=8)
    axA.axhline(0.9, ls="--", color=OI["black"], lw=1)
    axA.text(6.4, 0.91, "0.9 validity gate", ha="right", va="bottom", fontsize=9)
    axA.set_xticks(seats)
    axA.set_xticklabels([f"{s} seats" for s in seats])
    axA.set_ylabel("recovery tau  (ladder ordering vs truth)")
    axA.set_title("(A) Validity gate: only radius 2 recovers the ladder\n"
                  "(12 turns; radius 1 tau near 0 = scrambled)")
    axA.set_ylim(-0.1, 1.05)
    axA.grid(True, axis="y", alpha=0.3)
    axA.legend(loc="center left", fontsize=8)

    # Panel B: competitive-band discrimination at radius 2, seats x turns.
    width = 0.25
    for ti, t in enumerate(turns):
        xs = [s + (ti - 1) * width for s in seats]
        ys = [_cell(grid, s, t, 2)["D_mid"]["mean"] for s in seats]
        es = [_cell(grid, s, t, 2)["D_mid"]["std"] for s in seats]
        bars = axB.bar(xs, ys, width, label=f"{t} turns",
                       color=colors[t], hatch=hatches[t],
                       edgecolor=OI["black"], lw=0.6, yerr=es, capsize=3)
        for rect, y in zip(bars, ys):
            axB.text(rect.get_x() + rect.get_width()/2, y + 0.03,
                     f"{y:.2f}", ha="center", va="bottom", fontsize=7)
    axB.set_xticks(seats)
    axB.set_xticklabels([f"{s} seats" for s in seats])
    axB.set_ylabel("competitive-band discrimination D_mid  (+/- std over seeds)")
    axB.set_title("(B) Radius 2: discrimination of the competitive band\n"
                  "(4 seats best; turns barely move it)")
    axB.grid(True, axis="y", alpha=0.3)
    axB.legend(title="game length", loc="upper right", fontsize=8)

    fig.suptitle("Skill discrimination by format "
                 "(read D only for tau-valid formats)")
    fig.tight_layout()
    p = out_dir / "fig2_discrimination.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def fig_ladder(res, out_dir):
    grid = res["grid"]
    g = next(x for x in grid if x["seats"] == 4 and x["turns"] == 12
             and x["radius"] == 2)
    order = g["order"]  # strong -> weak
    names = list(reversed(order))  # plot weak (bottom) -> strong (top)
    mus = [g["ratings"][n]["mu"] for n in names]
    sigmas = [g["ratings"][n]["sigma"] for n in names]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ys = range(len(names))
    ax.errorbar(mus, ys, xerr=sigmas, fmt="o", color=OI["blue"],
                ecolor=OI["orange"], elinewidth=3, capsize=5, ms=8)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(names)
    for y, mu in zip(ys, mus):
        ax.text(mu, y + 0.15, f"mu={mu:.1f}", ha="center", va="bottom",
                fontsize=8)
    ax.set_xlabel("OpenSkill mu  (+/- sigma)")
    ax.set_title("Recommended format (4 seats, 12 turns, radius 2): "
                 "ladder separation")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    p = out_dir / "fig3_ladder.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def main(argv=None):
    argv = argv or sys.argv[1:]
    out_dir = Path(argv[0]) if argv else Path(
        "docs/design/2026-07-04-ruleset-v1-evidence")
    res = json.loads((out_dir / "results.json").read_text())
    for fn in (fig_convergence, fig_discrimination, fig_ladder):
        p = fn(res, out_dir)
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
