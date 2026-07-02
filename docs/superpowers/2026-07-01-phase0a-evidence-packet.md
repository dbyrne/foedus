# Phase 0a — evidence packet (reviewer audit)

**Milestone:** `M-foedus-arena-legibility-0a`  •  **Branch:** `feature/M-foedus-arena-legibility-0a` (off `main`)
**Coder session:** `732a7e3f` (claude-sonnet-5)  •  **Reviewer:** Opus 4.8 (this session)
**Date:** 2026-07-01  •  **Verdict: PASS at the code level** (one review nit fixed). Behavioral
exit gate (re-run 4-agent game) still pending.

## Scope delivered (maps to the 0a brief)
- **F1 economy transparency:** `foedus/render_common.py` — `CAPTURE_RULE_TEXT`, `node_label`
  (embeds `$value`), `income_ledger`/`render_income_ledger` (owned centers + per-turn total +
  occupying-not-converted + last-turn delta + build turns). New `GameState.last_turn_score_delta`
  (`core.py`), populated in `resolve.py`.
- **F2 legibility:** support options annotated with owner+location
  (`Support(target=u3 [P2 @ n25])`); enemy units shown; `render_adjacency_table` (all visible
  nodes); `render_betrayal_ledger`; `render_turn_calendar`.
- **F3 config:** `foedus/presets.py::conflict_forcing_config` (longer game / scarcity); détente
  threshold made reachable; chat cap raised + over-cap now errors visibly (`game_server/session.py`,
  `press.py`); `foedus_press_play.py` + `game_server/render.py` rewired onto `render_common`.
- **Tests:** ~590 new lines — `test_render_common.py` (251), `test_press_play_script.py` (155),
  `test_score_delta.py` (89), `test_presets.py` (48) + additions.

## Gate: test suite
`uv run pytest` on the branch: **664 passed, 1 skipped, 1 failed.**
- The failure — `tests/test_rating.py::test_detente_uses_tied_top_ranks` — **also fails identically
  on `main`** (verified). It is a **pre-existing, stale test**, not a 0a regression: it holds for 2
  turns and expects `detente_reached`, but détente requires active mutual-ALLY consensus
  (`mutual_ally_streak` stays 0 when players only Hold). **Not blocking 0a; fix separately.**
- All new 0a tests pass.

## Correctness verification (the critical claim)
The income ledger must never drift from what the engine pays, or it's worse than nothing. Verified two ways:
1. **Code identity:** `render_common.income_ledger` `per_turn` (lines 133–139) uses the *same*
   filter as `resolve.py` step-8 scoring (lines 702–712): `node_types[n] in (SUPPLY, HOME)` AND
   `ownership==player`, summed via `map.supply_value(n)`. Byte-for-byte the same rule.
2. **Property test:** `test_score_delta.py:79` asserts
   `last_turn_score_delta[p] == scores[p] - before[p]` across turns/players — the ledger's
   "last turn" number is the engine's actual delta, not a re-derivation.
   `per_turn` (steady supply income) and `last_turn_delta` (actual, may include combat bonuses) are
   honestly separated — no misleading claim.

## Review findings
- **[FIXED] `.gitignore` regression:** the coder removed the `.worktrees/` ignore entry (risking
  committed worktree contents). Restored from `main` — commit `8a5c45a`.
- **Constraints honored:** `.nexus-mcp.json` untouched (secret safe); branch off `main`; additive;
  render logic factored into a shared module reusable by the future `janus.llm.render`.
- No PR opened by the coder (branch is local, unpushed).

## Outstanding / recommendations
1. **Behavioral exit gate NOT yet met (evidence before assertion):** the code is verified, but the
   real 0a gate is *re-running the 4-agent game* with the new legible prompt + conflict preset and
   confirming agents capture from turn 1 (no reverse-engineering), reconcile their own scores, and
   make contact. Recommend running this before declaring 0a done.
2. Optional per the two-reviewer rule: a second (Sonnet) reviewer. Low-risk here (presentation +
   one verified correctness claim), so optional.
3. Push branch + open PR to `dbyrne/foedus` when David approves (not done — outward action).
4. Separately fix the stale `test_detente_uses_tied_top_ranks`.

## Behavioral exit-gate result (PASS)
Re-ran the 4-agent playtest against the **branch** code (conflict preset, commit-only, 2 turns)
with **fresh, naive agents** and a rule-light briefing (the prompt, not the briefing, had to teach
capture). Result:
- **4/4 understood move-then-Hold from turn 1** — all cited the stated capture rule and the income
  ledger's "OCCUPYING (not yet converted) — stay put to capture" line; three explicitly reasoned
  "occupying but not converted, so I Hold to lock in the capture."
- **Used the newly-visible per-center values** — P3 identified `6$2` as the board's best center and
  grabbed it; by turn 2 P3 leads (4) precisely because of the value-2 capture.
- **Used adjacency** (P0 defended its home route) and **combat reasoning** (can't dislodge a
  holding defender 1v1).
- **Scores reconcile exactly** with owned-center values: P0=3, P1=3, P3=4, P2=2 (P2 one turn behind
  only because it chose a plain hub node turn 1 — sound positional call, not confusion).
- **Contrast with the first playtest:** 0/4 understood capture, ~3 of 7 turns wasted, scores
  unreconcilable. The F1/F2 legibility fixes work.

Not yet observed (out of 0a scope): actual combat/betrayal emergence — expected, since agents are
still expanding into open centers. That's what **0b** (private stance, joint/conditional intents,
betrayal teeth) + a longer run targets. **0a is behaviorally verified.**
