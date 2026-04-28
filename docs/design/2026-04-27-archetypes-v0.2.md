# Archetypes v0.2 — Map Variety via Procedural Archetypes

**Status:** Draft, pending review.
**Date:** 2026-04-27.
**Authors:** David Erner, Claude (foedus session).
**Branch:** `archetypes` (off `press-v0`).

## 1. Motivation

The current procedural map generates uniform terrain — every hex is
mechanically identical. This makes individual maps feel
indistinguishable from each other and limits human-player replay
variety. From the mechanics roadmap (`docs/design/mechanics.md` Part
III): *"Adding terrain types with movement/combat modifiers turns each
generated map into a distinct strategic puzzle."*

This proposal introduces three **map archetypes** — Highland Pass,
Riverlands, and Continental Sweep — each with a recognizable
strategic flavor. The generator picks (or is told) an archetype, then
samples within that archetype's parameters. Specifics still vary
between maps of the same archetype, preserving the procedural-variety
mission, but each game has an identifiable character announced up
front.

(Archipelago was originally part of this set but was deferred to
v0.3 paired with convoy support — without cross-water movement,
players on separate islands cannot interact. See §12.)

This is the smallest viable depth pass: no combat modifiers, no
resources, no supply-chain mechanics. Just terrain shapes the playable
geometry, and that alone shifts strategy meaningfully.

## 2. Goals and non-goals

### Goals
- Each archetype produces visibly distinct, mechanically distinct maps
  that reward different play styles.
- Specifics still vary within an archetype (procedural variety
  preserved).
- Existing v1 / Press v0 tests continue to pass without modification.
- Forward-compatible architecture: future archetypes (Verdant, City
  Crown, etc.) and future map sizes (`map_radius > 3`) drop into the
  same generator framework.
- New archetype-aware logic stays bounded — the new code lives
  alongside the existing `mapgen.py`, not scattered across the
  codebase.

### Non-goals
- Terrain combat modifiers (forest defender bonus, etc.). Future work.
- Variable supply-center value (all supplies remain +1). Future work.
- Convoys / cross-water movement. Water is a hard barrier in v0.2.
- Unit type variety / rock-paper-scissors combat. Future work.
- Renaming archetypes is in scope; mechanical changes per archetype
  beyond what's in this spec is out of scope.

## 3. Locked design decisions

| Dimension | Decision |
|---|---|
| Archetype set | UNIFORM (v1 backward-compat) + HIGHLAND_PASS + RIVERLANDS + CONTINENTAL_SWEEP |
| Selection mechanism | `GameConfig.archetype: Archetype = Archetype.UNIFORM`; default preserves v1 behavior |
| Random selection | Standalone `random_archetype(rng_or_seed)` function returning a non-UNIFORM choice |
| Map size | Fixed nominal (`map_radius=3` default); `map_radius` exposed as a flexible parameter for future archetypes |
| Hex count consistency | Same total hex count across archetypes; archetypes vary the *playable* subset |
| Terrain types | Two new node types: `MOUNTAIN` and `WATER`. Identical semantics in v0.2 (impassable, not ownable, not occupiable). Distinct rendering. Forward-compatible for future divergence (combat modifiers, convoys). |
| Adjacency | MOUNTAIN/WATER hexes have empty edge sets; no node has them as neighbors. |
| Supply density | UNIFORM 40% (unchanged); HIGHLAND_PASS ~35%; CONTINENTAL_SWEEP ~50%; RIVERLANDS ~40% |
| Connectivity per archetype | UNIFORM 0-3 cells removed (unchanged); CONTINENTAL_SWEEP 0-1; HIGHLAND_PASS minimal removal + ridge mountains; RIVERLANDS minimal removal + snaking river WATER cells with two PLAIN crossings |
| Player count constraints | None (all archetypes accept the supported 2..6 range at radius=3) |

## 4. Architecture

### File structure

- **`foedus/core.py`** — extend `NodeType` enum with `MOUNTAIN` and
  `WATER`. Add `Archetype` enum. Add `archetype` and `map_radius`
  fields to `GameConfig`. Add `Map.is_passable(node) -> bool` helper.
- **`foedus/mapgen.py`** — extend with archetype-aware generator. Add
  `generate_map(num_players, seed, archetype, map_radius)` signature.
  Keep existing internal helpers (`_hex_disk`, `_hex_neighbors`, etc.)
  and add per-archetype generators.
- **`foedus/archetypes.py`** — new module. Public `random_archetype()`
  function. Internal per-archetype generator functions invoked by
  `mapgen.generate_map`.
- **`tests/test_archetypes.py`** — new test module.
- **`tests/test_mapgen.py`** — extend existing test file with archetype-
  aware cases (UNIFORM behavior preserved; new archetypes produce
  expected structural properties).

