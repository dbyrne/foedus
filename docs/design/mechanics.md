# foedus Game Mechanics — Current State and Future Directions

This document is a living description of the game's mechanics: what's
currently implemented, what's planned next, and what's been considered as
future extensions. It serves as a roadmap for contributors and a reference
for design discussions, *not* a strict spec — feature inclusion and
ordering are open to change.

Detailed specs for shipped features live in `docs/design/<date>-<feature>.md`.
This document references those by name when they exist.

---

## Part I — Current state (v1 + Press v0)

The engine fits in roughly 1k LOC; the test suite (~190 tests) runs in
~0.13s. Mechanics are deliberately lean.

### Map

- **Procedural hex disk**, radius 3, ~37 cells. 0–3 cells randomly
  removed for topological variation.
- **Players:** 2–6, configurable. Homes placed evenly around the perimeter
  by polar angle.
- **Node types:** `PLAIN`, `SUPPLY`, `HOME`. All nodes are otherwise
  identical — no terrain modifiers, no movement costs, all hexes hold one
  unit.
- **Supply centers:** all `HOME` nodes plus ~40% of remaining nodes,
  randomly assigned at generation time.
- **Adjacency:** standard hex 6-neighbor; symmetric; static across a game.

### Units

- **Single generic type.** No army/fleet distinction; no unit
  classes. Each unit has 1 base strength.
- **Initial placement:** one unit per player on their home node.

### Order language

- `Hold` — stay put.
- `Move(dest)` — move to adjacent node.
- `SupportHold(target)` — lend +1 strength to an adjacent unit's hold.
- `SupportMove(target, target_dest)` — lend +1 strength to an adjacent
  unit's move.

Submitted simultaneously and secretly each turn; revealed at end-of-round.

### Resolution

- Order normalization drops geometrically illegal orders (silently
  re-routed to `Hold`).
- Support cuts: any uncut attack on a supporter from someone other than
  the supported attack's target cancels the support.
- Strength comparison: highest move-strength wins each contested
  destination; ties bounce.
- Head-to-head: simple direct strength comparison; ties bounce, no swap.
- Cycle detection: A→B→C→A all-success is detected explicitly.
- Dislodgement: dislodged units are **eliminated** (no retreat phase,
  no disband phase).
- Self-dislodgement: forbidden.

See `foedus/resolve.py` for the full DATC-subset implementation.

### Build phase

- Every `build_period` turns (default 3), each player gets new units up to
  their supply count, placed at unoccupied territory they own.
- Build can target *any* unoccupied owned node, not just home — distinct
  from Diplomacy.

### Scoring

- **Cumulative**, not binary: each player gains +1 per controlled supply
  center per turn, summed over the game.
- Highest cumulative score after `max_turns` (default 25) wins, unless
  one of the alternative end conditions fires.

### Termination

A game ends when any of these fires:

- **Max turns reached** → highest cumulative score wins (ties → no winner).
- **Last player standing** → solo win.
- **Détente (collective victory)** → all surviving players co-win, see
  Press v0 below.

### Press v0 — negotiation, det̀ente re-anchor, stagnation cost

See `docs/design/2026-04-27-press-v0.md` for full spec. Summary:

- **Two-phase turn:** NEGOTIATION → ORDERS. Engine functions are pure
  state-transition; real-time orchestration (timers, async chat) is
  driver-side.
- **Press tokens:** structured per-turn signals.
  - `Stance` — public ALLY/NEUTRAL/HOSTILE toward each other player.
  - `Intent` — pre-declaration "I will issue order X for unit U," with
    `visible_to: frozenset[PlayerId] | None` controlling who sees it.
    `None` = public broadcast; explicit set = bilateral or group share.
- **Free-text chat:** opaque to the engine. Each `ChatMessage` has a
  `recipients` set (None = public broadcast). For humans and LLM agents.
- **Verification:** at finalize, the engine compares each declared intent
  to the player's *raw submitted order*. Mismatch emits a
  `BetrayalObservation` to each player in `visible_to` (or all surviving
  non-senders for public intents). Bounce/dislodge outcomes are *not*
  betrayal signals — only what the player tried to do counts.
- **Détente trigger:** fires when surviving players have all signaled
  mutual ALLY for `detente_threshold` consecutive turns. The default
  scales with table size as `4 + num_players` (so a 4-player game needs
  8 consecutive mutual-ALLY turns; a 2-player game, 6); `0` disables.
  Replaces v1's "no dislodgement" timeout, which had a degenerate
  attractor.
- **Stagnation cost:** -`stagnation_cost` score per turn for players whose
  canon contains no Move or SupportMove (default `0.0`, i.e. disabled;
  configurable). Was originally 1.0 in v1 to discourage all-Hold détente
  attractor games, but Bundle 2's hold-or-dislodge supply ownership rule
  now incentivizes commitment-to-hold directly — so the penalty became
  perverse (a single-unit player Holding to lock in a freshly-captured
  supply was paying the penalty for the strategically-correct play).
  Callers who want the v1 behavior can pass `stagnation_cost=1.0`.

