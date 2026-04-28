# Bundle 2 — Supply ownership cadence (mechanic A)

**Status:** Design approved. Ready for implementation plan.
**Date:** 2026-04-29
**Author:** David Erner + Claude (Opus)

## Why

Two playtests (Bundle 1 baseline and Bundle 3 press-exposed) both showed the
same finding: **greedy heuristic expansion beats coordinated LLM play**. In
the Bundle 3 game, P0 and P1 (Haiku) maintained mutual ALLY for all 7 turns,
honored every declared intent, executed coordinated multi-front attacks
against the leader — and still lost by 1 point to a heuristic that just
walked from supply to supply.

The root cause is the current ownership rule: at end of every turn, any
node with a unit on it gets stamped with that unit's owner. So a "walk and
go" expansion strategy collects supply ownership in passing, with no need
to commit force to actually hold them.

This bundle fixes the rule so that ownership transfers reflect actual
control:
- Walk-ins onto undefended supplies don't immediately count.
- Combat captures (dislodgements) transfer ownership immediately — you
  fought for it, you have it.
- Holding a supply through a full turn transfers ownership — you
  committed force to controlling it.

## Out of scope (deferred to later bundles)

- Alliance-strength multipliers (Bundle 4)
- D — fog-respecting `legal_orders_for_unit` (Bundle 5)
- H — threat-context in per-player view (Bundle 5)
- Heuristic press revision — anti-leader ALLY rule (Bundle 5)
- Chat UX — encourage explicit unit×destination pairings (Bundle 5)
- Mechanic I (strongest-attacker wins) — verified non-issue;
  current `_resolve_moves` already matches canonical vanilla Diplomacy
  behavior in all constructible cases.

## The rule

**Supply/home ownership at end of turn N transfers to player P if and only
if at least one of:**

**(a) Combat capture** — a unit owned by P dislodged a defender on the
supply during turn N's resolution.

**(b) Held through a full turn** — a unit owned by P was on the supply at
the **start of turn N (before any orders for turn N have resolved)** AND
is still there at the **end of turn N (after all moves are applied)**.

Equivalently: rule (b) checks `state.units` (the input state) against
`new_units` (the post-resolution state), and fires if both have a
P-owned unit at the same supply node.

Otherwise, ownership is unchanged.

**Plain nodes** (NodeType.PLAIN): unchanged from current behavior — flip
every turn based on end-of-turn occupant. (Plain ownership matters only
for build-overflow placement and fog logic, neither of which is affected
by this bundle.)

**Build phase**: unchanged from current behavior. Every `build_period`
turns, recruit new units to match owned supply count. No special role in
ownership.

## Why this rule

It cleanly maps to the two ways a supply can change hands in real military
terms: **combat** (you took it by force) and **occupation** (you sat on it
without challenge for long enough that everyone agrees it's yours now).
Walking through a supply on your way somewhere else is neither — it's
ambiguous, transient, and shouldn't count.

The rule also has a clean answer to "what if I lose a supply between build
phases?":
- Lost via dislodgement → ownership transfers immediately, you stop
  scoring it that turn.
- Lost via enemy holding through the next full turn → ownership transfers
  at end of that turn.

In both cases, you stop earning score from a supply you no longer control,
without artificial waiting until a build phase.

## Implementation

### Where the change lives

`foedus/resolve.py`, in `_resolve_orders`:

- **Step 5** (move resolution) already produces an `outcome` dict with
  values `'success' | 'fail' | 'dislodged'`. The dislodgement-flip hook
  (rule (a)) goes here.
- **Step 6** (ownership update, lines 375-379 currently) becomes the
  hold-through-full-turn flip (rule (b)) for supplies, plus the unchanged
  every-turn flip for plains.

### New ownership-update logic

Replace the current step 6:

```python
# Current (incorrect for supplies):
new_owner = dict(state.ownership)
for unit in new_units.values():
    new_owner[unit.location] = unit.owner
```

With a layered update:

```python
new_owner = dict(state.ownership)

# Identify start-of-turn supply occupants (from state.units, BEFORE moves
# resolved). state.units snapshots units at the START of turn N.
start_supply_occupants: dict[NodeId, PlayerId] = {}
for unit in state.units.values():
    if state.map.is_supply(unit.location):
        start_supply_occupants[unit.location] = unit.owner

# Rule (a) — dislodgement: any defender dislodged on a supply transfers
# ownership to the successful attacker who moved into that node.
for u_id, outcome_val in outcome.items():
    if outcome_val != "dislodged":
        continue
    defender = state.units[u_id]
    if not state.map.is_supply(defender.location):
        continue
    # Find the attacker whose successful Move ended at this node.
    attacker_id = next(
        (uid for uid, o in canon.items()
         if isinstance(o, Move)
         and o.dest == defender.location
         and outcome.get(uid) == "success"),
        None,
    )
    if attacker_id is not None:
        new_owner[defender.location] = state.units[attacker_id].owner

# Rule (b) — held through full turn: a unit at end-of-turn on a supply
# AND that unit was at the same supply at start of turn N transfers
# ownership.
for unit in new_units.values():
    if not state.map.is_supply(unit.location):
        continue
    # End-of-turn occupant. Was the same player there at start of turn?
    if start_supply_occupants.get(unit.location) == unit.owner:
        new_owner[unit.location] = unit.owner

# Plains: unchanged behavior — flip every turn for any occupied plain.
for unit in new_units.values():
    if not state.map.is_supply(unit.location):
        new_owner[unit.location] = unit.owner
```

### Ordering rationale

1. **(a) before (b)** — Dislodgements take precedence. If unit X dislodges
   unit Y on a supply, the supply transfers to X via (a). Then if X stays,
   (b) would also fire but it's a no-op (X is already the owner).
2. **(b) before plains** — purely for code clarity; they're disjoint sets
   of nodes (`is_supply` vs not).

### Edge cases

**Walk-in onto own supply**: e.g. P0's u4 moves from n4 to n9 (n4 P0's
supply). At end of turn, u4 is on n9. Was a P0 unit on n9 at start of
turn? No (n9 was empty or had non-P0 unit). Rule (b) doesn't fire for n9.
Was a P0 unit on n4 at start of turn? Yes (u4). End of turn n4 empty. Rule
(b) doesn't fire (no end-of-turn unit). Ownership of n4 stays P0
(unchanged from prior). ✓

