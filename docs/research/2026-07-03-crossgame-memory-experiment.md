# Cross-game memory — does a Sonnet table LEARN to coordinate across games? (2026-07-03)

Paired with `docs/plans/2026-07-03-crossgame-memory.md`. Follow-up to the strong-model coordination
probe (`docs/research/2026-07-03-strong-model-coordination-probe.md`, PR #37).

> **STATUS: Arm B run in progress.** Arm A (baseline) numbers below are final (PR #37 data,
> re-scored with the new extractor). Arm B numbers + the verdict are filled once the campaign
> completes. This header is removed at that point.

## The question (the earned rung)
PR #37 proved a capability gradient: Sonnet seats + the neutral reciprocation ledger dethrone the
DishonestCooperator freerider 3-of-4 (subsidy −78%, first-ever LLM↔LLM mutual-support coalitions),
where a naive 14b table lost 4/4. **The one loss (seed 3) is the residual failure mode: coordination
never FORMED** — zero Support declarations by anyone all game, atomized play, freerider blowout.
Every game there started from a blank slate.

**Does compact memory of PRIOR GAMES teach the table to coordinate — do atomized losses become
coalitions next game?** This is exactly the recurring-opponent setting a public leaderboard arena
creates, so the memory format built here becomes part of the standard entrant scaffold.

## Design (pre-declared; no iteration after data started)
- **Arm A (baseline)** — PR #37's four *independent* games (fresh agents each game), seeds 0–3.
  Reused, not re-run.
- **Arm B (campaign)** — the SAME seeds 0→1→2→3 played SEQUENTIALLY by *persistent* agents carrying
  cross-game memory (harness-computed neutral per-game facts + each agent's own ≤80-word self-note,
  stored verbatim and prepended next game, capped to the last 3 games).

Both arms: 8 turns, map-radius 1, `--llm-seats 0,1,2 --heuristics DishonestCooperator --recip-ledger
--backend claude-cli --model sonnet`, **CLI timeout pinned 180s** (Arm B pinned to Arm A's handicap
for a clean pairing; the new default is 300s going forward). Freerider = seat 3 in every game.

## New metric (first-class, applied identically to both arms)
**LLM↔LLM supports** — Support orders whose target unit belongs to *another LLM seat* (coalition
formation). PR #37 saw this only qualitatively; here it is measured. Computed from decision logs, so
Arm A is scored retroactively with the same extractor.

## Falsifiable bar (pre-declared)
- **Primary (learning signal)**: across campaign games 2–4 (seeds 1,2,3), LLM↔LLM supports/game
  EXCEED the Arm A mean (**0.75**), AND the freerider wins ≤1 of games 2–4. Special attention to
  seed 3 (Arm A's atomized blowout).
- **Mechanism**: subsidy stays ≤ Arm A's (**1.50/game** — no seduction regression), and the
  self-notes visibly reference non-reciprocation / coordination (legible, not coincidental learning).
- **Anti-patterns, reported honestly**: game-1 ≈ games-2-4 (flat) → memory didn't teach; subsidy
  RISES → memory hurt. No re-runs, no prompt tweaks after start.

## Arm A (baseline) — final, re-scored with the new extractor
Freerider wins **1/4** (seed 3); mean margin **+3.58**; mean subsidy **1.50/game**; mean **LLM↔LLM
supports 0.75/game**; parse-fail 21.8% (18% of that was 180s-timeout forced Holds, not true parse
failure — see PR #37).

| seed | freerider | LLM mean | margin | outcome | subsidy | LLM↔LLM supports |
|---|---|---|---|---|---|---|
| 0 | 15.0 | 12.7 | +2.3 | LLM held | 0 | **2** |
| 1 | 15.0 | 14.3 | +0.7 | LLM held | 3 | **0** |
| 2 | 12.0 | 14.0 | −2.0 | LLM held | 3 | **1** |
| 3 | 23.0 | 9.7 | +13.3 | **freerider WON** | 0 | **0** |

Note the coordination signal tracks the outcome: the seed-3 blowout had **zero** LLM↔LLM supports
(atomized), consistent with PR #37's "coordination never formed" reading.

## Arm B (campaign) — _pending run completion_
_Scorecard table (per game + vs same-seed Arm A), subsidy, LLM↔LLM supports trajectory, stance-
toward-freerider trajectory, parse-fail split (timeouts vs true), and verbatim self-note samples go
here._

## Verdict vs the bar — _pending_
_Honest call filled after scoring. If flat (game-1 ≈ games-2-4), report memory didn't teach; if
subsidy rose, report memory hurt._