### Fog of war

- Each unit reveals its node + 1-hop neighborhood (`fog_radius=1`); enemy
  units outside that are invisible.
- Public state always visible: ownership, scores, eliminations, turn,
  map structure.
- Press visibility: see Press v0 spec §12. Public stance is universal;
  private intents only to recipients; chat filtered by recipient list.

---

## Part II — Near-term direction (planned: v0.2 — map archetypes)

The current procedural map generates uniform terrain — every node is
mechanically identical. This makes individual maps feel
indistinguishable from each other and limits replay variety. The next
mechanical depth pass introduces **map archetypes**: the generator picks
an archetype (random or configured) and samples within that archetype's
parameters. Each archetype produces maps with a recognizable strategic
flavor while preserving randomization within.

### Initial archetype set

Three archetypes for v0.2, each requiring minimal new mechanics:

- **Highland Pass.** Mostly plains with one or two mountain ranges
  creating chokepoints. Homes positioned at pass entrances. Strategic
  flavor: defensive grind, control of one key hex can hold off larger
  forces, coalitions form around pass control.

- **Riverlands.** Snaking river divides the map into two regions
  connected by exactly two crossings. Strategic flavor: control of
  crossings is decisive; coalitions form around which crossing to
  push through.

- **Continental Sweep.** Mostly open plains, dense connectivity, no
  terrain barriers. Closest to current uniform foedus. Strategic
  flavor: mobility-first, fast wars, encirclement common.

### Required mechanics (v0.2 minimum)

- **New node types:**
  - `MOUNTAIN` — impassable; cannot hold units; cannot be owned.
  - `WATER` — impassable; cannot hold units; cannot be owned. Distinct
    from mountain for rendering and future convoy support.
- **Archetype-aware mapgen.** Generator accepts an `archetype` parameter
  (or picks at random) and samples terrain mix, connectivity, and home
  placement accordingly.
- **Adjacency through impassable terrain:** mountain/water hexes still
  exist as nodes for rendering but have no edges (or edges marked
  impassable). Order normalization treats them as non-adjacent.

### Out of scope for v0.2

- Combat modifiers from terrain (forest defender bonus, etc.). Pure
  passable/impassable distinction only.
- Variable supply center values.
- Anything from Part III below. Each is a distinct future feature.

---

## Part III — Future directions (open, undated)

These are mechanics ideas captured during design discussions. They are
*not* committed; ordering and inclusion depend on future priorities.
Each is presented with its strategic motivation, scope, and notable
open questions.

### A. More archetypes

Once the v0.2 generator framework lands, additional archetypes are
cheap to add:

- **Verdant.** Heavy forest cover; forests give defender +1 strength.
  Slow attrition wars; negotiation strongly incentivized. *Requires:
  forest combat modifier (see C below).*
- **City Crown.** ~5 hexes are CITIES worth +3 score per turn instead
  of +1. Cities scattered; players' homes are not cities. Wars over
  high-value targets. *Requires: variable supply value (see B).*
- **River Network.** Multiple rivers crossing the map; rivers are
  movement-penalty edges or only passable at bridge hexes. Flanking
  play. *Requires: edge-typed movement.*
- **Inland Sea.** Large central body of water; player homes on the
  perimeter; central sea is contested neutral ground. *Requires:
  variant home placement.*
- **City State.** Urban centers around home regions; surrounding
  hinterlands sparse. Wars contained to a few key locations.
- **Archipelago.** Heavy water; land breaks into 3-5 isolated regions;
  each player's home on a different island. Requires convoys for
  cross-water movement (currently not implemented). Strategic flavor:
  isolated buildup followed by sudden contact via convoy chains.

### B. Variable supply center values

Each supply center carries a `value` (default 1). Some hexes are worth
+2 or +3 per turn. Generator distributes high-value supplies based on
archetype.

**Why:** Adds heterogeneity to the map. Some objectives matter more
than others; coalitions form around high-value targets.

**Open questions:** How is value displayed in fog views? Are
high-value supplies always public? How does this interact with build
phase — do players build at high-value owned hexes preferentially?

### C. Terrain combat modifiers

Each non-impassable terrain type gives modifiers to combat or movement:

- `FOREST` — defender +1 hold strength (and maybe +1 defend strength
  in head-to-head).
- `MOUNTAIN_FOOTHILL` — passable but defender +1; attacker -1 move
  strength into the hex.
- `RIVER_CROSSING` — attacker -1 move strength across the edge.

**Why:** Combat outcomes depend on geography, not just unit count.
Adds tactical depth to position selection.

