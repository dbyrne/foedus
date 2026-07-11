# G2 Phase B — pre-registration (sealed, seed-paired, CONSTRAINED trained-vs-base eval)

**Status:** committed BEFORE game 0. This document + the sealed seed commitment
are the pre-registration of a scientific claim; nothing below changes after the
campaign starts.

**Seed commitment (published pre-match):**
`51addb9744069da5031ac1a2f0fa3d4ade8c170ba76831482a1ef32b21d6ad0c`
(SHA-256, domain `foedus-ruleset-v1`, match-id `phaseb-gym-g2-2026-07-11`; see
`run/seed_manifest.sealed.json`). Fresh CSPRNG draw — G1's seeds are NOT
reused. Seeds + nonce sealed on disk (`run/seed_manifest.secret.json`,
operator-private, never committed) and revealed post-campaign to
`run/seed_manifest.revealed.json`, where `foedus.eval.campaign.verify()`
recomputes the commitment.

**Seed-disjointness (asserted at seal, scripted):** the drawn seeds were
checked disjoint from (a) the 8 canonical-campaign-v1 seeds and (b) the 4
canonical-sonnet-arm seeds — the 12 games that produced the ENTIRE training
corpus — and (c) G1 Phase B's 20 sealed eval seeds (proof of no-reuse). The
check is `_assert_seed_disjointness` in `scripts/foedus_phaseb_paired_eval.py`
(hard-abort on overlap or an unreadable manifest), recorded in
`run/phaseb_plan.json → seed_disjointness`, re-run on every `--resume`, and
re-asserted post-reveal from the PUBLIC manifests by
`scripts/foedus_g2_residual_analysis.py`.

## What G2 changes vs G1 — and the claim under test

G1's B1 verdict (`REAL`, p=0.03125) was **predominantly MECHANICAL**: the
untrained base emitted invalid JSON on ~51% of its turns (falling back to safe
Holds), never parsed a single clean game, and 0/20 pairs allowed a
strategy-isolating comparison. G2 removes that confound at the root:
**constrained decoding ON for BOTH arms** (`--constrained`) — every
negotiate/orders call carries the per-phase JSON schema
(`foedus.agents.llm.schema`, G2a-validated: accepts 716/716 corpus teacher
decisions; base structural fallback 90.6%→0.0% in real games; residual
semantic illegality comparable across arms, 17.2% vs 18.8%) via ollama
structured output. Both models are grammar-forced to structurally-valid
decisions; all strategic values stay free.

**The claim under test (B1):** with JSON-fluency mechanically equalized, does
`foedus-entrant-v1` (distilled from 12 high-coordination Sonnet games) place
better than `foedus-base-v1` (identical untrained base weights, identical
q4_K_M serve path) in the MODEL seat on fresh sealed games? **Whatever
placement gap survives is strategy.**

**Pre-registered honest framing (BOTH outcomes are decisive findings):**
- **B1 NULL/collapses** ⇒ distilling 12 games into a 3B taught *format*, not
  *strategy* — G1's edge was JSON-fluency; steer: more data / RL / bigger base.
- **B1 REAL** ⇒ genuine strategic learning survived removing the mechanical
  channel.
Neither outcome is tuned away.

## Design — identical to G1 Phase B except constrained decoding

Everything below is byte-for-byte the G1 design (see
`docs/research/2026-07-10-gym-g1/phase-b/prereg.md` for full rationale):

- **Table:** `[MODEL, Golf (DishonestCooperator), Cooperator, TitForTat]`;
  deterministic scripted opponents; Ruleset-v1 board (4 players, 12 turns,
  continental_sweep, radius 2, détente 8).
- **N = 20 sealed seeds × 2 arms = 40 games**, seed-paired: byte-identical
  boards asserted per arm via sealed `board_fingerprint` (abort on mismatch);
  post-run pair-consistency re-check.
- **Seat rotation:** `model_seat = seed_index % 4` (each position 5 times).
- **Fresh `LLMDiplomat` per game** (no cross-game memory, recip OFF, campaign
  OFF — so no self-note call exists; the constrained wrapper would pass a
  self-note through unconstrained by design anyway).
- **$0 API:** MODEL seats are `LLMDiplomat` + explicit local
  `OllamaClient` wrapped in `PhaseConstrainedClient`; anthropic/claude-cli
  unreachable from the runner; ANTHROPIC_* stripped in launch/resume scripts.
