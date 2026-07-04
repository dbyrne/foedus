# Canonical Ruleset-v1 campaign — archive + reproduction

The **first official match** run in the ratified standard format
(`docs/design/2026-07-04-ruleset-v1.md`). This directory is a durable,
committed archive: the leaderboard seed, the defector-punishment science
record, **and** the SFT training corpus the gym pipeline
(`M-foedus-gym-pipeline-v0`) consumes. Nothing here is throwaway.

> Board: 4 seats · 12 turns · map radius 2 · `continental_sweep` · détente
> threshold 8 (engine default). Toggles: reciprocation ledger ON · campaign
> memory ON · retreats OFF · LLM decision timeout 300 s. Roster: 3 Sonnet
> entrants (`claude-cli`) + 1 `DishonestCooperator` house freerider. Seats
> rotate by the §7.4 cyclic Latin square; seeds are commit-reveal sealed (§7.5).
> Rating: OpenSkill (Plackett-Luce), one identity per entrant, conservative
> μ − 3σ.

## Directory layout

| Path | What it is |
|---|---|
| `campaign_plan.json` | The full pre-registered plan: board params, roster, per-game seat→entrant rotation, freerider seat per game. |
| `seed_manifest.sealed.json` | The **commitment** (SHA-256) published *before* any game — `commit` only, seeds withheld. |
| `seed_manifest.revealed.json` | The **reveal**: the seed list + nonce, published after the match. `verify()` recomputes the commitment. |
| `sweep.jsonl` | One record per game (entrant-identity–labelled `agents`, `final_scores`, `winners`, rotation, wall-clock). The gym-pipeline / rating input. |
| `telemetry.jsonl` | Per-game betrayals, pact breaches, reputation, and per-seat decision + parse-fail counts. |
| `decisions_game{g}_seat{s}.jsonl` | Every LLM decision that game/seat: `prompt` (system+user), `raw_response`, `parsed`, `fell_back`, `n_coerced`. **The SFT records.** |
| `transcript_game{g}.md` | Human-readable per-game scheming transcript (stances, intents, betrayals, reputation). |
| `campaign_memory_game{g}_seat{s}.json` | Cross-game memory carried into later games: neutral facts + the seat's own verbatim ≤80-word self-note, tagged with the entrant identity. |
| `standings.json` | Final OpenSkill leaderboard (μ, σ, μ−3σ) per entrant identity. |
| `run_summary.json` | Wall-clock (match + per game), decision + parse-fail totals, seed commitment. |
| `scorecard.json` | Output of `foedus_canonical_scorecard.py` — per-game + trajectory + parse-fail split + standings. |

## Verifying the seeds (anyone can do this)

The operator committed to the seed list before playing, so they could not
re-roll a disliked board:

```python
PYTHONPATH=. python3 - <<'PY'
import json
from foedus.eval import campaign
m = campaign.SeedManifest.from_dict(
    json.load(open("seed_manifest.revealed.json")))
sealed = json.load(open("seed_manifest.sealed.json"))
assert m.commit == sealed["commit"], "commit changed between seal and reveal!"
assert campaign.verify(m), "revealed seeds do not hash to the commitment!"
print("OK — seeds were fixed in advance:", m.seeds)
PY
```

## Reproducing the analysis

```sh
# scorecard + trajectory + parse-fail split + standings (colourblind-safe text)
PYTHONPATH=. python3 scripts/foedus_canonical_scorecard.py --out-dir <this-dir>/run

# OpenSkill standings straight from the sweep (independent recompute)
PYTHONPATH=. python3 scripts/foedus_compute_ratings.py <this-dir>/run/sweep.jsonl
```

## Reproducing the match (costs LLM subscription time)

The run is deterministic given the revealed seeds. Re-running draws a *fresh*
sealed seed list unless you pass the revealed seeds back (the CSPRNG draw is
intentionally not reproducible without them; `--seed-rng` exists for tests
only).

```sh
FOEDUS_LLM_CLI_TIMEOUT=300 PYTHONPATH=. python3 scripts/foedus_canonical_campaign.py \
    --match-id <match-id> --num-games <N> \
    --backend claude-cli --model sonnet \
    --out-dir <this-dir>/run
```

`preflight/` holds the mandatory 1-game smoke used to project the full-match
wall-clock before committing to the long run.