**Open questions:** How do modifiers stack with supports? Should
modifiers be visible in fog views? Are modifiers symmetric for both
combatants or attacker-only?

### D. Resource economy

Hexes generate resources each turn instead of (or in addition to)
contributing to supply count. Resources accumulate per-player in a
treasury. Actions cost resources:

- Building units costs `food` or `gold`.
- Special orders (e.g., long-range moves, scouting) cost something.
- Maintenance: existing units cost upkeep per turn.

**Why:** Adds a strategic accumulation/timing layer. Save for a big
push vs spend now. Resources become a third class of negotiable
commitment alongside stance and orders ("I'll trade you 5 food for
safe passage").

**Open questions:** Single-resource or multi-resource economy? Are
resource pools public (visible to all) or fogged? Does the existing
build phase get replaced or extended? How does this interact with
NN training (continuous state vs discrete categorical)?

### E. Unit type variety / rock-paper-scissors combat

Multiple unit types with combat advantages over each other:

- **Infantry > Cavalry > Archer > Infantry** (or similar three-way
  cycle).
- Each type has its own movement, strength, and cost (if resources are
  in play).

**Why:** Counter-picking depth. Forces players to scout and adapt to
opponents' compositions. Adds tactical surprise.

**Open questions:** Does this require resources first (so build choice
is meaningful)? How do mixed-type stacks interact (multiple units in a
hex)? How is type visibility fogged?

### F. Supply chain mechanics

Supply centers must be connected to the player's home via a friendly
path. Disconnected supplies don't score (or only score reduced).
Severing supply by occupying a chokepoint cripples income.

**Why:** Geographic pressure becomes more meaningful. Encourages
coalition warfare aimed at logistics, not just frontline territory.

**Open questions:** Does the path have to be land-only? How is
"connected" defined when the map has multiple components? Does fog
hide supply chain status from observers?

### G. Hidden information enrichments

- **Forest hides units:** units inside forest hexes are not visible
  to enemies even when adjacent (overrides fog_radius).
- **Scout units:** specialized units with extended fog_radius.
- **Stealth orders:** an order modifier that hides movement until
  resolution (vs reveal at submit).

**Why:** Increases the value of belief modeling — agents must reason
about possible enemy positions, not just observed ones.

**Open questions:** Do these mechanics cooperate with press tokens
(can you commit a "stealth move" intent)?

### H. Asymmetric starting conditions

Players draw a "civilization" or "trait" at game start that gives
distinct starting bonuses or special abilities. Examples:

- **Mountaineer:** ignores +1 defender bonus in mountain foothills.
- **Trader:** starts with +N resources (if economy is in play).
- **Diplomat:** can issue one extra intent per turn.

**Why:** Adds per-game variety even on the same archetype. Forces
adaptation to your draw.

**Open questions:** How is balance maintained across drafts? Public
or hidden traits? Does this break NN training (now agent must learn
trait-conditioned strategies)?

### I. Variable victory conditions / secret objectives

In addition to the standard cumulative-score victory, each player
draws a secret objective at game start (e.g., "control all 4 corners,"
"never have more than 3 units," "control player N's home by turn 15").
A player who hits their secret objective wins immediately.

**Why:** Different players pursue different goals; "winning" looks
different per player; coalitions become more complex (your "ally" may
be playing for a goal that hurts you).

**Open questions:** Are objectives public or private? How is the
trigger evaluated (engine-checked or player-claimed)?

### J. Multi-round negotiation

Currently a single negotiation round per turn. Future: configurable N
rounds, with stance/intent revisability across rounds. Or: open-ended
"until all players signal done" rounds.

**Why:** More authentic to Diplomacy table-talk; allows offer →
counter-offer → accept dynamics within a turn.

**Open questions:** How long do we let multi-round runs go before
forcing a turn-clock? Does each round emit its own press_history
entry, or just the final?

---

## Design principles to preserve through extension

When considering any extension above, weigh against:

1. **NN training compatibility.** Mechanics that explode the action
   space or make rewards noisy hurt training. Discrete, bounded, and
   semantically meaningful additions are preferred over continuous or
   open-ended ones.

2. **Fog and asymmetric information.** foedus' commitment to hidden
   information means every new mechanic should consider: what does
   each player observe? Does it have a fogged view?

3. **Procedural variety, not memorization.** New mechanics should not
   reward memorization of fixed configurations. Archetypes, asymmetric
   starts, secret objectives — all should be sampled fresh each game.

4. **Engine simplicity.** The engine fits in ~1k LOC. New mechanics
   that bloat it materially should be split into separate modules
   (like `foedus/press.py` was).

5. **Backward compatibility for training.** A `RandomAgent` (or any v1
   agent) should continue to play without modification. New mechanics
   should default to off or to neutral behavior so existing training
   pipelines don't silently break.

---

*Last updated: 2026-04-27. See git history for prior design decisions.*
