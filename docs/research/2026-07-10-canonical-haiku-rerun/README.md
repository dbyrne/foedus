# Canonical re-run on the fixed engine (Haiku, 8 games) — supersedes run #1's confounded null

**Match id:** `canonical-haiku-2026-07-10` · **Milestone:** M-foedus-canonical-rerun-haiku

This is the CLEAN re-run of the canonical Ruleset-v1 campaign
(`docs/research/2026-07-04-canonical-campaign-v1/`) on the engine as of
`main` **after** the `require_dest` ("pin") Support-parser fix (PR #47) —
S1.5's corpus autopsy (PR #46) showed run #1's "coordinated punishment
fails" verdict was an engine bug (pinned Supports were silently coerced to
Hold before ever reaching the resolver), not a genuine finding about LLM
coordination. Run #1's defector-containment interpretation is **superseded**
by this run; run #1 remains archived, unmodified, as the confounded-null
record of the bug it exposed.

> Board: 4 seats · 12 turns · map radius 2 · `continental_sweep` · détente
> threshold 8 (engine default). Toggles: reciprocation ledger ON · campaign
> memory ON · retreats OFF · LLM decision timeout 300 s · **parallel seat
> calls ON, `FOEDUS_PARALLEL_SEATS_WORKERS=3`** (all 3 LLM seats concurrent —
> pre-registered before game 0 per PR #43's proven-equivalent hot-swap; see
> `run/campaign_plan.json`'s `parallel_seats` field). Roster: 3 **Haiku**
> entrants (`claude-cli --model haiku`, per PR #48's fitness probe — 0/144
> parse-fail, thin-but-real coordination) + 1 `DishonestCooperator` house
> freerider. Seats rotate by the §7.4 cyclic Latin square; seeds are
> commit-reveal sealed (§7.5). Rating: OpenSkill (Plackett-Luce), one
> identity per entrant, conservative μ − 3σ.

## Primary question (pre-registered)

Does the LLM table contain / dethrone the freerider once its coordinated
Supports actually reach the resolver (the fixed engine), or does the
freerider still win/place highly? Report the punishment-conversion pipeline
(proposed → executed → paid) using the S1 tooling (coverage-guarded) so run
#1 vs this re-run is directly comparable.

## Directory layout

Same schema as run #1 (`docs/research/2026-07-04-canonical-campaign-v1/README.md`):

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
| `launch.sh` / `resume.sh` | The exact commands used to launch / crash-resume the match (env vars included). |

## Verifying the seeds (anyone can do this)

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
PYTHONPATH=. python3 scripts/foedus_canonical_scorecard.py --out-dir docs/research/2026-07-10-canonical-haiku-rerun/run
PYTHONPATH=. python3 scripts/foedus_compute_ratings.py docs/research/2026-07-10-canonical-haiku-rerun/run/sweep.jsonl
```

See `results.md` (written after the match completes) for the full
supersession note and the punishment-conversion comparison against run #1.