### Engine vs driver split

This is purely engine-layer work. No driver/CLI changes are required
beyond the CLI being told which archetype to use (existing
`--archetype` flag would need to be added; out of scope of this spec
beyond noting the entry point exists).

## 5. Data model

### Extended `NodeType` enum

```python
class NodeType(Enum):
    PLAIN = "plain"
    SUPPLY = "supply"
    HOME = "home"
    MOUNTAIN = "mountain"   # NEW: impassable, not ownable, not occupiable
    WATER = "water"         # NEW: same semantics as MOUNTAIN; distinct render
```

### New `Archetype` enum

```python
class Archetype(Enum):
    UNIFORM = "uniform"                       # v1 backward-compat
    HIGHLAND_PASS = "highland_pass"
    RIVERLANDS = "riverlands"
    CONTINENTAL_SWEEP = "continental_sweep"
```

### `GameConfig` additions

```python
@dataclass
class GameConfig:
    # ... existing fields ...
    archetype: Archetype = Archetype.UNIFORM   # NEW; default = v1 behavior
    map_radius: int = 3                        # NEW; controls hex-disk size
```

`map_radius` is a forward-compat hook. v0.2 archetypes are tuned for
radius=3 (~37 hexes); higher radii are accepted by the generators but
balance is not guaranteed.

### `Map` helper

```python
@dataclass(frozen=True)
class Map:
    # ... existing fields ...

    def is_passable(self, n: NodeId) -> bool:
        """True iff a unit can occupy/move-through this node."""
        return self.node_types[n] not in (NodeType.MOUNTAIN, NodeType.WATER)
```

Add `MOUNTAIN`/`WATER` to the `is_supply` check (returns False, since
they cannot hold supplies).

## 6. Engine API

### `mapgen.generate_map` signature

```python
def generate_map(
    num_players: int,
    seed: int | None = None,
    archetype: Archetype = Archetype.UNIFORM,
    map_radius: int = 3,
) -> Map: ...
```

Backward compatible: existing `generate_map(num_players, seed=...)`
calls continue to work and produce UNIFORM maps.

### `archetypes.random_archetype`

```python
def random_archetype(seed: int | None = None) -> Archetype:
    """Return a random Archetype from the non-UNIFORM set.

    Caller can pass a seed for reproducibility. Returns one of:
    HIGHLAND_PASS, RIVERLANDS, CONTINENTAL_SWEEP.
    """
```

This is a *selector* function, not part of the engine state. Callers
who want randomization compute an archetype at config time:

```python
cfg = GameConfig(num_players=4, seed=42,
                 archetype=random_archetype(seed=42))
```

## 7. Per-archetype generator algorithms

Each generator receives `(num_players, seed, map_radius)` and returns
a `Map`. Internally each begins with the same hex disk skeleton, then
applies archetype-specific transformations.

### `UNIFORM` (preserves v1 exactly)

```
1. Generate hex disk of radius map_radius.
2. Remove 0-3 random non-home, non-center cells (existing logic).
3. Place num_players home cells evenly around the perimeter by angle
   (existing logic).
4. Mark all home cells as HOME, ~40% of remaining cells as SUPPLY,
   the rest as PLAIN.
5. Build adjacency from hex neighbor rules (existing logic).
6. Return Map.
```

This is the existing `mapgen.generate_map` body, lightly refactored to
fit the new dispatch.

### `CONTINENTAL_SWEEP`

Same as UNIFORM with two parameter tweaks:

```
1. Remove 0-1 cells (lower than UNIFORM's 0-3) → denser connectivity.
2. ~50% of non-home cells as SUPPLY (higher than UNIFORM's 40%) →
   resource-rich; mobility-first play favored.
3. No MOUNTAIN / WATER cells.
```

### `HIGHLAND_PASS`

```
1. Generate hex disk of radius map_radius.
2. Remove 0-1 random cells (minimal variation; we're going to add our
   own structure).
3. Define a ridge: pick two random perimeter points roughly opposite
   each other; trace the hex line between them; collect all hexes
   within distance 1 of that line as ridge candidates.
4. Pick num_passes = 1 + (num_players // 3) ridge candidates as PASSES
   (these stay as PLAIN). Distribute passes evenly along the ridge so
   each "side" of the ridge has roughly half the passes.
5. Mark remaining ridge candidates as MOUNTAIN.
6. Place homes: for each player, pick a perimeter cell on alternating
   sides of the ridge, near a pass. Half the players home on one side,
   half on the other; players adjacent to the same pass come from
   opposite sides (forces them to meet at the pass).
7. ~35% of remaining (non-mountain, non-home) cells as SUPPLY → austere
   passes make each contested supply matter more.
8. Build adjacency, excluding edges to/from MOUNTAIN cells.
9. Return Map.
```

