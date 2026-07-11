# G1 Phase B — results (sealed, seed-paired trained-vs-base eval)

**This is a scientific claim under the full review gate.** Verdicts below are applied EXACTLY as pre-registered in `prereg.md` — the sealed commitment was committed before game 0.

## Bottom line (read this first)

- **B1 — beats-own-base: pre-registered verdict is `REAL — trained beats base (sign test p=0.03125)` — BUT this is PREDOMINANTLY MECHANICAL, not strategic.** The untrained base is so JSON-unfit (falls back to a safe Hold on `234/456 (51.3%)` of its turns, never parses a single clean game, and lands LAST on all 20/20 seeds) that the pre-registered placement test cleanly separates the two — but it cannot separate *learned strategy* from *learned to emit valid orders*. The strategy-isolating view finds **0/20 pairs where the base parsed cleanly**, so no strategic edge can be observed. Read it as: **distillation produced a mechanically-fit local entrant that reliably out-plays its untrained base (trained falls back only `121/470 (25.7%)`) — a real, valuable G1 outcome — NOT a demonstration of superior strategy.**
- **B2 — containment: `NULL — no significant difference (p=0.2668)`.** A table with the trained entrant does NOT contain the freerider (Golf) better than one with the base: mean Golf score 41.7 (trained field) vs 39.4 (base field) — if anything Golf did marginally BETTER against the trained entrant, non-significant. Golf dominates both fields (never eliminated; top OpenSkill μ−3σ by a wide margin) and the anchor-score attribution signal shows no coordination benefit. An honest null.
- **G1 read:** the distill→serve→play loop yields a *mechanically-fit* entrant; **superior strategy and freerider containment are NOT demonstrated** at this n / config. Next steps are the pre-registered retrain levers (fewer epochs / winners-only / assistant-masking) AND a mechanically-fit base control (few-shot or repaired base) so a future B1 can test *strategy* rather than *JSON-fluency*. A null is a real, useful result — reported, not tuned away.

## Seal (commit-reveal, verifiable)

- match-id: `phaseb-gym-g1-2026-07-10`  domain: `foedus-ruleset-v1`
- commitment (published pre-match): `c5a25b271e1e4843766011ef82dcef526b18dd179036cdc4c87259c890019072`
- nonce (revealed): `66a4b8ff8a31e315e217ebb108ee4473`
- seeds (20, revealed): `[639372847246931933, 1839970594324512917, 4626576710564105032, 8907712770557996506, 4034783164285317850, 2338027146699170302, 2574046895833080206, 2108411291163524788, 578424137460431154, 5104953522339238097, 8836717405907922055, 1662204705814762481, 2610203445983164385, 7172147522055120959, 8683433526728125744, 6322717499865223782, 6374103229293578726, 2510003524117943195, 5483099070840259580, 4311658937975593802]`
- **verify() recomputes the commitment: PASS ✅** (anyone can rerun `foedus.eval.campaign.verify` on `seed_manifest.revealed.json`)

- N = 20 paired seeds = 40 games
- trained = `foedus-entrant-v1:latest`  base = `foedus-base-v1:latest`
- table = MODEL + Golf(`DishonestCooperator`) + anchors `['Cooperator', 'TitForTat']`

## B1 — does the trained entrant beat its own base?

**Verdict: REAL — trained beats base (sign test p=0.03125)**

Primary metric: MODEL placement (competition rank; paired).

- paired MODEL placement (positive = trained placed better): 6 trained-better / 0 base-better / 14 tied of 20 seeds; two-sided sign-test p = 0.03125
- corroborating MODEL final-score (positive = trained higher): 13/6/1 (pos/neg/tie) of 20; p = 0.1671 → SUGGESTIVE — leans trained higher score, not significant (p=0.1671)

| metric | trained | base |
|---|---|---|
| mean MODEL score | 17.85 | 11.45 |
| mean MODEL placement | 3.45 | 4.00 |
| MODEL win/tie rate | 2/20 | 0/20 |
| MODEL parse-fail (all its calls) | 121/470 | 234/456 |

### B1 interpretation — mechanical (JSON-fluency) vs strategic

_Descriptive/secondary lens (added at reviewer request). Does NOT change the pre-registered B1 verdict above. `fallback rate` = MODEL `parse_fail_count / n_decisions` = the fraction of a game's MODEL turns that fell back to a safe Hold. The question: is any 'trained beats base' mostly 'trained emits valid JSON more often' (mechanical, still a real distillation win) or 'trained plays better' (strategic)?_

**Read: PREDOMINANTLY MECHANICAL / INSEPARABLE — base parses cleanly too rarely to observe it play a clean game, so a strategic edge cannot be isolated from JSON-fluency at this n.**

1. **Campaign fallback rate per arm (denominated):** trained `121/470 (25.7%)` vs base `234/456 (51.3%)`. A large base excess ⇒ much of base's disadvantage is its turns collapsing to Hold.
2. **When base loses the seat** (trained out-placed it on 6 seeds): base's mean fallback rate was 51% on those seeds vs 52% on the 14 seeds it did not lose — i.e. that share of its turns on lost seeds were mechanical fallback-Holds, not valid-but-weak play.
3. **Strategy-isolating view — restrict to pairs where BOTH arms parsed cleanly** (fallback rate ≤ τ) and re-run the placement sign test. If the edge vanishes when base parses cleanly ⇒ mechanical; if it persists ⇒ strategic.

