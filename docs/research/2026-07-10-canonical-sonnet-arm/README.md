# Sonnet arm (4 games, fixed engine) — answers the open S1.5 question

**Match id:** `canonical-sonnet-arm-2026-07-10` · **Milestone:** M-foedus-canonical-sonnet-arm

This is the pre-registered contingency arm from the Haiku re-run
(`docs/research/2026-07-10-canonical-haiku-rerun/`, PR #49): the Haiku table
barely attempted cross-player coordination (2 LLM↔LLM supports across 8
games vs run #1's 79), so the core S1.5 question — does coordinated
punishment pay once it reaches the resolver? — was still open. This run puts
a **Sonnet** table (coordination volume known to be high from run #1) on the
same fixed engine (post-#47, `require_dest` parser fix) to test it directly.

> Board: 4 seats · 12 turns · map radius 2 · `continental_sweep` · détente
> threshold 8 (engine default). Toggles: reciprocation ledger ON · campaign
> memory ON · retreats OFF · LLM decision timeout 300 s · **parallel seat
> calls ON, `FOEDUS_PARALLEL_SEATS_WORKERS=3`** (all 3 LLM seats concurrent;
> see `run/campaign_plan.json`'s `parallel_seats` field). Roster: 3
> **Sonnet** entrants (`claude-cli --model sonnet`) + 1
> `DishonestCooperator` house freerider. Seats rotate by the §7.4 cyclic
> Latin square; seeds are commit-reveal sealed (§7.5). Rating: OpenSkill
> (Plackett-Luce), one identity per entrant, conservative μ − 3σ. **4
> games** (cost control — David's call, since Sonnet's coordination volume
> exercises the punishment pipeline roughly as much per game as the entire
> 8-game Haiku run).

## Primary question (pre-registered)

With a high-coordination (Sonnet) table on the fixed engine, does
coordinated punishment convert, and does the table contain the freerider?
Report the punishment-conversion pipeline (proposed → executed → paid), the
LLM↔LLM cross-player support volume, and pin-Support usage using the same
S1 tooling (coverage-guarded) so this run is directly comparable to run #1
and the Haiku re-run — the decisive artifact is the **three-way comparison**
across all three runs.

## Directory layout

Same schema as run #1 and the Haiku re-run
(`docs/research/2026-07-04-canonical-campaign-v1/README.md`):

| Path | What it is |
|---|---|
| `campaign_plan.json` | The full pre-registered plan: board params, roster, per-game seat→entrant rotation, freerider seat per game, and the `parallel_seats` concurrency setting the match ran under. |
| `seed_manifest.sealed.json` | The **commitment** (SHA-256) published *before* any game — `commit` only, seeds withheld. |
| `seed_manifest.revealed.json` | The **reveal**: the seed list + nonce, published after the match. `verify()` recomputes the commitment. |
| `sweep.jsonl` | One record per game (entrant-identity–labelled `agents`, `final_scores`, `winners`, rotation, wall-clock). |
| `telemetry.jsonl` | Per-game betrayals, pact breaches, reputation, and per-seat decision + parse-fail counts. |
| `decisions_game{g}_seat{s}.jsonl` | Every LLM decision that game/seat: `prompt`, `raw_response`, `parsed`, `fell_back`, `n_coerced`. |
| `transcript_game{g}.md` | Human-readable per-game scheming transcript. |
| `campaign_memory_game{g}_seat{s}.json` | Cross-game memory carried into later games. |
| `standings.json` | Final OpenSkill leaderboard (μ, σ, μ−3σ) per entrant identity. |
| `run_summary.json` | Wall-clock (match + per game), decision + parse-fail totals, seed commitment. |
| `launch.sh` / `resume.sh` | The exact commands used to launch the match / the crash-resume path (env vars included). This match completed in a single `launch.sh` leg (`run_summary.json`'s `resumed: false`) — `resume.sh` was installed behind a guarded `@reboot` autoresume and dry-fire-tested against the live run, but never actually invoked. |
| `timing.log`, `launch.log`, `run.stdout.log`, `run.stderr.log` | Raw process logs from `launch.sh` (start/end timestamps, per-game console output, the `ClaudeCLIClient` argv lines). Not needed to reproduce anything — `run_summary.json` / `sweep.jsonl` already carry the same information structured; kept for a from-scratch audit trail. |

Top-level `scorecard.json` / `autopsy-s1.json` are the `--json` outputs of
`foedus_canonical_scorecard.py` / `foedus_s1_autopsy.py` against `run/`,
kept alongside `results.md` for a from-scratch re-derivation without
re-running the tools.

## Verifying the seeds (anyone can do this)

```python
PYTHONPATH=. python3 - <<'PY'
import json
from foedus.eval import campaign
m = campaign.SeedManifest.from_dict(
    json.load(open("run/seed_manifest.revealed.json")))
sealed = json.load(open("run/seed_manifest.sealed.json"))
assert m.commit == sealed["commit"], "commit changed between seal and reveal!"
assert campaign.verify(m), "revealed seeds do not hash to the commitment!"
print("OK — seeds were fixed in advance:", m.seeds)
PY
```

## Reproducing the analysis

```sh
PYTHONPATH=. python3 scripts/foedus_canonical_scorecard.py --out-dir docs/research/2026-07-10-canonical-sonnet-arm/run
PYTHONPATH=. python3 scripts/foedus_compute_ratings.py docs/research/2026-07-10-canonical-sonnet-arm/run/sweep.jsonl
```

See `results.md` for the full three-way comparison (run #1 / Haiku re-run /
this arm) and the honest verdict, including a live confound this run does
**not** resolve (§6 of `results.md`).