**Edge case:** if the ridge would isolate any player from their home,
re-roll the ridge direction up to N times (default 5). If still
infeasible, fall back to fewer mountain cells along the ridge.

### `RIVERLANDS`

```
1. Generate hex disk of radius map_radius; remove 0-1 random cells
   (minimal variation; the river itself supplies the structure).
2. Pick two roughly opposite perimeter cells as the river endpoints.
3. Compute a midpoint waypoint perpendicular-offset from the
   straight ep_a->ep_b segment by a random amount (~30% of the
   straight-line length); snap to the closest live coord. The two
   hex line traces (ep_a->waypoint, waypoint->ep_b) form the snake.
4. Gather all live cells whose center is within ~0.85 of either
   line segment as river candidates.
5. Pick exactly 2 evenly-spaced river candidates (sorted along the
   path) as CROSSINGS — these stay passable. Endpoints (ep_a, ep_b)
   are also forced to be passable (homes need them).
6. Mark remaining river candidates as WATER.
7. Place homes evenly along the passable perimeter.
8. Verify all homes are mutually reachable through the crossings;
   re-roll up to 5 attempts if not.
9. ~40% of remaining (non-home, non-water) cells as SUPPLY.
10. Build adjacency, excluding edges to/from WATER cells.
11. Return Map.
```