**Sit-still on own supply**: u4 holds at n4 (P0's supply). Start-of-turn
n4 has P0 unit. End-of-turn n4 has P0 unit. Rule (b) fires for n4 →
ownership stays P0 (no-op). ✓

**Dislodge then leave**: P1's u_x dislodges P0's u4 at n4 in turn N (rule
(a) → n4 transfers to P1). Turn N+1 P1's u_x moves out, n4 empty. n4
ownership stays P1 (no rule fires to change it, empty supplies retain
prior owner). ✓

**Walk in then leave**: P1's u_x walks into P0's empty n4 in turn N (no
rule fires; n4 stays P0). Turn N+1 P1's u_x moves out before any holding.
n4 stays P0 (still no rule fires). P0 never lost the supply despite the
walk-through. ✓

**Walk in then hold through next turn**: P1's u_x walks into P0's empty n4
in turn N (no rule fires; n4 stays P0). Turn N+1 P1's u_x stays on n4. At
end of turn N+1, P1 unit was at n4 at start of N+1 (yes — they were there
at end of N) AND at end of N+1. Rule (b) fires → n4 transfers to P1. ✓

**Three-way contest with one survivor**: u_a, u_b, u_c all attack n5 (P0
supply with no defender at start). u_a wins via support (str 2 vs 1, 1).
u_a is at n5 end of turn. Was u_a (or another P_a unit) at n5 at start of
turn N? No. Rule (b) doesn't fire. Was anyone dislodged at n5? No (no
defender). Rule (a) doesn't fire. n5 stays P0. ✓
Even though u_a "won" the contest, they merely walked into the empty
supply. They have to hold it through next turn for it to flip.

