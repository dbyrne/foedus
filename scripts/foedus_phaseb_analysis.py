"""G1 Phase B — analysis: apply the pre-registered B1/B2 verdict rules.

Reads a completed Phase B run dir (``sweep.jsonl`` + ``phaseb_plan.json`` +
``seed_manifest.revealed.json``) and emits ``results.json`` + ``results.md``
answering B1 (trained beats base) and B2 (Golf containment), with the paired
sign tests, the seal table, every metric denominated "N of M", and the verdicts
applied EXACTLY as pre-registered (see ``prereg.md``).

Coverage-guarded: refuses to report unless it parsed all 2·num_seeds banked
rows and every pair is complete + board-fingerprint-consistent.

    PYTHONPATH=. python3 scripts/foedus_phaseb_analysis.py \
        --run-dir docs/research/2026-07-10-gym-g1/phase-b/run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from foedus.eval._coverage import assert_coverage          # noqa: E402
from foedus.eval import campaign                            # noqa: E402
from foedus.eval.phaseb import (                            # noqa: E402
    competition_ranks,
    summary_stats,
    two_sided_sign_test,
)


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _verdict(sign, *, better_label: str, worse_label: str) -> str:
    """Apply the pre-registered 4-way verdict to a sign-test result.

    Convention: n_positive counts pairs where the *better_label* arm won.
    """
    p = sign.p_value
    pos, neg = sign.n_positive, sign.n_negative
    if pos > neg and p < 0.05:
        return f"REAL — {better_label} (sign test p={p:.4g})"
    if neg > pos and p < 0.05:
        return f"{worse_label.upper()} (sign test p={p:.4g})"
    if pos > neg and p < 0.20:
        return f"SUGGESTIVE — leans {better_label}, not significant (p={p:.4g})"
    if neg > pos and p < 0.20:
        return f"SUGGESTIVE — leans {worse_label}, not significant (p={p:.4g})"
    return f"NULL — no significant difference (p={p:.4g})"


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _mechanical_vs_strategic(by_seed: dict, num_seeds: int) -> dict:
    """DESCRIPTIVE decomposition of the B1 confound (added at reviewer request).

    Distinguishes "trained beats base because it emits valid JSON far more often
    (fewer fallback-Holds)" — a real, valuable distillation outcome but a
    *mechanical* one — from "trained learned better strategy". Everything here is
    computed from the banked per-game MODEL parse-fail counts: a game's MODEL
    "fallback rate" = parse_fail_count / n_decisions is exactly the fraction of
    that game's MODEL turns that fell back to a safe Hold. This is a
    descriptive/secondary lens; it does NOT alter the pre-registered primary
    verdict (the B1 placement sign test, computed unchanged elsewhere).
    """
    seeds = []
    for i in range(num_seeds):
        pair = by_seed[i]
        ms = pair["trained"]["model_seat"]
        d = {"seed_index": i, "model_seat": ms}
        for arm in ("trained", "base"):
            r = pair[arm]
            n, f = r["n_decisions"], r["parse_fail_count"]
            d[f"{arm}_fallback"] = f
            d[f"{arm}_ndec"] = n
            d[f"{arm}_fbrate"] = (f / n) if n else 0.0
            d[f"{arm}_rank"] = competition_ranks(r["final_scores"], r["eliminated"])[ms]
            d[f"{arm}_score"] = r["final_scores"][ms]
        d["place_delta"] = d["base_rank"] - d["trained_rank"]   # >0 ⇒ trained placed better
        d["fbgap"] = d["base_fbrate"] - d["trained_fbrate"]     # >0 ⇒ base noisier
        seeds.append(d)

    tf = sum(s["trained_fallback"] for s in seeds)
    tn = sum(s["trained_ndec"] for s in seeds)
    bf = sum(s["base_fallback"] for s in seeds)
    bn = sum(s["base_ndec"] for s in seeds)

    # (2) base's fallback rate when it LOSES the seat (trained out-places it) vs not.
    lost = [s for s in seeds if s["place_delta"] > 0]
    notlost = [s for s in seeds if s["place_delta"] <= 0]

    # (3a) restrict to pairs where BOTH arms parsed "cleanly" (fallback rate ≤ τ)
    #      and re-run the placement sign test there. Sensitivity over τ.
    subsets = []
    for tau in (0.10, 0.20, 0.34):
        S = [s for s in seeds if s["trained_fbrate"] <= tau and s["base_fbrate"] <= tau]
        st = two_sided_sign_test([s["place_delta"] for s in S])
        subsets.append({
            "clean_threshold_fallback_rate": tau,
            "n_pairs_both_clean": len(S),
            "of_total": num_seeds,
            "seeds": [s["seed_index"] for s in S],
            "placement_sign_test": st.to_dict(),
            "trained_mean_rank": _mean([s["trained_rank"] for s in S]),
            "base_mean_rank": _mean([s["base_rank"] for s in S]),
        })

    # (3b) split seeds by the parse-fail GAP (base − trained) into low/high halves;
    #      if trained's placement edge lives only in the high-gap half, it is
    #      mechanical; if it survives in the low-gap half, there is a strategic part.
    ordered = sorted(seeds, key=lambda s: s["fbgap"])
    half = len(ordered) // 2
    low_gap, high_gap = ordered[:half], ordered[half:]
    low_st = two_sided_sign_test([s["place_delta"] for s in low_gap])
    high_st = two_sided_sign_test([s["place_delta"] for s in high_gap])

    trained_better = [s for s in seeds if s["place_delta"] > 0]
    coincide = [s for s in trained_better if s["fbgap"] > 0]

    # Headline heuristic (descriptive, spelled out so the numbers govern):
    tau20 = subsets[1]
    strat = tau20["placement_sign_test"]
    if tau20["n_pairs_both_clean"] >= 5 and strat["n_positive"] > strat["n_negative"]:
        headline = ("STRATEGIC COMPONENT SURVIVES — trained still out-places base "
                    "on the clean-parse subset")
    elif low_st.n_positive > low_st.n_negative and low_st.n_nonzero >= 3:
        headline = ("MIXED — trained's placement edge persists even where the "
                    "parse-fail gap is small, so it is not purely mechanical")
    elif tau20["n_pairs_both_clean"] < 3:
        headline = ("PREDOMINANTLY MECHANICAL / INSEPARABLE — base parses cleanly "
                    "too rarely to observe it play a clean game, so a strategic "
                    "edge cannot be isolated from JSON-fluency at this n")
    else:
        headline = ("PREDOMINANTLY MECHANICAL — trained's edge concentrates where "
                    "base's fallback rate is high")

    return {
        "note": ("DESCRIPTIVE/secondary, added at reviewer (Nova) request. 'fallback "
                 "rate' = MODEL parse_fail_count / n_decisions = fraction of a game's "
                 "MODEL turns that fell back to a safe Hold. Does NOT change the "
                 "pre-registered primary B1 verdict."),
        "campaign_fallback_rate": {
            "trained": f"{tf}/{tn} ({tf/tn:.1%})" if tn else "0/0",
            "base": f"{bf}/{bn} ({bf/bn:.1%})" if bn else "0/0",
        },
        "base_fallback_when_losing": {
            "n_seeds_trained_outplaced_base": len(lost),
            "mean_base_fallback_rate_when_losing": _mean([s["base_fbrate"] for s in lost]),
            "n_seeds_base_not_outplaced": len(notlost),
            "mean_base_fallback_rate_when_not_losing": _mean([s["base_fbrate"] for s in notlost]),
        },
        "clean_parse_subset_sensitivity": subsets,
        "parse_fail_gap_split": {
            "low_gap_half": {"n": len(low_gap),
                             "seeds": [s["seed_index"] for s in low_gap],
                             "placement_sign_test": low_st.to_dict()},
            "high_gap_half": {"n": len(high_gap),
                              "seeds": [s["seed_index"] for s in high_gap],
                              "placement_sign_test": high_st.to_dict()},
        },
        "edge_coincides_with_mechanical_gap": (
            f"{len(coincide)}/{len(trained_better)}"
            if trained_better else "0/0"
            ) + " of trained-out-placed-base seeds also had base noisier than trained",
        "headline": headline,
    }


def _openskill_standing(rows: list[dict]):
    """Descriptive OpenSkill μ−3σ (trained-MODEL vs base-MODEL as two
    identities). Corroborating only; returns None if openskill is absent."""
    try:
        from foedus.rating import RatingSystem
        from foedus.scoring import MatchResult
    except Exception:
        return None
    rs = RatingSystem()
    for r in rows:
        n = len(r["final_scores"])
        identities = []
        for seat in range(n):
            role = r["role_by_seat"][seat]
            if role == "MODEL":
                identities.append(f"MODEL({r['arm']})")
            else:
                identities.append(role)
        # Build a MatchResult from the banked outcome (ranks from competition).
        ranks = competition_ranks(r["final_scores"], r["eliminated"])
        mr = MatchResult(rank={i: ranks[i] for i in range(n)}, payout={},
                         final_scores={i: r["final_scores"][i] for i in range(n)},
                         detente=r["detente_reached"], solo_winner=None)
        rs.update(mr, identities=identities)
    return [{"identity": ident, "mu": round(rt.mu, 3),
             "sigma": round(rt.sigma, 3), "conservative": round(rt.conservative, 3)}
            for ident, rt in rs.leaderboard()]


def analyze(run_dir: Path) -> dict:
    plan = json.loads((run_dir / "phaseb_plan.json").read_text())
    rows = _read_rows(run_dir / "sweep.jsonl")
    expected = plan["num_games"]
    # COVERAGE GUARD: must have parsed every banked game before reporting.
    assert_coverage(len(rows), expected, "phaseb sweep rows", min_frac=1.0)

    by_seed: dict[int, dict[str, dict]] = {}
    for r in rows:
        by_seed.setdefault(r["seed_index"], {})[r["arm"]] = r

    num_seeds = plan["num_seeds"]
    # Pairing invariants (fail loud — a broken pair is not analyzable).
    for i in range(num_seeds):
        pair = by_seed.get(i, {})
        if set(pair) != {"trained", "base"}:
            raise SystemExit(f"seed {i}: incomplete pair {sorted(pair)}")
        if pair["trained"]["board_fingerprint"] != pair["base"]["board_fingerprint"]:
            raise SystemExit(f"seed {i}: arms saw different boards")
        if pair["trained"]["role_by_seat"] != pair["base"]["role_by_seat"]:
            raise SystemExit(f"seed {i}: arms had different seat layouts")

    # --- per-seed paired quantities -----------------------------------------
    b1_place_delta, b1_score_delta = [], []
    b2_golf_score_delta, b2_golf_place_delta = [], []
    model_win = {"trained": 0, "base": 0}
    golf_win = {"trained": 0, "base": 0}
    golf_elim = {"trained": 0, "base": 0}
    model_score = {"trained": [], "base": []}
    model_place = {"trained": [], "base": []}
    golf_score = {"trained": [], "base": []}
    golf_place = {"trained": [], "base": []}
    anchor_score = {"trained": [], "base": []}
    model_parse = {"trained": {"fail": 0, "n": 0}, "base": {"fail": 0, "n": 0}}
    per_seed_table = []

    for i in range(num_seeds):
        pair = by_seed[i]
        ms = pair["trained"]["model_seat"]
        gs = pair["trained"]["golf_seat"]
        anchor_seats = pair["trained"]["anchor_seats"]
        row = {"seed_index": i, "model_seat": ms, "golf_seat": gs}
        ranks = {}
        for arm in ("trained", "base"):
            r = pair[arm]
            fs = r["final_scores"]
            rk = competition_ranks(fs, r["eliminated"])
            ranks[arm] = rk
            model_score[arm].append(fs[ms])
            model_place[arm].append(rk[ms])
            golf_score[arm].append(fs[gs])
            golf_place[arm].append(rk[gs])
            anchor_score[arm].extend(fs[s] for s in anchor_seats)
            if ms in r["winners"]:
                model_win[arm] += 1
            if gs in r["winners"]:
                golf_win[arm] += 1
            if gs in r["eliminated"]:
                golf_elim[arm] += 1
            model_parse[arm]["fail"] += r["parse_fail_count"]
            model_parse[arm]["n"] += r["n_decisions"]
            row[f"model_score_{arm}"] = fs[ms]
            row[f"model_rank_{arm}"] = rk[ms]
            row[f"golf_score_{arm}"] = fs[gs]
        # B1 deltas (positive = trained better)
        b1_place_delta.append(ranks["base"][ms] - ranks["trained"][ms])
        b1_score_delta.append(pair["trained"]["final_scores"][ms]
                              - pair["base"]["final_scores"][ms])
        # B2 deltas (positive = trained field contained Golf better)
        b2_golf_score_delta.append(pair["base"]["final_scores"][gs]
                                  - pair["trained"]["final_scores"][gs])
        b2_golf_place_delta.append(ranks["trained"][gs] - ranks["base"][gs])
        per_seed_table.append(row)

    b1_place = two_sided_sign_test(b1_place_delta)
    b1_score = two_sided_sign_test(b1_score_delta)
    b2_score = two_sided_sign_test(b2_golf_score_delta)
    b2_place = two_sided_sign_test(b2_golf_place_delta)

    result = {
        "match_id": plan["match_id"],
        "num_seeds": num_seeds,
        "num_games": expected,
        "trained_model": plan["trained_model"],
        "base_model": plan["base_model"],
        "anchors": plan["anchors"],
        "freerider_class": plan["freerider_class"],
        "seal": _seal_table(run_dir),
        "B1": {
            "primary_metric": "MODEL placement (competition rank; paired)",
            "placement_sign_test": b1_place.to_dict(),
            "score_sign_test": b1_score.to_dict(),
            "model_score": {a: summary_stats(model_score[a]) for a in ("trained", "base")},
            "model_placement": {a: summary_stats([float(x) for x in model_place[a]]) for a in ("trained", "base")},
            "model_win_tie_rate": {a: f"{model_win[a]}/{num_seeds}" for a in ("trained", "base")},
            "model_parse_fail": {a: f"{model_parse[a]['fail']}/{model_parse[a]['n']}"
                                 for a in ("trained", "base")},
            "verdict": _verdict(b1_place, better_label="trained beats base",
                                worse_label="base better"),
            "score_corroboration": _verdict(b1_score, better_label="trained higher score",
                                            worse_label="base higher score"),
        },
        "B2": {
            "primary_metric": "Golf final score (paired; lower in trained field = contained)",
            "golf_score_sign_test": b2_score.to_dict(),
            "golf_placement_sign_test": b2_place.to_dict(),
            "golf_score": {a: summary_stats(golf_score[a]) for a in ("trained", "base")},
            "golf_placement": {a: summary_stats([float(x) for x in golf_place[a]]) for a in ("trained", "base")},
            "golf_win_tie_rate": {a: f"{golf_win[a]}/{num_seeds}" for a in ("trained", "base")},
            "golf_elim_rate": {a: f"{golf_elim[a]}/{num_seeds}" for a in ("trained", "base")},
            "anchor_score_mean": {a: summary_stats(anchor_score[a]) for a in ("trained", "base")},
            "verdict": _verdict(b2_score, better_label="trained field contains Golf",
                                worse_label="base field contains Golf"),
        },
        "mechanical_vs_strategic": _mechanical_vs_strategic(by_seed, num_seeds),
        "openskill_descriptive": _openskill_standing(rows),
        "per_seed": per_seed_table,
    }
    return result


def _seal_table(run_dir: Path) -> dict:
    revealed_p = run_dir / "seed_manifest.revealed.json"
    if not revealed_p.exists():
        return {"revealed": False, "note": "campaign not yet revealed"}
    revealed = campaign.SeedManifest.from_dict(json.loads(revealed_p.read_text()))
    ok = campaign.verify(revealed)
    return {
        "revealed": True,
        "match_id": revealed.match_id,
        "domain": revealed.domain,
        "commit": revealed.commit,
        "nonce": revealed.nonce,
        "num_seeds": revealed.num_games,
        "seeds": revealed.seeds,
        "verify_recomputes_commitment": ok,
    }


def _fmt_stat(s: dict, key="mean", nd=2) -> str:
    v = s.get(key)
    return "n/a" if v is None else f"{v:.{nd}f}"


def _fmt(v, nd=2) -> str:
    return "n/a" if v is None else f"{v:.{nd}f}"


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def render_markdown(res: dict) -> str:
    L = []
    L.append("# G1 Phase B — results (sealed, seed-paired trained-vs-base eval)\n")
    L.append("**This is a scientific claim under the full review gate.** Verdicts "
             "below are applied EXACTLY as pre-registered in `prereg.md` — the "
             "sealed commitment was committed before game 0.\n")
    seal = res["seal"]
    L.append("## Seal (commit-reveal, verifiable)\n")
    if seal.get("revealed"):
        L.append(f"- match-id: `{seal['match_id']}`  domain: `{seal['domain']}`")
        L.append(f"- commitment (published pre-match): `{seal['commit']}`")
        L.append(f"- nonce (revealed): `{seal['nonce']}`")
        L.append(f"- seeds ({seal['num_seeds']}, revealed): `{seal['seeds']}`")
        L.append(f"- **verify() recomputes the commitment: "
                 f"{'PASS ✅' if seal['verify_recomputes_commitment'] else 'FAIL ❌'}** "
                 f"(anyone can rerun `foedus.eval.campaign.verify` on "
                 f"`seed_manifest.revealed.json`)\n")
    else:
        L.append("- NOT YET REVEALED (campaign incomplete)\n")

    L.append(f"- N = {res['num_seeds']} paired seeds = {res['num_games']} games")
    L.append(f"- trained = `{res['trained_model']}`  base = `{res['base_model']}`")
    L.append(f"- table = MODEL + Golf(`{res['freerider_class']}`) + anchors "
             f"`{res['anchors']}`\n")

    # B1
    b1 = res["B1"]
    L.append("## B1 — does the trained entrant beat its own base?\n")
    L.append(f"**Verdict: {b1['verdict']}**\n")
    L.append(f"Primary metric: {b1['primary_metric']}.\n")
    st = b1["placement_sign_test"]
    L.append(f"- paired MODEL placement (positive = trained placed better): "
             f"{st['n_positive']} trained-better / {st['n_negative']} base-better / "
             f"{st['n_zero']} tied of {st['n_pairs']} seeds; two-sided sign-test "
             f"p = {st['p_value_two_sided']:.4g}")
    ss = b1["score_sign_test"]
    L.append(f"- corroborating MODEL final-score (positive = trained higher): "
             f"{ss['n_positive']}/{ss['n_negative']}/{ss['n_zero']} "
             f"(pos/neg/tie) of {ss['n_pairs']}; p = {ss['p_value_two_sided']:.4g} "
             f"→ {b1['score_corroboration']}")
    L.append("")
    L.append("| metric | trained | base |")
    L.append("|---|---|---|")
    L.append(f"| mean MODEL score | {_fmt_stat(b1['model_score']['trained'])} | "
             f"{_fmt_stat(b1['model_score']['base'])} |")
    L.append(f"| mean MODEL placement | {_fmt_stat(b1['model_placement']['trained'])} | "
             f"{_fmt_stat(b1['model_placement']['base'])} |")
    L.append(f"| MODEL win/tie rate | {b1['model_win_tie_rate']['trained']} | "
             f"{b1['model_win_tie_rate']['base']} |")
    L.append(f"| MODEL parse-fail (all its calls) | {b1['model_parse_fail']['trained']} | "
             f"{b1['model_parse_fail']['base']} |")
    L.append("")

    # B1 mechanical-vs-strategic decomposition (descriptive lens)
    mv = res["mechanical_vs_strategic"]
    L.append("### B1 interpretation — mechanical (JSON-fluency) vs strategic\n")
    L.append("_Descriptive/secondary lens (added at reviewer request). Does NOT "
             "change the pre-registered B1 verdict above. `fallback rate` = MODEL "
             "`parse_fail_count / n_decisions` = the fraction of a game's MODEL turns "
             "that fell back to a safe Hold. The question: is any 'trained beats "
             "base' mostly 'trained emits valid JSON more often' (mechanical, still a "
             "real distillation win) or 'trained plays better' (strategic)?_\n")
    L.append(f"**Read: {mv['headline']}.**\n")
    L.append(f"1. **Campaign fallback rate per arm (denominated):** trained "
             f"`{mv['campaign_fallback_rate']['trained']}` vs base "
             f"`{mv['campaign_fallback_rate']['base']}`. A large base excess ⇒ much "
             f"of base's disadvantage is its turns collapsing to Hold.")
    bl = mv["base_fallback_when_losing"]
    L.append(f"2. **When base loses the seat** (trained out-placed it on "
             f"{bl['n_seeds_trained_outplaced_base']} seeds): base's mean fallback "
             f"rate was {_pct(bl['mean_base_fallback_rate_when_losing'])} on those "
             f"seeds vs {_pct(bl['mean_base_fallback_rate_when_not_losing'])} on the "
             f"{bl['n_seeds_base_not_outplaced']} seeds it did not lose — i.e. that "
             f"share of its turns on lost seeds were mechanical fallback-Holds, not "
             f"valid-but-weak play.")
    L.append("3. **Strategy-isolating view — restrict to pairs where BOTH arms "
             "parsed cleanly** (fallback rate ≤ τ) and re-run the placement sign "
             "test. If the edge vanishes when base parses cleanly ⇒ mechanical; if "
             "it persists ⇒ strategic.\n")
    L.append("| clean threshold τ | pairs both-clean | trained better / base better / tie | sign p | trained mean rank | base mean rank |")
    L.append("|---|---|---|---|---|---|")
    for sub in mv["clean_parse_subset_sensitivity"]:
        st = sub["placement_sign_test"]
        L.append(f"| ≤{sub['clean_threshold_fallback_rate']:.0%} | "
                 f"{sub['n_pairs_both_clean']}/{sub['of_total']} | "
                 f"{st['n_positive']} / {st['n_negative']} / {st['n_zero']} | "
                 f"{st['p_value_two_sided']:.3g} | "
                 f"{_fmt(sub['trained_mean_rank'])} | {_fmt(sub['base_mean_rank'])} |")
    gap = mv["parse_fail_gap_split"]
    lo, hi = gap["low_gap_half"]["placement_sign_test"], gap["high_gap_half"]["placement_sign_test"]
    L.append("")
    L.append(f"   Split by parse-fail gap (base−trained): **low-gap half** "
             f"(n={gap['low_gap_half']['n']}) trained-better/base-better/tie = "
             f"{lo['n_positive']}/{lo['n_negative']}/{lo['n_zero']} (p={lo['p_value_two_sided']:.3g}); "
             f"**high-gap half** (n={gap['high_gap_half']['n']}) = "
             f"{hi['n_positive']}/{hi['n_negative']}/{hi['n_zero']} (p={hi['p_value_two_sided']:.3g}). "
             f"If trained only wins in the high-gap half, the edge is mechanical.")
    L.append(f"   Coincidence check: {mv['edge_coincides_with_mechanical_gap']}.\n")

    # B2
    b2 = res["B2"]
    L.append("## B2 — does the trained entrant help contain the freerider (Golf)?\n")
    L.append(f"**Verdict: {b2['verdict']}**\n")
    L.append(f"Primary metric: {b2['primary_metric']}.\n")
    gs = b2["golf_score_sign_test"]
    L.append(f"- paired Golf score (positive = trained field held Golf LOWER = "
             f"better containment): {gs['n_positive']} trained-contains / "
             f"{gs['n_negative']} base-contains / {gs['n_zero']} tied of "
             f"{gs['n_pairs']}; two-sided sign-test p = {gs['p_value_two_sided']:.4g}")
    L.append("")
    L.append("| metric | trained field | base field |")
    L.append("|---|---|---|")
    L.append(f"| mean Golf score | {_fmt_stat(b2['golf_score']['trained'])} | "
             f"{_fmt_stat(b2['golf_score']['base'])} |")
    L.append(f"| mean Golf placement | {_fmt_stat(b2['golf_placement']['trained'])} | "
             f"{_fmt_stat(b2['golf_placement']['base'])} |")
    L.append(f"| Golf win/tie rate | {b2['golf_win_tie_rate']['trained']} | "
             f"{b2['golf_win_tie_rate']['base']} |")
    L.append(f"| Golf elimination rate | {b2['golf_elim_rate']['trained']} | "
             f"{b2['golf_elim_rate']['base']} |")
    L.append(f"| mean anchor score (attribution) | "
             f"{_fmt_stat(b2['anchor_score_mean']['trained'])} | "
             f"{_fmt_stat(b2['anchor_score_mean']['base'])} |")
    L.append("")
    L.append("_Attribution: if anchors score HIGHER in the trained field, "
             "containment leans toward coordination/protection; if only the MODEL "
             "gains, it leans toward the trained model being a stronger rival "
             "denying Golf supplies. See caveat 6._\n")

    if res.get("openskill_descriptive"):
        L.append("## OpenSkill μ−3σ (descriptive, NOT the verdict — unpaired)\n")
        L.append("| identity | μ | σ | μ−3σ |")
        L.append("|---|---|---|---|")
        for r in res["openskill_descriptive"]:
            L.append(f"| {r['identity']} | {r['mu']:.2f} | {r['sigma']:.2f} | "
                     f"{r['conservative']:.2f} |")
        L.append("")

    L.append("## Per-seed paired outcomes\n")
    L.append("| seed | MODEL seat | MODEL score (tr/base) | MODEL rank (tr/base) | "
             "Golf score (tr/base) |")
    L.append("|---|---|---|---|---|")
    for r in res["per_seed"]:
        L.append(f"| {r['seed_index']} | {r['model_seat']} | "
                 f"{r['model_score_trained']:.0f} / {r['model_score_base']:.0f} | "
                 f"{r['model_rank_trained']} / {r['model_rank_base']} | "
                 f"{r['golf_score_trained']:.0f} / {r['golf_score_base']:.0f} |")
    L.append("")

    L.append("## Honest caveats (load-bearing — see prereg.md for the full text)\n")
    for c in [
        "Small n (20 paired seeds), ONE archetype / board family.",
        "ONE scripted freerider archetype (DishonestCooperator).",
        "Local q4_K_M quant, single training config (r16/α32, 3 epochs, all seats, "
        "no LR sweep, no assistant-masking — deferred G1 levers). A null ⇒ retrain "
        "differently, not 'distillation can't work'.",
        "The memorization framing IS the test: fresh sealed seeds never in the corpus.",
        "Mechanical-fitness confound (B1): part of any trained edge may be lower "
        "parse-fail (valid JSON ⇒ fewer fallback Holds), not superior strategy — the "
        "per-arm parse-fail row lets a reviewer weigh this.",
        "B2 attribution: stronger-rival vs genuine-coordination is only partially "
        "disentangled by the anchor-score signal at this n / one board family.",
        "LLM stochasticity: boards are reproducible (fingerprinted); MODEL text is not "
        "(ollama defaults). Pairing controls conditions; the sign test averages noise.",
    ]:
        L.append(f"- {c}")
    L.append("")
    L.append("_A null is a real, useful result — not tuned away._\n")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-dir", required=True)
    args = p.parse_args(argv)
    run_dir = Path(args.run_dir)
    res = analyze(run_dir)
    (run_dir / "results.json").write_text(json.dumps(res, indent=2, default=str))
    md = render_markdown(res)
    (run_dir.parent / "results.md").write_text(md)
    print(md)
    print(f"\n[analysis] wrote {run_dir/'results.json'} and "
          f"{run_dir.parent/'results.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