**Edge case:** if all 5 attempts fail (e.g., snake is too short or
crossings can't connect both regions), fall back to UNIFORM with a
logging.warning.

## 8. Adjacency and passability rules

### MOUNTAIN/WATER hexes

- `Map.edges[mountain_or_water_node] == frozenset()` — no neighbors
- For every other node `n`, `Map.edges[n]` excludes any neighbor whose
  `node_type` is MOUNTAIN or WATER.
- `node_or_water_node not in ownership` — these nodes never appear in
  the ownership map.
- `Map.is_passable(n)` returns False for MOUNTAIN/WATER, True for
  PLAIN/SUPPLY/HOME.

### Order normalization

No changes needed to `_normalize` in `resolve.py` — the existing
adjacency check (`m.is_adjacent(unit.location, order.dest)`) already
handles MOUNTAIN/WATER correctly, since those hexes have empty edge
sets.

### Build phase

The build-phase logic in `_resolve_orders` filters candidates by
ownership. MOUNTAIN/WATER hexes are not in the ownership map, so they
are automatically excluded as build targets. No change needed.

### Scoring

`state.supply_count` and the per-turn supply scoring already filter
by `node_types[n] in (NodeType.SUPPLY, NodeType.HOME)`. MOUNTAIN/WATER
are excluded from this set, so no change needed.

## 9. Backward compatibility

- `GameConfig()` with no arguments produces an UNIFORM archetype map at
  `map_radius=3`, preserving exact v1 behavior.
- Existing 188 tests (96 v1 + 92 Press v0) pass without modification.
- The v1 `generate_map(num_players, seed)` call signature still works
  because new parameters have defaults.
- All press v0 helpers (`tests/helpers.py`) continue to use the v1
  uniform-map paths (`line_map`, `triangle_map`, etc.) which are
  hand-built and don't go through `generate_map`.
- CLI continues to work unchanged; an `--archetype` flag is a separate
  follow-up.

## 10. Configuration summary

| Param | Default | Purpose |
|---|---|---|
| `archetype` | `Archetype.UNIFORM` | Which archetype generator to use |
| `map_radius` | `3` | Hex disk radius (forward-compat for larger maps) |

## 11. Tests

### `tests/test_archetypes.py` (new)

- `test_archetype_enum_has_four_values` — UNIFORM, HIGHLAND_PASS,
  RIVERLANDS, CONTINENTAL_SWEEP
- `test_random_archetype_excludes_uniform` — sample 100 calls; UNIFORM
  never returned
- `test_random_archetype_seeded_deterministic` — same seed → same
  archetype
- `test_random_archetype_distribution` — 1000 samples cover all 3
  non-UNIFORM archetypes (no value should be < 200 samples)

### `tests/test_mapgen.py` (extended)

UNIFORM behavior:
- `test_uniform_archetype_preserves_v1_behavior` — generate with
  Archetype.UNIFORM and verify properties match the existing v1
  generator output exactly (same seed → same output)
- `test_default_archetype_is_uniform` — `generate_map(num_players=4,
  seed=42)` produces UNIFORM map
- All existing test_mapgen.py tests continue to pass

CONTINENTAL_SWEEP:
- `test_continental_sweep_no_terrain` — no MOUNTAIN, no WATER cells
- `test_continental_sweep_higher_supply_density` — supply count ≥ 50%
  of non-home nodes (within ±10%)
- `test_continental_sweep_dense_connectivity` — average node degree ≥
  some threshold (e.g., 4.5 vs UNIFORM's lower)

HIGHLAND_PASS:
- `test_highland_pass_has_mountains` — at least one MOUNTAIN node per
  generated map
- `test_highland_pass_has_passes` — at least one PLAIN cell along the
  ridge axis (i.e., a pass exists)
- `test_highland_pass_homes_reachable` — each home is reachable from
  every other home via passable cells (BFS on adjacency)
- `test_highland_pass_split_geography` — homes are split across the
  ridge (at least one home on each side)

RIVERLANDS:
- `test_riverlands_has_water` — at least one WATER node
- `test_riverlands_no_mountain` — no MOUNTAIN cells
- `test_riverlands_homes_reachable_through_crossings` — every home
  reachable from every other home via passable cells (i.e., crossings
  bridge the river)
- `test_riverlands_water_cells_have_no_edges` — WATER nodes have empty
  edge sets

Generator general properties:
- `test_all_archetypes_produce_valid_maps` — for each archetype, the
  generated Map satisfies basic invariants (every home_assignment
  references a HOME cell; every supply node is in node_types; etc.)
- `test_all_archetypes_seeded_deterministic` — for each archetype,
  same seed → same Map
- `test_all_archetypes_homes_match_player_count` — `len(home_assignments)
  == num_players`

### `tests/test_state_additions.py` (extended)

- `test_gameconfig_archetype_default_is_uniform`
- `test_gameconfig_map_radius_default_is_3`

## 12. What's deferred

- Terrain combat modifiers (forest defender bonus, mountain attacker
  penalty, etc.)
- Variable supply-center value (some supplies worth +2/+3)
- Additional archetypes (Verdant, City Crown, River Network, Inland
  Sea, City State) — all of which require new mechanics this spec
  doesn't introduce
- Convoys / cross-water movement
- **ARCHIPELAGO archetype.** Originally part of the v0.2 set, but
  deferred to v0.3 paired with convoy support. Without cross-water
  movement, players on separate islands cannot interact, making the
  archetype strategically degenerate. RIVERLANDS replaces it as the
  v0.2 water-themed archetype because the playable surface stays
  connected through the crossings.
- CLI `--archetype` flag (small follow-up)
- Map rendering: cli.py needs ASCII chars for MOUNTAIN/WATER. Plan
  task will include this. Suggested: `^` for MOUNTAIN, `~` for WATER.
- Asymmetric starting conditions tied to archetype (e.g., island
  power has +1 starting unit)

## 13. Open questions for review

1. **Highland Pass orientation.** Should the ridge axis be uniformly
   random, or constrained to certain angles for better playability
   (e.g., horizontal/vertical only)? Random is simpler; constrained
   may produce more recognizable maps.
2. **Pass count formula.** `1 + num_players // 3` gives 1 pass for
   2-3 players, 2 for 4-5, 3 for 6. Is this the right scaling?
3. **Riverlands snake amplitude.** The waypoint perpendicular offset
   is sampled uniformly from ±30% of the straight-line length. Larger
   offsets create more dramatic snakes but more re-roll failures; is
   30% the right ceiling?
4. **Continental Sweep degree threshold.** What's the "right" average
   node degree for "denser than UNIFORM"? My test threshold is 4.5
   but it may need tuning post-implementation.
5. **Archetype names.** Are these final, or do we want more evocative
   names ("The Iron Pass" / "Two Fords" / "Open Steppe")?

## 14. Appendix — generator pseudocode flow

For a quick end-to-end sense:

```python
def generate_map(num_players, seed=None, archetype=Archetype.UNIFORM,
                 map_radius=3) -> Map:
    rng = random.Random(seed)
    if archetype == Archetype.UNIFORM:
        return _gen_uniform(num_players, rng, map_radius)
    elif archetype == Archetype.CONTINENTAL_SWEEP:
        return _gen_continental_sweep(num_players, rng, map_radius)
    elif archetype == Archetype.HIGHLAND_PASS:
        return _gen_highland_pass(num_players, rng, map_radius)
    elif archetype == Archetype.RIVERLANDS:
        return _gen_riverlands(num_players, rng, map_radius)
    else:
        raise ValueError(f"Unknown archetype: {archetype}")
```

Each `_gen_*` function shares a common skeleton (hex disk → cell
classification → adjacency → home placement → supply assignment) but
varies the specific steps per archetype's strategic intent.