**Final turn**: turn N is the last turn (game becomes terminal). Rule (a)
and (b) fire normally. Final supply ownership reflects rules (a) and (b)
applied to turn N's events. **There is no special "final turn flip"** —
the rules just produce the right answer naturally. (See "Open question
resolved" below.)

## Open question resolved

In an earlier draft I considered "ownership also flips at end-of-game" as
a special case to preserve final-turn drama. With this revised rule it's
not needed:

- Final-turn dislodgements: rule (a) fires, ownership transfers that turn.
- Final-turn walk-ins onto empty supply: rule (b) doesn't fire (the
  attacker wasn't there at start of turn). Ownership unchanged. **This is
  intentional**: a walk-in on the final turn shouldn't count any more
  than a walk-in mid-game would.

This is a real game-balance tradeoff. The Bundle 3 playtest's last-turn
walk-ins (e.g. P1's u8 walking into empty n24) would NOT transfer
ownership under the new rule. Final-turn drama becomes about who
DISLODGES whom, not who walks where. That feels more in spirit with the
rest of the rule.

If we find this too punitive in playtest, we can revisit.

## Game-balance impact (qualitative)

Walking through the Bundle 3 press playtest under the new rule:

| Turn | Old cumulative scores | New scores (mechanic A) |
|---|---|---|
| 1 | 2/2/2/1 | 1/1/1/1 — no flips, walk-ins don't count |
| 2 | 5/5/5/3 | 2/2/2/2 — units kept moving; never held a supply |
| 3 | 9/9/9/6 | 3/3/3/3 — still moving, no flips, build phase produces 0 new units (no extra supplies) |

The first 2-3 turns become much slower — "walk and go" expansion produces
nothing. To get a build, you need to either dislodge an enemy from a
supply (rule (a)) or commit a unit to camping on a supply for two
consecutive turns (rule (b)).

This is intentional. It rewards:
- **Real combat** (dislodging earns supplies fast)
- **Coordination** (one ally holds, the other expands or attacks)
- **Defense** (SupportHold becomes meaningful — you can shore up a
  holder's strength against challengers)

And penalizes:
- "Greedy walk-and-go" expansion (the strategy heuristics currently
  win with)

A real test of impact requires a fresh playtest — same seed, same setup,
new rule — and comparing scoring trajectory and final outcome to Bundles
1 and 3.

## Components and data flow

```
            ┌─ resolve.py / _resolve_orders ─┐
            │                                │
            │   1. Flatten orders            │
            │   2. Normalize                 │
            │   3. Cuts + strengths          │
            │   4. h2h resolution            │
            │   5. Move resolution           │
            │       └─ produces `outcome`    │
            │   ★ NEW: ownership update      │
            │       ├─ rule (a) dislodges    │
            │       ├─ rule (b) held         │
            │       └─ plain (unchanged)     │
            │   7. Build phase (unchanged)   │
            │   8. Scoring (unchanged)       │
            │   9. Eliminations (unchanged)  │
            └────────────────────────────────┘
```

The change is contained to step 6 of `_resolve_orders`. No other module
needs to change. No new types, no schema changes, no wire-format changes.

## Tests

### Unit tests in `tests/test_supply_ownership_cadence.py` (new)

Each test exercises one rule path:

- `test_walk_in_onto_empty_supply_does_not_flip` — P1 walks into P0's
  empty supply; ownership stays P0 after turn 1.
- `test_walk_in_then_hold_flips_after_second_turn` — P1 walks into P0's
  empty supply turn 1, stays turn 2; ownership flips to P1 at end of
  turn 2 (rule (b)).
- `test_walk_in_then_leave_does_not_flip` — P1 walks in turn 1, leaves
  turn 2; ownership stays P0 throughout.
- `test_dislodge_flips_immediately` — P1 dislodges P0's defender on a
  supply; ownership flips to P1 at end of that same turn (rule (a)).
- `test_dislodge_then_vacate_keeps_dislodger_ownership` — P1 dislodges
  P0 turn 1, then leaves turn 2; supply stays P1 even though empty.
- `test_sit_still_on_own_supply_no_change` — P0 holds at their own
  supply; ownership stays P0 (no-op).
- `test_three_way_contest_winner_must_hold_to_flip` — three players
  contest an empty supply; winner moves in but doesn't hold; ownership
  doesn't flip.
- `test_three_way_contest_winner_holds_flips_next_turn` — same as above
  but winner stays through next turn; ownership flips to winner end of
  turn 2.
- `test_plain_node_flips_every_turn` — plain ownership unchanged from
  current behavior; regression check.
- `test_home_node_treated_as_supply` — homes follow the same rule as
  supplies (since `is_supply` returns True for HOME).

### Integration / smoke

Existing `tests/smoke/test_press_driver_smoke.py` runs a heuristic-only
game end-to-end. With the new rule it should still complete cleanly
(no engine errors, press_history populated). Heuristics may build fewer
units, score lower cumulatively. Update assertions to be resilient to
the new behavior (e.g., total game length should still terminate
naturally; no infinite loops).

### Test impact on existing suite

- `tests/test_resolve.py` — scrutinize each test. Many use `make_state`
  with explicit ownership; they test resolution logic, not ownership
  flipping per se. Those should stay green.
- `tests/test_scoring.py` (if it exists) — may have assertions that
  depend on per-turn ownership flipping. Update assertions to reflect
  the new cadence.
- `tests/test_archetypes.py`, `tests/test_mapgen.py`, `tests/test_fog.py`
  — independent of ownership cadence; should stay green.

A best-guess estimate: ~5-15 existing tests may need assertion updates.
We'll fix them inline as they come up during implementation.

## Backward compatibility

- **Wire format**: unchanged. `Map`, `GameState`, `GameConfig`,
  serialization code all unchanged.
- **Public API**: unchanged. `resolve_turn`, `finalize_round`,
  `advance_turn` all keep their signatures.
- **Save files**: unchanged (no new fields).
- **CLI / driver**: unchanged.
- **Heuristic and Random agents**: unchanged. Their behavior may produce
  different game outcomes, but their orders interface is unaffected.

The change is purely internal to `_resolve_orders`. Anyone using foedus
as a library will see different gameplay but no API breakage.

## Migration of existing playtest data

None needed. Bundle 3's playtest run is preserved in Nexus (history
logged); we don't need to replay it under the new rule. The playtest
finding stands: greedy expansion beat cooperation under the OLD rule.
Bundle 2's value is to be evaluated by a FRESH playtest run after merge.

## Success criteria

1. All 327 existing tests pass (with any necessary assertion updates for
   the new ownership cadence).
2. New `tests/test_supply_ownership_cadence.py` (~10 unit tests) passes,
   covering both rules and the major edge cases.
3. `tests/smoke/test_press_driver_smoke.py` completes cleanly under the
   new rule.
4. A fresh 4-player heuristic playtest (run after merge, comparable to
   Bundle 1's baseline) shows materially different scoring trajectory,
   especially in the first 3 turns.
5. The Bundle 3 press-exposed playtest, re-run after merge, can be
   compared to the original — does cooperation now beat greedy
   heuristics?
