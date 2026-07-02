# Retreats — lethality-softening pass: evidence packet (2026-07-02)

**TL;DR — honest negative.** Retreats are implemented, correct, and tested, and
they demonstrably change the game's *lethality* (dislodged units survive; ~half
the units that used to die now retreat home). But they do **not** clear the
falsifiable "freerider closed" bar, **alone or paired with a mild leader
counterweight**. `DishonestCooperator` (DC) and `MinimalReciprocator` (MR) stay
in the top-3 in both arms; `Shunner` is viable (#1 in Arm A) but cannot dethrone
them; `Reciprocator` stays mid-pack. The leaderboards with retreats ON are
within rating noise of the retreats-OFF control. Adding a supply-upkeep leader
tax makes it worse in the roomier arm (re-crowns `ValueGreedy` at #2), exactly
the failure mode the freerider design pass predicted.

This **hardens** the freerider doc's stated fallback conclusion: *if retreats
don't clear the bar, the freerider is only closeable by LLM-coordinated
shunning, and the arena's fitness claim rests on the press layer.*

**Recommendation:** ship retreats as a **default-OFF**, correct, opt-in mechanic
(a taste/design lever David can toggle — decisive → grindier), not as the
freerider fix it was hoped to be. Keep the leader counterweight default-OFF too
(prototype infra only). The next real lever is the **press/LLM layer**, not
another engine knob.

---

## 1. What was built

- **Retreats** (`foedus/resolve.py`, gated on `GameConfig.retreats_enabled`,
  default OFF): a dislodged unit is teleported to its **home node** (tempo cost
  = lost forward position) instead of being eliminated. Fallback ladder:
  - home **captured by an enemy** (`new_owner[home] != owner`) → eliminate
    (terminal);
  - home owned but **occupied** (by any unit) → **nearest empty owned passable
    node** (BFS from home, lowest-node-id tie-break); else eliminate.
  Retreats run after the ownership update (to see a captured home / owned
  fallback nodes) and before builds + eliminations (a retreated unit counts
  toward supply-need and can save a player). They land on already-owned nodes,
  so they never change ownership or award score. Dislodgement attribution and
  combat/alliance rewards are unaffected — the dislodge still *happened*, the
  unit just survives. 13 unit tests in `tests/test_retreats.py`.
- **Shunner** (`foedus/agents/heuristics/shunner.py`, roster now 22): reconstructs
  the freerider-doc probe. Reads the public reciprocation ledger; a player that
  took ally support (`received > 0`) while `standing < reciprocation_floor` is a
  free-rider → declare HOSTILE, refuse to Support it, attack its supply-sitting
  units (coordinating a 2nd unit as Support to actually dislodge). Detection is
  clean (never flags honest cooperators — tested).
- **Leader counterweight** (`GameConfig.supply_upkeep`, default 0.0): per-turn
  upkeep on supplies above `supply_upkeep_free` (default 3). Prototype toggle
  only; see §4.
- Sweep flags: `--retreats`, `--supply-upkeep`, `--supply-upkeep-free`.

## 2. The falsifiable bar (from the freerider design pass)

For retreats to "close the freerider":
1. `DishonestCooperator` **AND** `MinimalReciprocator` both **≥ rank 4** (out of
   top-3) in **both** arms.
2. `Shunner` **and** `Reciprocator` rank **above** both freeriders.
3. `GreedyHold`/`ValueGreedy` **not** back at #1–3.

Protocol: 22-agent roster, `continental_sweep`, 4 players, 15 turns, seed 0,
peace_threshold 99 (play to max_turns), 10,000 games/arm. Arm A = map-radius 2,
Arm C = map-radius 3. Control = retreats OFF; test = retreats ON. Ratings are
conservative OpenSkill (`mu − 3σ`).

## 3. Results — retreats OFF (control) vs ON (test)

Top of ladder (`mu − 3σ`); **bold** = a freerider or a quiet expander that the
bar wants *out* of the top-3.

| # | OFF · Arm A | OFF · Arm C | ON · Arm A | ON · Arm C |
|---|---|---|---|---|
| 1 | Shunner 29.74 | **DishonestCooperator 36.02** | Shunner 29.63 | **DishonestCooperator 35.91** |
| 2 | **DishonestCooperator 29.09** | **MinimalReciprocator 33.65** | **DishonestCooperator 29.01** | **MinimalReciprocator 33.62** |
| 3 | **MinimalReciprocator 29.03** | **ValueGreedy 32.86** | **MinimalReciprocator 28.95** | **GreedyHold 32.98** |
| 4 | ValueGreedy 27.14 | GreedyHold 32.83 | ValueGreedy 26.90 | ValueGreedy 32.89 |
| 5 | Cooperator 26.53 | Shunner 32.50 | Cooperator 26.59 | Shunner 32.56 |
| 6 | TitForTat 25.92 | Patron 32.27 | TitForTat 25.84 | Reciprocator 32.25 |
| 7 | GreedyHold 25.87 | Reciprocator 31.95 | GreedyHold 25.72 | Patron 32.23 |
| … | Reciprocator #10 25.01 | TitForTat 31.80 | Reciprocator #10 25.14 | TitForTat 31.84 |

**Verdict: FAIL, both arms, retreats ON.**
- Bar 1 (DC & MR out of top-3): **FAIL** — DC #2 & MR #3 in Arm A; DC #1 & MR #2
  in Arm C.
- Bar 2 (Shunner & Reciprocator above both freeriders): **partial/FAIL** —
  Shunner beats the freeriders in Arm A (#1) but not Arm C (#5, below DC/MR);
  Reciprocator is #10 (Arm A) / #6 (Arm C), **below** the freeriders in both.
- Bar 3 (no quiet expander in #1–3): **FAIL in Arm C** — GreedyHold #3.

**The ON and OFF ladders are within noise of each other** (e.g. Shunner Arm A
29.74 → 29.63; DC 29.09 → 29.01). Retreats did not move the competitive order.

## 4. Leader counterweight (retreats ON + supply upkeep) — also fails

Top-4, retreats ON + `--supply-upkeep`:

| # | upkeep 0.25 · Arm A | upkeep 0.25 · Arm C | upkeep 0.5 · Arm A | upkeep 0.5 · Arm C |
|---|---|---|---|---|
| 1 | Shunner 29.83 | **DishonestCooperator 35.14** | Shunner 29.83 | **DishonestCooperator 34.97** |
| 2 | **MinimalReciprocator 28.87** | **ValueGreedy 32.77** | **MinimalReciprocator 28.63** | **ValueGreedy 33.12** |
| 3 | **DishonestCooperator 28.64** | **MinimalReciprocator 32.57** | **DishonestCooperator 28.40** | **MinimalReciprocator 32.24** |
| 4 | Cooperator 26.72 | GreedyHold 32.32 | ValueGreedy 26.76 | Shunner 31.84 |

The tax barely dents DC in Arm A (still #3) and in Arm C **re-crowns the quiet
expander `ValueGreedy` at #2** — the exact backfire the freerider pass reported
for a leader tax alone. Retreats do not rescue it. Recommendation: leave
`supply_upkeep` at 0 (kept as default-off infra for the LLM-phase re-test).

## 5. Why retreats don't bite — diagnosis (measured, not asserted)

Per-game aggregates (10k/arm):

| arm | dislodge events / game¹ | % games with a dislodge | eliminations / game | units surviving via retreat² |
|---|---|---|---|---|
| OFF · A | 0.53 | 27.5% | 0.08 | — |
| ON · A | 0.55 | 17.1%³ | 0.07 | ~half of dislodged |
| OFF · C | 0.32 | 19.0% | 0.02 | — |
| ON · C | 0.33 | 6.6%³ | 0.02 | ~half of dislodged |

¹ `combat_rewards_fired`/game — the count of actual dislodgement *events*. It is
**unchanged** OFF→ON, confirming retreats do not prevent attacks; they let the
victim survive. ² the sweep's `dislodgement_count` (units-lost) roughly halves
OFF→ON because retreated units stay in `units`. ³ "% games with a dislodge" here
is the units-lost proxy and therefore *drops* with retreats — read it together
with column 1 (event count), which does not.

**The binding constraint is not lethality — it is that combat is rare.** Only
**~19–28%** of games contain *any* dislodgement, and eliminations are already
**~0.02–0.08/game**. The equilibrium is a low-conflict expansion race (Fable's
"quiet expansion"). Softening the *consequence* of a rare event (and symmetrically
— the punished freerider retreats just like a stabbed cooperator) cannot move a
ranking that is decided by expansion tempo, not by surviving combat. The
freerider's edge (§1 of the freerider doc: quiet GreedyHold expansion + a
tempo-baiting residual) never routes through "was I hard to dislodge," so making
dislodging non-lethal leaves it untouched. `Shunner` remains structurally
insufficient: it holds ~1 of 4 seats in a fraction of games, and one punisher
cannot tax a whole field of expanders faster than they expand.

This is consistent with the freerider pass's own hypothesis-with-caveat: it hoped
retreats would "make dislodging cheaper/repeatable," but retreats-to-home make the
*victim survive*, not attacking *cheaper or more frequent* — and frequency is the
variable that's actually pinned low here.

## 6. Recommendation

- **Ship retreats, default OFF.** It is a correct, well-tested, opt-in mechanic
  and a legitimate **taste lever** (David flagged the character change:
  decisive → grindier). It is *not* the freerider fix.
- **Leader counterweight: keep default OFF** — inert-to-harmful, as measured.
- **Do not add more engine knobs chasing the freerider.** The evidence across
  this pass + the three prior ones is now overwhelming that no heuristic-layer
  physics lever closes it. The next lever is the **press/LLM layer**: a table of
  LLM agents that read `freeride_debt`/`reciprocation_standing` and *coordinate*
  a punishment coalition — the one mechanism the heuristic roster (one shunning
  seat, no coordination channel) structurally cannot test. Retreats + the public
  ledger + a viable, correctly-targeted `Shunner` are the substrate that layer
  needs; they are now in place.

## 7. Reproduce

```sh
# From the worktree, with the [dev] extra installed.
SW="PYTHONPATH=. python scripts/foedus_sim_sweep.py --num-games 10000 \
  --max-turns 15 --archetype continental_sweep --num-players 4 --workers 10 --seed 0"
$SW --map-radius 2               --out off_A.jsonl   # control, Arm A
$SW --map-radius 3               --out off_C.jsonl   # control, Arm C
$SW --map-radius 2 --retreats    --out on_A.jsonl    # test, Arm A
$SW --map-radius 3 --retreats    --out on_C.jsonl    # test, Arm C
$SW --map-radius 2 --retreats --supply-upkeep 0.5 --out on_up50_A.jsonl
$SW --map-radius 3 --retreats --supply-upkeep 0.5 --out on_up50_C.jsonl
python scripts/foedus_compute_ratings.py <file>.jsonl
```