| clean threshold τ | pairs both-clean | trained better / base better / tie | sign p | trained mean rank | base mean rank |
|---|---|---|---|---|---|
| ≤10% | 0/20 | 0 / 0 / 0 | 1 | n/a | n/a |
| ≤20% | 0/20 | 0 / 0 / 0 | 1 | n/a | n/a |
| ≤34% | 0/20 | 0 / 0 / 0 | 1 | n/a | n/a |

   Split by parse-fail gap (base−trained): **low-gap half** (n=10) trained-better/base-better/tie = 2/0/8 (p=0.5); **high-gap half** (n=10) = 4/0/6 (p=0.125). If trained only wins in the high-gap half, the edge is mechanical.
   Coincidence check: 5/6 of trained-out-placed-base seeds also had base noisier than trained.

## B2 — does the trained entrant help contain the freerider (Golf)?

**Verdict: NULL — no significant difference (p=0.2668)**

Primary metric: Golf final score (paired; lower in trained field = contained).

- paired Golf score (positive = trained field held Golf LOWER = better containment): 4 trained-contains / 9 base-contains / 7 tied of 20; two-sided sign-test p = 0.2668

| metric | trained field | base field |
|---|---|---|
| mean Golf score | 41.70 | 39.40 |
| mean Golf placement | 1.65 | 1.65 |
| Golf win/tie rate | 12/20 | 11/20 |
| Golf elimination rate | 0/20 | 0/20 |
| mean anchor score (attribution) | 33.33 | 34.60 |

_Attribution: if anchors score HIGHER in the trained field, containment leans toward coordination/protection; if only the MODEL gains, it leans toward the trained model being a stronger rival denying Golf supplies. See caveat 6._

## OpenSkill μ−3σ (descriptive, NOT the verdict — unpaired)

| identity | μ | σ | μ−3σ |
|---|---|---|---|
| Golf | 45.77 | 5.01 | 30.74 |
| Cooperator | 35.28 | 4.64 | 21.36 |
| TitForTat | 24.48 | 4.71 | 10.35 |
| MODEL(trained) | 15.49 | 6.07 | -2.71 |
| MODEL(base) | 0.49 | 6.29 | -18.37 |

## Per-seed paired outcomes

| seed | MODEL seat | MODEL score (tr/base) | MODEL rank (tr/base) | Golf score (tr/base) |
|---|---|---|---|---|
| 0 | 0 | 17 / 12 | 4 / 4 | 22 / 22 |
| 1 | 1 | 15 / 12 | 4 / 4 | 46 / 43 |
| 2 | 2 | 8 / 12 | 4 / 4 | 35 / 41 |
| 3 | 3 | 7 / 12 | 4 / 4 | 61 / 60 |
| 4 | 0 | 4 / 12 | 4 / 4 | 37 / 29 |
| 5 | 1 | 19 / 12 | 4 / 4 | 47 / 47 |
| 6 | 2 | 34 / 12 | 1 / 4 | 23 / 23 |
| 7 | 3 | 5 / 12 | 4 / 4 | 23 / 23 |
| 8 | 0 | 25 / 12 | 3 / 4 | 58 / 39 |
| 9 | 1 | 11 / 4 | 4 / 4 | 47 / 56 |
| 10 | 2 | 11 / 12 | 4 / 4 | 23 / 23 |
| 11 | 3 | 23 / 12 | 4 / 4 | 36 / 31 |
| 12 | 0 | 35 / 12 | 3 / 4 | 39 / 32 |
| 13 | 1 | 12 / 12 | 4 / 4 | 58 / 58 |
| 14 | 2 | 25 / 12 | 4 / 4 | 43 / 39 |
| 15 | 3 | 30 / 12 | 2 / 4 | 42 / 42 |
| 16 | 0 | 26 / 15 | 4 / 4 | 49 / 50 |
| 17 | 1 | 10 / 6 | 4 / 4 | 55 / 48 |
| 18 | 2 | 34 / 12 | 1 / 4 | 31 / 34 |
| 19 | 3 | 6 / 12 | 3 / 4 | 59 / 48 |

## Honest caveats (load-bearing — see prereg.md for the full text)

- Small n (20 paired seeds), ONE archetype / board family.
- ONE scripted freerider archetype (DishonestCooperator).
- Local q4_K_M quant, single training config (r16/α32, 3 epochs, all seats, no LR sweep, no assistant-masking — deferred G1 levers). A null ⇒ retrain differently, not 'distillation can't work'.
- The memorization framing IS the test: fresh sealed seeds never in the corpus.
- Mechanical-fitness confound (B1): part of any trained edge may be lower parse-fail (valid JSON ⇒ fewer fallback Holds), not superior strategy — the per-arm parse-fail row lets a reviewer weigh this.
- B2 attribution: stronger-rival vs genuine-coordination is only partially disentangled by the anchor-score signal at this n / one board family.
- LLM stochasticity: boards are reproducible (fingerprinted); MODEL text is not (ollama defaults). Pairing controls conditions; the sign test averages noise.

_A null is a real, useful result — not tuned away._
