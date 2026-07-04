# Plan — Cross-game memory: does a Sonnet table LEARN to coordinate across games? (2026-07-03)

Paired with the eventual results doc `docs/research/2026-07-03-crossgame-memory-experiment.md`.
This is the implementation plan; the design rationale lives inline in the code and in the results doc.

## The question
PR #37 proved a capability gradient: sonnet seats + the reciprocation ledger dethrone the
DishonestCooperator freerider 3-of-4 (subsidy −78%, first LLM↔LLM coalitions). The one loss (seed 3)
was **coordination-never-formed** — zero Support declarations all game, atomized blowout. Every game
started from a blank slate. **If agents carry compact memory of prior games, does the table learn —
do atomized losses become coalitions next game?** This is also the recurring-opponent setting a
public leaderboard arena creates.

## Arms (pre-declared; no iteration after data starts)
- **Arm A (baseline)** = PR #37's four independent games. ALREADY RUN — reuse. Copied durably to the
  coder scratchpad; key numbers committed into the results doc.
- **Arm B (campaign)** = the SAME seeds 0→1→2→3 played SEQUENTIALLY by persistent agents carrying
  cross-game memory. Same protocol: 8 turns, map-radius 1, `--llm-seats 0,1,2 --heuristics
  DishonestCooperator --recip-ledger --backend claude-cli --model sonnet`, **CLI timeout pinned to
  180s** for pairing with Arm A's handicap.

## Part 1 — timeout configurability (small, first)
`ClaudeCLIClient` per-call timeout configurable via `FOEDUS_LLM_CLI_TIMEOUT` (seconds), **new default
300** (kills PR #37's 18%-of-decisions 180s-timeout Hold handicap going forward). Precedence:
explicit `timeout=` arg > env > 300. Bad / empty / non-positive env → default. TDD the env parsing.

## Part 2 — cross-game memory
1. **Campaign mode** (`--campaign`): REUSE the same LLMDiplomat instances across the N games; seat
   identities persist (seat s is the same agent every game; freerider always seat 3).
2. **Between games, each agent's memory gains a compact per-game record**, two components:
   - **Harness-computed neutral facts** (counts only, no advice): final scores + your rank; per
     opponent — declared-ally-toward-you turns, your supports of them, declared support-intents toward
     your units visible to you, whether any pact/breach involved you.
     - *Fog note:* executed "they supported my units" is NOT fog-observable (`SupportRound` is
       set-valued; the fog view exposes no executed-order data — the same constraint `memory.py`
       already documents). So we count the fog-legal proxy: inbound **Support intents** that were
       visible to this seat. Labeled precisely as declared-intents, never as executed support.
   - **The agent's OWN post-game note** (self-authored): one extra LLM call per agent after each game
     — "Facts: <neutral record>. Write ≤80 words to your future self for the next game with these
     same opponents." Stored **verbatim**, exempt from neutrality (it is model output), prepended next
     game.
   - Subsequent games render a **"PRIOR GAMES (your records)"** section: per past game the neutral
     facts + the verbatim note. Section hard-capped to the last 3 games to bound prompt growth.
3. **Fog-legality unchanged** — everything derives from the seat's own views/outcomes.
   **Neutrality tests**: the harness-computed text passes the leading-words denylist; the self-note
   is exempt but stored/rendered verbatim.
4. **Persist everything** per game into the out-dir (`campaign_memory_game{g}_seat{s}.json`) for
   auditability: we must be able to read WHAT it told itself and whether behavior followed.

## New metric (first-class)
**LLM↔LLM supports** — Support orders whose target unit belongs to *another LLM seat* (coordination
formation). Added to `foedus/eval/memory_metrics.py`; run over BOTH Arm A (retroactively, from its
decision logs) and Arm B.

## Falsifiable bar (pre-declared)
- **Primary (learning)**: across campaign games 2–4, LLM↔LLM supports/game EXCEED the Arm A mean AND
  the freerider wins ≤1 of games 2–4. Special attention to seed 3 (Arm A's atomized blowout).
- **Mechanism**: subsidy stays ≤ Arm A's (no seduction regression); self-notes visibly reference
  non-reciprocation/coordination (legible learning).
- **Anti-pattern, report honestly**: game-1 ≈ games-2-4 (flat) → memory didn't teach; subsidy rises →
  memory hurt. No re-runs, no prompt tweaks after start.

## Implementation checklist (TDD, RED committed before impl)
1. [ ] Part 1: `FOEDUS_LLM_CLI_TIMEOUT` (default 300) + env-parse tests.
2. [ ] `campaign_memory.py`: GameFacts / OpponentGameFacts / GameRecord / CampaignMemory (cap) +
       `build_game_facts` + `to_dict`/`from_dict` round-trip.
3. [ ] `ReciprocationMemory`: `their_support_intent_toward_me` fog-legal accumulation +
       non-mutating getter. (recip-arm prompt stays byte-identical — new field never rendered there.)
4. [ ] `render.py`: `render_game_facts` (neutral, denylist), `render_campaign_record` (verbatim
       note), `render_self_note_prompt`, `campaign_memory` param on `render_negotiation_prompt`.
5. [ ] `LLMDiplomat`: campaign toggle (arg > `FOEDUS_LLM_CAMPAIGN` env), decoupled recip rendering,
       `reset_for_new_game`, `finalize_game`, `_write_self_note`.
6. [ ] Harness `--campaign`: reuse agents, reset each game, `agents_by_seat` param on
       `run_one_llm_game`, finalize + persist per game.
7. [ ] `memory_metrics.py`: LLM↔LLM supports first-class + scorecard CLI line.
8. [ ] Full suite green; failure set == origin/main baseline.
9. [ ] Two-reviewer inline (Sonnet + Opus); address findings.
10. [ ] Run Arm B (background, ~4.5h, budget ~210 sonnet calls).
11. [ ] Results doc: Arm B vs Arm A per-seed scorecard + verbatim self-notes + honest verdict.
12. [ ] PR `--base main`; notify.

## Guardrails (hard-won)
`uv run --extra llm`. No scaling / no opus seats / pause-don't-retry on rate limits. Do NOT touch
`.nexus-mcp.json`. Colorblind-safe output (David is red/green colorblind — labels/symbols, not
red-vs-green). Session pinned at dispatch → background-run parking is safe.