- **Sealed + crash-resumable:** commit-reveal seal, banked-only `--resume`
  (constrained flag + models + config verified against the sealed secret on
  every resume).
- **NEW (G2): per-game MODEL decision banking** — each (seed, arm) writes
  `run/decisions/decisions_seed{i}_{arm}.jsonl` (turn/phase/raw_response/
  fell_back/n_coerced; no prompts) so the confound decomposition over the
  sealed campaign itself is reviewable.

## Pre-registered verdict rules (identical statistics to G1)

Two-sided exact binomial sign test over N paired per-seed deltas (ties
dropped), α = 0.05; positive delta = trained better.

### B1 — beats-own-base ON A MECHANICALLY-CLEAN BASIS (THE strategy verdict)

- **PRIMARY:** paired MODEL **placement** delta = `rank(base) − rank(trained)`
  per seed. Sign test.
- **Corroborating (must not contradict a positive verdict):** paired MODEL
  final-score delta; MODEL win/tie rate per arm.
- **Descriptive:** OpenSkill μ−3σ (unpaired; never the verdict).
- **Verdict (applied exactly as written):**
  - **REAL — trained beats base (strategy)** iff PRIMARY p < 0.05, trained favored.
  - **SUGGESTIVE** iff 0.05 ≤ p < 0.20, trained favored in majority of non-zero pairs.
  - **NULL** iff neither direction significant, pairs ~balanced ⇒ format-not-strategy.
  - **BASE-BETTER** iff significant in the base direction.

### B2 — freerider containment (completeness; same 4-way rules as G1)

PRIMARY: paired Golf-score delta = `score_golf(base_field) −
score_golf(trained_field)`; corroborating Golf placement / win-tie /
elimination; anchor-score attribution signal reported, not gated.

### Mandatory mechanical-cleanliness report (gate on interpretation, not on running)

From `run/decisions/` via `scripts/foedus_g2_residual_analysis.py` (coverage-
guarded: every decisions file present, row counts match banked `n_decisions`):

- **Per-arm STRUCTURAL fallback** (raw not schema-valid) — expected ~0 both
  arms. If materially non-zero, the constraint failed and B1 is NOT read as a
  pure strategy verdict (reported as such, honestly).
- **Per-arm RESIDUAL semantic illegality** (schema-valid, geometrically illegal,
  parser-coerced): per-decision (of schema-valid) and per-emitted-order rates.
  G2a probe baseline: base 17.2%/8.6%, entrant 18.8%/17.9% — re-reported over
  the sealed campaign (the G2a caveat: probe n=64/cell).
- **Comparison to G1** (unconstrained): per-arm parse-fallback G1 vs G2, and
  the fate of G1's B1 verdict on the clean basis.

## Scale + ops

40 games. G1 ran 14 s/game (9.4 min total); constrained decoding adds grammar
overhead (G2a probe: ~1–3 min/game at 8 turns incl. both-condition replays) —
budget **≤ ~2 h expected; operational cap 3 h** (beyond that: investigate, do
not blindly continue). Detached launch (`setsid`, log + PID, `run/launch.sh`),
guarded crash-resume (`run/resume.sh`, no-op if revealed or a runner is alive).
Prior sealed run dirs READ-ONLY; `.nexus-mcp.json` untouched.

## Honest caveats (pre-registered)

1. **Small n, one archetype** — 20 paired seeds, one board family; no claim
   beyond it.
2. **One scripted freerider archetype** (B2).
3. **Local q4_K_M quant, single training config** (G1's: r16/α32, 3 epochs,
   all-seats). A NULL ⇒ this corpus/recipe taught format, not strategy — not
   "distillation can't work".
4. **Residual illegality is NOT forced to zero** — only structural validity is.
   The residual channel is measured per arm; near-parity (per G2a) is what
   licenses the strategy reading. If the campaign shows a large per-arm
   asymmetry, that asymmetry is reported as a bounded mechanical residue on
   the verdict.
5. **Constraint could alter play style** — a grammar changes the sampling
   distribution. Mitigation: identical constraint on BOTH arms (any distortion
   is shared), and G2a showed entrant constrained ≈ unconstrained on every
   measured rate.
6. **LLM stochasticity** — boards reproducible (fingerprinted), MODEL text not
   (ollama defaults); pairing + sign test average the noise, as in G1.

## Gate

Full two-reviewer + Nova audit on results; no self-merge, no self-review as
the gate. Nova notified at (a) seal published + launch (this commit) and
(b) completion + results.
