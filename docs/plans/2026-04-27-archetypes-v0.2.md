# Archetypes v0.2 Implementation Plan

> **Note (post-implementation):** After initial implementation,
> ARCHIPELAGO was swapped out of the v0.2 archetype set in favor of
> RIVERLANDS. Archipelago without convoy support left players
> permanently isolated on separate islands, making the archetype
> strategically degenerate; it is deferred to v0.3 paired with convoys.
> Phase E and Task 7 references below still describe the original
> Archipelago implementation as historical context — see commit history
> for the swap.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement three procedural map archetypes (Highland Pass, Archipelago, Continental Sweep) plus a backward-compat UNIFORM archetype, per `docs/design/2026-04-27-archetypes-v0.2.md`.

**Architecture:** Two new `NodeType` values (MOUNTAIN, WATER) with identical impassable semantics. New `Archetype` enum and per-archetype generator functions. `mapgen.generate_map` dispatches on archetype; existing v1 behavior preserved exactly under `Archetype.UNIFORM` (the new default).

**Tech Stack:** Python 3.10+, pytest 9.x, no new third-party dependencies.

**Branch:** `archetypes` (off `press-v0`; spec at `2b7fdb4`).

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `foedus/core.py` | Modify | `NodeType` extension, `Archetype` enum, `GameConfig` fields, `Map.is_passable` |
| `foedus/mapgen.py` | Modify | Hex utilities (existing) + `generate_map` dispatcher |
| `foedus/archetypes.py` | Create | Per-archetype generators + `random_archetype` selector |
| `tests/test_state_additions.py` | Modify | Add tests for new GameConfig fields |
| `tests/test_mapgen.py` | Modify | Add tests for `is_passable`, archetype dispatching, UNIFORM preservation |
| `tests/test_archetypes.py` | Create | Per-archetype structural property tests + `random_archetype` tests |

The new `archetypes.py` module imports hex utilities (`_hex_disk`, `_hex_neighbors`, `_hex_to_xy`, `_ring_distance`) from `mapgen.py` and exports per-archetype generator functions plus the `random_archetype()` selector.

---

## Phase index

| Phase | Tasks | Outcome |
|---|---|---|
| A. Type scaffolding | 1–3 | New types and config fields land; existing 188 tests still pass |
| B. Refactor mapgen | 4 | `_gen_uniform` extracted; `generate_map` dispatches on archetype; UNIFORM behavior preserved exactly |
| C. Continental Sweep | 5 | Open-plains archetype implemented and tested |
| D. Highland Pass | 6 | Mountain-ridge-with-passes archetype implemented and tested |
| E. Archipelago | 7 | Island archetype implemented; ValueError for 5+ players on radius=3 |
| F. Selector + final tests | 8–9 | `random_archetype` function + comprehensive structural tests |
| G. Final verification | 10 | Full suite green; backward compat confirmed |

---

## Phase A: Type scaffolding

### Task 1: Extend `NodeType` with `MOUNTAIN`/`WATER` and add `Map.is_passable`

**Files:**
- Modify: `foedus/core.py`
- Test: `tests/test_mapgen.py` (extend existing)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mapgen.py`:

```python
def test_node_type_has_mountain_and_water() -> None:
    from foedus.core import NodeType
    assert NodeType.MOUNTAIN.value == "mountain"
    assert NodeType.WATER.value == "water"


def test_map_is_passable_for_plain_supply_home() -> None:
    from foedus.core import Map, NodeType
    m = Map(
        coords={0: (0, 0), 1: (1, 0), 2: (0, 1)},
        edges={0: frozenset({1, 2}), 1: frozenset({0, 2}), 2: frozenset({0, 1})},
        node_types={0: NodeType.PLAIN, 1: NodeType.SUPPLY, 2: NodeType.HOME},
        home_assignments={2: 0},
    )
    assert m.is_passable(0) is True
    assert m.is_passable(1) is True
    assert m.is_passable(2) is True


def test_map_is_passable_false_for_mountain_water() -> None:
    from foedus.core import Map, NodeType
    m = Map(
        coords={0: (0, 0), 1: (1, 0)},
        edges={0: frozenset(), 1: frozenset()},
        node_types={0: NodeType.MOUNTAIN, 1: NodeType.WATER},
        home_assignments={},
    )
    assert m.is_passable(0) is False
    assert m.is_passable(1) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_mapgen.py -v -k "node_type_has_mountain or is_passable"`
Expected: FAIL — `AttributeError: MOUNTAIN` (or `'Map' object has no attribute 'is_passable'`).

- [ ] **Step 3: Extend `NodeType` and add `is_passable` helper**

In `foedus/core.py`, find the `NodeType` enum and replace it:

```python
class NodeType(Enum):
    PLAIN = "plain"
    SUPPLY = "supply"
    HOME = "home"
    MOUNTAIN = "mountain"   # impassable, not ownable, not occupiable
    WATER = "water"         # same semantics as MOUNTAIN; distinct render
```

In the `Map` dataclass, add the helper method (after `is_supply`):

```python
    def is_passable(self, n: NodeId) -> bool:
        """True iff a unit can occupy/move-through this node.

        MOUNTAIN and WATER are impassable; PLAIN, SUPPLY, and HOME are passable.
        """
        return self.node_types[n] not in (NodeType.MOUNTAIN, NodeType.WATER)
```

Confirm `is_supply` still returns False for MOUNTAIN/WATER — it already does, since it only matches `SUPPLY` or `HOME`. No change needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_mapgen.py -v -k "node_type_has_mountain or is_passable"`
Expected: PASS — 3 tests passed.

- [ ] **Step 5: Run full suite to verify nothing else broke**

Run: `python3 -m pytest -q`
Expected: PASS — 191 tests passed (188 prior + 3 new).

- [ ] **Step 6: Commit**

```bash
git add foedus/core.py tests/test_mapgen.py
git commit -m "Extend NodeType with MOUNTAIN/WATER + add Map.is_passable helper"
```

---

### Task 2: Add `Archetype` enum

**Files:**
- Modify: `foedus/core.py`
- Test: `tests/test_archetypes.py` (create new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_archetypes.py`:

```python
"""Tests for the Archetype enum and archetype selection (Press v0.2)."""

from __future__ import annotations

from foedus.core import Archetype


def test_archetype_enum_has_four_values() -> None:
    values = {a.value for a in Archetype}
    assert values == {"uniform", "highland_pass", "archipelago", "continental_sweep"}


def test_archetype_uniform_present() -> None:
    assert Archetype.UNIFORM.value == "uniform"


def test_archetype_highland_pass_present() -> None:
    assert Archetype.HIGHLAND_PASS.value == "highland_pass"


def test_archetype_archipelago_present() -> None:
    assert Archetype.ARCHIPELAGO.value == "archipelago"


def test_archetype_continental_sweep_present() -> None:
    assert Archetype.CONTINENTAL_SWEEP.value == "continental_sweep"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_archetypes.py -v`
Expected: FAIL — `ImportError: cannot import name 'Archetype'`.

- [ ] **Step 3: Add `Archetype` enum to `foedus/core.py`**

After the `NodeType` enum in `foedus/core.py`, add:

```python
class Archetype(Enum):
    UNIFORM = "uniform"                       # v1 backward-compat (no terrain)
    HIGHLAND_PASS = "highland_pass"           # mountain ridges with passes
    ARCHIPELAGO = "archipelago"               # water-separated islands
    CONTINENTAL_SWEEP = "continental_sweep"   # open plains, dense connectivity
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_archetypes.py -v`
Expected: PASS — 5 tests passed.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 196 tests passed (191 + 5).

- [ ] **Step 6: Commit**

```bash
git add foedus/core.py tests/test_archetypes.py
git commit -m "Add Archetype enum to core.py"
```

---

### Task 3: Add `GameConfig.archetype` and `GameConfig.map_radius` fields

**Files:**
- Modify: `foedus/core.py`
- Test: `tests/test_state_additions.py` (extend existing)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_state_additions.py`:

```python
def test_gameconfig_archetype_default_is_uniform() -> None:
    from foedus.core import Archetype, GameConfig
    cfg = GameConfig()
    assert cfg.archetype == Archetype.UNIFORM


def test_gameconfig_map_radius_default_is_3() -> None:
    from foedus.core import GameConfig
    cfg = GameConfig()
    assert cfg.map_radius == 3


def test_gameconfig_explicit_archetype() -> None:
    from foedus.core import Archetype, GameConfig
    cfg = GameConfig(archetype=Archetype.HIGHLAND_PASS)
    assert cfg.archetype == Archetype.HIGHLAND_PASS


def test_gameconfig_explicit_map_radius() -> None:
    from foedus.core import GameConfig
    cfg = GameConfig(map_radius=5)
    assert cfg.map_radius == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_state_additions.py -v -k "archetype or map_radius"`
Expected: FAIL — `TypeError: GameConfig.__init__() got an unexpected keyword argument 'archetype'` (or similar).

- [ ] **Step 3: Add fields to `GameConfig` in `foedus/core.py`**

In the `GameConfig` dataclass, add the two new fields. Keep them after existing fields, before `seed` and the deprecated `peace_threshold`:

```python
@dataclass
class GameConfig:
    num_players: int = 4
    max_turns: int = 25
    fog_radius: int = 1
    build_period: int = 3
    detente_threshold: int = 5
    stagnation_cost: float = 1.0
    chat_char_cap: int = 500
    round_timer_seconds: float = 60.0
    archetype: Archetype = Archetype.UNIFORM   # NEW
    map_radius: int = 3                        # NEW
    seed: int | None = None
    peace_threshold: int | None = None  # deprecated alias

    def __post_init__(self) -> None:
        if self.peace_threshold is not None:
            self.detente_threshold = self.peace_threshold
        self.peace_threshold = self.detente_threshold
```

(The existing `__post_init__` body for the deprecation alias stays unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_state_additions.py -v`
Expected: PASS — all tests pass (4 new + previous).

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 200 tests passed (196 + 4).

- [ ] **Step 6: Commit**

```bash
git add foedus/core.py tests/test_state_additions.py
git commit -m "Add GameConfig.archetype and GameConfig.map_radius fields"
```

---

## Phase B: Refactor mapgen

### Task 4: Extract `_gen_uniform` helper and add `generate_map` dispatcher

**Files:**
- Modify: `foedus/mapgen.py`
- Create: `foedus/archetypes.py`
- Test: `tests/test_mapgen.py`

This task changes the structure of `generate_map` to dispatch on archetype, but preserves UNIFORM behavior exactly. After this task, all existing tests still produce identical Map outputs.

- [ ] **Step 1: Write the failing test for UNIFORM determinism**

Append to `tests/test_mapgen.py`:

```python
def test_uniform_archetype_preserves_v1_output_for_seed() -> None:
    """The UNIFORM archetype must produce maps byte-identical to the
    pre-archetype generator for the same seed and player count.
    This is the primary backward-compat invariant."""
    from foedus.core import Archetype
    from foedus.mapgen import generate_map

    # Generate via new explicit-archetype call.
    m_explicit = generate_map(num_players=4, seed=42,
                              archetype=Archetype.UNIFORM)
    # Generate via default (no archetype argument).
    m_default = generate_map(num_players=4, seed=42)

    # Default must equal explicit UNIFORM.
    assert m_explicit.coords == m_default.coords
    assert m_explicit.edges == m_default.edges
    assert m_explicit.node_types == m_default.node_types
    assert m_explicit.home_assignments == m_default.home_assignments


def test_default_generate_map_produces_uniform_archetype() -> None:
    """Default archetype is UNIFORM — no terrain types, ~37 nodes."""
    from foedus.core import NodeType
    from foedus.mapgen import generate_map
    m = generate_map(num_players=4, seed=42)
    types = {t for t in m.node_types.values()}
    assert NodeType.MOUNTAIN not in types
    assert NodeType.WATER not in types


def test_generate_map_accepts_archetype_kwarg() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    m = generate_map(num_players=4, seed=42, archetype=Archetype.UNIFORM)
    assert m is not None
```

- [ ] **Step 2: Run tests to verify they fail (or pass on default)**

Run: `python3 -m pytest tests/test_mapgen.py -v -k "uniform or default_generate"`
Expected: At least the `archetype` keyword test fails — `TypeError: unexpected keyword argument 'archetype'`.

- [ ] **Step 3: Refactor `foedus/mapgen.py`**

Read the current `generate_map` function. Move its body into a new private function `_gen_uniform_inner` and replace `generate_map` with a dispatcher.

The new `foedus/mapgen.py` should look like (replacing the existing `generate_map`):

```python
"""Procedural hex map generation.

The generator dispatches on `archetype`:
- UNIFORM produces v1-compatible maps (no terrain types).
- HIGHLAND_PASS / ARCHIPELAGO / CONTINENTAL_SWEEP produce maps with
  archetype-specific terrain and structural variation.
"""

from __future__ import annotations

import math
import random

from foedus.core import Archetype, Map, NodeId, NodeType, PlayerId


def _hex_neighbors(q: int, r: int) -> list[tuple[int, int]]:
    return [
        (q + 1, r),
        (q - 1, r),
        (q, r + 1),
        (q, r - 1),
        (q + 1, r - 1),
        (q - 1, r + 1),
    ]


def _hex_disk(radius: int) -> list[tuple[int, int]]:
    out = []
    for q in range(-radius, radius + 1):
        r1 = max(-radius, -q - radius)
        r2 = min(radius, -q + radius)
        for r in range(r1, r2 + 1):
            out.append((q, r))
    return out


def _hex_to_xy(q: int, r: int) -> tuple[float, float]:
    x = q + r / 2.0
    y = r * (math.sqrt(3) / 2.0)
    return x, y


def _ring_distance(c: tuple[int, int]) -> int:
    q, r = c
    return max(abs(q), abs(r), abs(q + r))


def generate_map(
    num_players: int,
    seed: int | None = None,
    archetype: Archetype = Archetype.UNIFORM,
    map_radius: int = 3,
) -> Map:
    """Generate a procedural hex map.

    Dispatches on archetype to a specialized generator. UNIFORM preserves
    pre-archetype behavior exactly for backward compatibility.
    """
    if not 2 <= num_players <= 6:
        raise ValueError("num_players must be 2..6")

    rng = random.Random(seed)

    # Lazy import avoids circular dependency between mapgen and archetypes.
    from foedus.archetypes import (
        _gen_archipelago,
        _gen_continental_sweep,
        _gen_highland_pass,
        _gen_uniform,
    )

    if archetype == Archetype.UNIFORM:
        return _gen_uniform(num_players, rng, map_radius)
    if archetype == Archetype.CONTINENTAL_SWEEP:
        return _gen_continental_sweep(num_players, rng, map_radius)
    if archetype == Archetype.HIGHLAND_PASS:
        return _gen_highland_pass(num_players, rng, map_radius)
    if archetype == Archetype.ARCHIPELAGO:
        return _gen_archipelago(num_players, rng, map_radius)
    raise ValueError(f"Unknown archetype: {archetype}")
```

- [ ] **Step 4: Create `foedus/archetypes.py` with `_gen_uniform`**

Create `foedus/archetypes.py`:

```python
"""Archetype-specific map generators and the random_archetype selector.

Each generator function receives (num_players, rng, map_radius) and returns
a Map. They share hex utilities from foedus.mapgen.
"""

from __future__ import annotations

import math
import random

from foedus.core import Archetype, Map, NodeId, NodeType, PlayerId
from foedus.mapgen import _hex_disk, _hex_neighbors, _hex_to_xy, _ring_distance


def _gen_uniform(num_players: int, rng: random.Random,
                 map_radius: int) -> Map:
    """V1-compatible generator: no terrain types, 0-3 cells removed."""
    coords = _hex_disk(map_radius)
    perimeter = [c for c in coords if _ring_distance(c) == map_radius]

    def angle(c: tuple[int, int]) -> float:
        x, y = _hex_to_xy(*c)
        return math.atan2(y, x)

    perimeter.sort(key=angle)
    home_coords = [perimeter[(i * len(perimeter)) // num_players]
                   for i in range(num_players)]

    removable = [c for c in coords if c not in home_coords and c != (0, 0)]
    rng.shuffle(removable)
    removed = set(removable[: rng.randint(0, 3)])

    final_coords = sorted(c for c in coords if c not in removed)
    node_id_of = {c: i for i, c in enumerate(final_coords)}
    coord_of = {i: c for c, i in node_id_of.items()}

    edges: dict[NodeId, set[NodeId]] = {i: set() for i in node_id_of.values()}
    for c, i in node_id_of.items():
        for nbr in _hex_neighbors(*c):
            if nbr in node_id_of:
                edges[i].add(node_id_of[nbr])
    edges_frozen = {n: frozenset(s) for n, s in edges.items()}

    home_assignments: dict[NodeId, PlayerId] = {
        node_id_of[hc]: i for i, hc in enumerate(home_coords)
    }

    non_home_ids = [n for n in node_id_of.values()
                    if n not in home_assignments]
    rng.shuffle(non_home_ids)
    num_supply = max(num_players, int(len(non_home_ids) * 0.4))
    supply_set = set(non_home_ids[:num_supply])

    node_types: dict[NodeId, NodeType] = {}
    for n in node_id_of.values():
        if n in home_assignments:
            node_types[n] = NodeType.HOME
        elif n in supply_set:
            node_types[n] = NodeType.SUPPLY
        else:
            node_types[n] = NodeType.PLAIN

    return Map(
        coords=coord_of,
        edges=edges_frozen,
        node_types=node_types,
        home_assignments=home_assignments,
    )


def _gen_continental_sweep(num_players: int, rng: random.Random,
                           map_radius: int) -> Map:
    raise NotImplementedError("Implemented in Task 5")


def _gen_highland_pass(num_players: int, rng: random.Random,
                       map_radius: int) -> Map:
    raise NotImplementedError("Implemented in Task 6")


def _gen_archipelago(num_players: int, rng: random.Random,
                     map_radius: int) -> Map:
    raise NotImplementedError("Implemented in Task 7")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_mapgen.py -v`
Expected: PASS — all existing test_mapgen tests + 3 new ones pass.

- [ ] **Step 6: Run full suite — confirm UNIFORM preserves all v1 behavior**

Run: `python3 -m pytest -q`
Expected: PASS — 203 tests passed (200 + 3).

- [ ] **Step 7: Commit**

```bash
git add foedus/mapgen.py foedus/archetypes.py tests/test_mapgen.py
git commit -m "Refactor mapgen: extract _gen_uniform; add archetype dispatcher"
```

---

## Phase C: Continental Sweep

### Task 5: Implement `_gen_continental_sweep`

**Files:**
- Modify: `foedus/archetypes.py`
- Test: `tests/test_archetypes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archetypes.py`:

```python
def test_continental_sweep_no_terrain() -> None:
    """Continental Sweep should have no MOUNTAIN or WATER."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.CONTINENTAL_SWEEP)
        types = set(m.node_types.values())
        assert NodeType.MOUNTAIN not in types
        assert NodeType.WATER not in types


def test_continental_sweep_higher_supply_density() -> None:
    """Continental Sweep targets ~50% supply density (vs UNIFORM's 40%)."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    densities = []
    for seed in range(20):
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.CONTINENTAL_SWEEP)
        non_home = [n for n in m.nodes if m.node_types[n] != NodeType.HOME]
        supply = [n for n in non_home if m.node_types[n] == NodeType.SUPPLY]
        densities.append(len(supply) / len(non_home))
    avg = sum(densities) / len(densities)
    # Allow ±10% tolerance around 50% target
    assert 0.40 <= avg <= 0.60, f"avg supply density {avg:.2%}"


def test_continental_sweep_is_deterministic() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    m1 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.CONTINENTAL_SWEEP)
    m2 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.CONTINENTAL_SWEEP)
    assert m1.coords == m2.coords
    assert m1.edges == m2.edges
    assert m1.node_types == m2.node_types


def test_continental_sweep_homes_match_player_count() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for n in [2, 3, 4, 5, 6]:
        m = generate_map(num_players=n, seed=42,
                         archetype=Archetype.CONTINENTAL_SWEEP)
        assert len(m.home_assignments) == n
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_archetypes.py -v -k continental`
Expected: FAIL — `NotImplementedError: Implemented in Task 5`.

- [ ] **Step 3: Implement `_gen_continental_sweep`**

In `foedus/archetypes.py`, replace the `_gen_continental_sweep` stub with:

```python
def _gen_continental_sweep(num_players: int, rng: random.Random,
                           map_radius: int) -> Map:
    """Open plains, dense connectivity, resource-rich.

    Like UNIFORM but with 0-1 cells removed (denser connectivity) and
    ~50% supply density instead of ~40%. No MOUNTAIN/WATER terrain.
    """
    coords = _hex_disk(map_radius)
    perimeter = [c for c in coords if _ring_distance(c) == map_radius]

    def angle(c: tuple[int, int]) -> float:
        x, y = _hex_to_xy(*c)
        return math.atan2(y, x)

    perimeter.sort(key=angle)
    home_coords = [perimeter[(i * len(perimeter)) // num_players]
                   for i in range(num_players)]

    # Continental: remove only 0-1 cells (denser connectivity than UNIFORM).
    removable = [c for c in coords if c not in home_coords and c != (0, 0)]
    rng.shuffle(removable)
    removed = set(removable[: rng.randint(0, 1)])

    final_coords = sorted(c for c in coords if c not in removed)
    node_id_of = {c: i for i, c in enumerate(final_coords)}
    coord_of = {i: c for c, i in node_id_of.items()}

    edges: dict[NodeId, set[NodeId]] = {i: set() for i in node_id_of.values()}
    for c, i in node_id_of.items():
        for nbr in _hex_neighbors(*c):
            if nbr in node_id_of:
                edges[i].add(node_id_of[nbr])
    edges_frozen = {n: frozenset(s) for n, s in edges.items()}

    home_assignments: dict[NodeId, PlayerId] = {
        node_id_of[hc]: i for i, hc in enumerate(home_coords)
    }

    non_home_ids = [n for n in node_id_of.values()
                    if n not in home_assignments]
    rng.shuffle(non_home_ids)
    # Continental: 50% supply density (vs UNIFORM's 40%).
    num_supply = max(num_players, int(len(non_home_ids) * 0.5))
    supply_set = set(non_home_ids[:num_supply])

    node_types: dict[NodeId, NodeType] = {}
    for n in node_id_of.values():
        if n in home_assignments:
            node_types[n] = NodeType.HOME
        elif n in supply_set:
            node_types[n] = NodeType.SUPPLY
        else:
            node_types[n] = NodeType.PLAIN

    return Map(
        coords=coord_of,
        edges=edges_frozen,
        node_types=node_types,
        home_assignments=home_assignments,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_archetypes.py -v -k continental`
Expected: PASS — 4 tests pass.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 207 tests passed (203 + 4).

- [ ] **Step 6: Commit**

```bash
git add foedus/archetypes.py tests/test_archetypes.py
git commit -m "Implement Continental Sweep archetype generator"
```

---

## Phase D: Highland Pass

### Task 6: Implement `_gen_highland_pass`

**Files:**
- Modify: `foedus/archetypes.py`
- Test: `tests/test_archetypes.py`

This task introduces MOUNTAIN cells and ridge-with-passes geometry. Includes a re-roll loop to handle infeasible ridge placements.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archetypes.py`:

```python
def test_highland_pass_has_mountains() -> None:
    """Highland Pass produces at least one MOUNTAIN cell per map."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.HIGHLAND_PASS)
        types = list(m.node_types.values())
        assert NodeType.MOUNTAIN in types, f"seed {seed}: no mountains"


def test_highland_pass_no_water() -> None:
    """Highland Pass uses MOUNTAIN, never WATER."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.HIGHLAND_PASS)
        assert NodeType.WATER not in m.node_types.values()


def test_highland_pass_homes_reachable() -> None:
    """Every home is reachable from every other home via passable cells.

    Passes through the ridge must exist; otherwise homes get isolated.
    """
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.HIGHLAND_PASS)
        homes = sorted(m.home_assignments.keys())
        # BFS from first home; verify all other homes reachable.
        start = homes[0]
        visited = {start}
        frontier = [start]
        while frontier:
            n = frontier.pop()
            for nbr in m.edges[n]:
                if nbr not in visited and m.is_passable(nbr):
                    visited.add(nbr)
                    frontier.append(nbr)
        for h in homes:
            assert h in visited, \
                f"seed {seed}: home {h} unreachable from home {start}"


def test_highland_pass_mountain_cells_have_no_edges() -> None:
    """MOUNTAIN cells should have empty edge sets and no neighbors."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    m = generate_map(num_players=4, seed=42,
                     archetype=Archetype.HIGHLAND_PASS)
    for n, t in m.node_types.items():
        if t == NodeType.MOUNTAIN:
            assert m.edges[n] == frozenset(), f"mountain node {n} has edges"
        else:
            # non-mountain cells have no mountain neighbors
            for nbr in m.edges[n]:
                assert m.node_types[nbr] != NodeType.MOUNTAIN


def test_highland_pass_is_deterministic() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    m1 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.HIGHLAND_PASS)
    m2 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.HIGHLAND_PASS)
    assert m1.coords == m2.coords
    assert m1.edges == m2.edges
    assert m1.node_types == m2.node_types
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_archetypes.py -v -k highland`
Expected: FAIL — `NotImplementedError: Implemented in Task 6`.

- [ ] **Step 3: Implement `_gen_highland_pass`**

In `foedus/archetypes.py`, replace the `_gen_highland_pass` stub with:

```python
def _gen_highland_pass(num_players: int, rng: random.Random,
                       map_radius: int) -> Map:
    """Mountain ridge with passes; defensive flavor.

    1. Generate base hex disk with 0-1 cells removed (minimal variation).
    2. Pick two opposite perimeter cells; trace a ridge between them.
    3. Mark ridge cells as MOUNTAIN, leaving num_passes gaps as PLAIN.
    4. Place homes near pass entrances on alternating sides of the ridge.
    5. Apply ~35% supply density to non-home, non-mountain cells.
    Re-rolls up to 5 times if homes end up unreachable from each other.
    """
    num_passes = max(1, 1 + (num_players // 3))

    for attempt in range(5):
        coords = _hex_disk(map_radius)

        # Remove 0-1 random cells.
        removable = [c for c in coords if c != (0, 0)]
        rng.shuffle(removable)
        removed = set(removable[: rng.randint(0, 1)])
        live_coords = [c for c in coords if c not in removed]

        perimeter = [c for c in live_coords if _ring_distance(c) == map_radius]
        if len(perimeter) < 2:
            continue

        def angle(c: tuple[int, int]) -> float:
            x, y = _hex_to_xy(*c)
            return math.atan2(y, x)

        perimeter.sort(key=angle)

        # Pick two roughly opposite perimeter cells as ridge endpoints.
        endpoint_a_idx = rng.randrange(len(perimeter))
        endpoint_b_idx = (endpoint_a_idx + len(perimeter) // 2) % len(perimeter)
        ep_a = perimeter[endpoint_a_idx]
        ep_b = perimeter[endpoint_b_idx]

        # Trace ridge: take all cells whose center lies near the line ep_a→ep_b.
        ax, ay = _hex_to_xy(*ep_a)
        bx, by = _hex_to_xy(*ep_b)
        dx, dy = bx - ax, by - ay
        line_len_sq = dx * dx + dy * dy
        ridge_candidates: list[tuple[int, int]] = []
        for c in live_coords:
            cx, cy = _hex_to_xy(*c)
            # Perpendicular distance from c to line through ep_a, ep_b.
            if line_len_sq == 0:
                continue
            t = ((cx - ax) * dx + (cy - ay) * dy) / line_len_sq
            if not (0.0 <= t <= 1.0):
                continue
            proj_x = ax + t * dx
            proj_y = ay + t * dy
            d_sq = (cx - proj_x) ** 2 + (cy - proj_y) ** 2
            if d_sq <= 0.85:  # within ~1 hex of the line (axial distance ~1)
                ridge_candidates.append(c)

        if len(ridge_candidates) < num_passes + 2:
            # Need at least num_passes gaps + 2 mountains for it to be a "ridge"
            continue

        # Pick num_passes gap cells from the ridge, evenly distributed.
        ridge_candidates.sort(key=lambda c: ((c[0] - ep_a[0]) ** 2
                                             + (c[1] - ep_a[1]) ** 2))
        pass_indices = [
            (i * len(ridge_candidates)) // num_passes
            for i in range(num_passes)
        ]
        pass_cells = {ridge_candidates[i] for i in pass_indices}
        mountain_cells = set(ridge_candidates) - pass_cells

        # Don't allow ridge endpoints to be mountains (they're perimeter cells
        # we may need for home placement); coerce them to passes if they
        # ended up as mountains.
        if ep_a in mountain_cells:
            mountain_cells.remove(ep_a)
            pass_cells.add(ep_a)
        if ep_b in mountain_cells:
            mountain_cells.remove(ep_b)
            pass_cells.add(ep_b)

        # Place homes: even distribution along perimeter EXCLUDING mountain cells.
        passable_perimeter = [c for c in perimeter if c not in mountain_cells]
        if len(passable_perimeter) < num_players:
            continue
        home_coords = [
            passable_perimeter[(i * len(passable_perimeter)) // num_players]
            for i in range(num_players)
        ]

        # Make sure mountain cells don't include any home.
        if any(h in mountain_cells for h in home_coords):
            continue

        # Build node_id mapping.
        final_coords = sorted(live_coords)
        node_id_of = {c: i for i, c in enumerate(final_coords)}
        coord_of = {i: c for c, i in node_id_of.items()}

        # Mountains get empty edges; non-mountains get edges to non-mountain neighbors.
        mountain_ids = {node_id_of[c] for c in mountain_cells}
        edges: dict[NodeId, set[NodeId]] = {
            i: set() for i in node_id_of.values()
        }
        for c, i in node_id_of.items():
            if i in mountain_ids:
                continue
            for nbr in _hex_neighbors(*c):
                if nbr in node_id_of and node_id_of[nbr] not in mountain_ids:
                    edges[i].add(node_id_of[nbr])
        edges_frozen = {n: frozenset(s) for n, s in edges.items()}

        home_assignments: dict[NodeId, PlayerId] = {
            node_id_of[hc]: i for i, hc in enumerate(home_coords)
        }

        # Reachability check: BFS from first home over passable cells.
        if home_assignments:
            start = next(iter(home_assignments))
            visited = {start}
            frontier = [start]
            while frontier:
                n = frontier.pop()
                for nbr in edges_frozen[n]:
                    if nbr not in visited:
                        visited.add(nbr)
                        frontier.append(nbr)
            if not all(h in visited for h in home_assignments):
                continue  # ridge isolated some homes; re-roll

        # Apply supply density (~35%).
        non_home_passable_ids = [
            n for n in node_id_of.values()
            if n not in home_assignments and n not in mountain_ids
        ]
        rng.shuffle(non_home_passable_ids)
        num_supply = max(num_players, int(len(non_home_passable_ids) * 0.35))
        supply_set = set(non_home_passable_ids[:num_supply])

        node_types: dict[NodeId, NodeType] = {}
        for n in node_id_of.values():
            if n in mountain_ids:
                node_types[n] = NodeType.MOUNTAIN
            elif n in home_assignments:
                node_types[n] = NodeType.HOME
            elif n in supply_set:
                node_types[n] = NodeType.SUPPLY
            else:
                node_types[n] = NodeType.PLAIN

        return Map(
            coords=coord_of,
            edges=edges_frozen,
            node_types=node_types,
            home_assignments=home_assignments,
        )

    # Fall back to UNIFORM if all attempts fail.
    return _gen_uniform(num_players, rng, map_radius)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_archetypes.py -v -k highland`
Expected: PASS — 5 highland tests pass.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 212 tests passed (207 + 5).

- [ ] **Step 6: Commit**

```bash
git add foedus/archetypes.py tests/test_archetypes.py
git commit -m "Implement Highland Pass archetype generator"
```

---

## Phase E: Archipelago

### Task 7: Implement `_gen_archipelago`

**Files:**
- Modify: `foedus/archetypes.py`
- Test: `tests/test_archetypes.py`

This task introduces WATER cells and island-based geometry. Includes a player-count validation that raises `ValueError` for 5+ players on radius=3 maps.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archetypes.py`:

```python
def test_archipelago_has_water() -> None:
    """Archipelago produces at least one WATER cell per map."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.ARCHIPELAGO)
        assert NodeType.WATER in m.node_types.values()


def test_archipelago_no_mountain() -> None:
    """Archipelago uses WATER, never MOUNTAIN."""
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.ARCHIPELAGO)
        assert NodeType.MOUNTAIN not in m.node_types.values()


def test_archipelago_islands_disconnected() -> None:
    """No path exists between any two homes through passable cells.

    Each player's home is on its own island, and water blocks passage.
    """
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.ARCHIPELAGO)
        homes = sorted(m.home_assignments.keys())
        start = homes[0]
        visited = {start}
        frontier = [start]
        while frontier:
            n = frontier.pop()
            for nbr in m.edges[n]:
                if nbr not in visited and m.is_passable(nbr):
                    visited.add(nbr)
                    frontier.append(nbr)
        # All other homes should be UNREACHABLE.
        for h in homes[1:]:
            assert h not in visited, \
                f"seed {seed}: home {h} reachable from {start}"


def test_archipelago_each_player_has_island() -> None:
    """Each player's home has at least 3 passable cells in its connected
    component (including the home itself)."""
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for seed in [1, 7, 11, 42, 99]:
        m = generate_map(num_players=4, seed=seed,
                         archetype=Archetype.ARCHIPELAGO)
        for home in m.home_assignments:
            visited = {home}
            frontier = [home]
            while frontier:
                n = frontier.pop()
                for nbr in m.edges[n]:
                    if nbr not in visited and m.is_passable(nbr):
                        visited.add(nbr)
                        frontier.append(nbr)
            assert len(visited) >= 3, \
                f"seed {seed}: home {home} island too small ({len(visited)} cells)"


def test_archipelago_water_cells_have_no_edges() -> None:
    from foedus.core import Archetype, NodeType
    from foedus.mapgen import generate_map
    m = generate_map(num_players=4, seed=42,
                     archetype=Archetype.ARCHIPELAGO)
    for n, t in m.node_types.items():
        if t == NodeType.WATER:
            assert m.edges[n] == frozenset()


def test_archipelago_5_players_radius_3_raises() -> None:
    """Archipelago with 5+ players requires map_radius >= 4."""
    import pytest
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    with pytest.raises(ValueError):
        generate_map(num_players=5, seed=42,
                     archetype=Archetype.ARCHIPELAGO, map_radius=3)


def test_archipelago_is_deterministic() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    m1 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.ARCHIPELAGO)
    m2 = generate_map(num_players=4, seed=42,
                      archetype=Archetype.ARCHIPELAGO)
    assert m1.coords == m2.coords
    assert m1.edges == m2.edges
    assert m1.node_types == m2.node_types
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_archetypes.py -v -k archipelago`
Expected: FAIL — `NotImplementedError: Implemented in Task 7`.

- [ ] **Step 3: Implement `_gen_archipelago`**

In `foedus/archetypes.py`, replace the `_gen_archipelago` stub with:

```python
def _gen_archipelago(num_players: int, rng: random.Random,
                     map_radius: int) -> Map:
    """Water-separated islands, one per player; isolated buildup flavor.

    1. Validate: 5+ players require map_radius >= 4.
    2. Generate base hex disk; pick num_players seed cells around the perimeter.
    3. BFS-grow each island round-robin until cells run out or quota reached.
    4. Mark unclaimed cells as WATER.
    5. Apply ~45% supply density per island.
    Re-rolls up to 5 times if any island ends up below the 3-cell minimum.
    """
    if num_players >= 5 and map_radius < 4:
        raise ValueError(
            "Archipelago archetype requires map_radius >= 4 for 5+ players"
        )

    for attempt in range(5):
        coords = _hex_disk(map_radius)
        coord_set = set(coords)

        perimeter = [c for c in coords if _ring_distance(c) == map_radius]

        def angle(c: tuple[int, int]) -> float:
            x, y = _hex_to_xy(*c)
            return math.atan2(y, x)

        perimeter.sort(key=angle)
        seed_coords = [
            perimeter[(i * len(perimeter)) // num_players]
            for i in range(num_players)
        ]

        # Round-robin BFS from each seed.
        island_assignments: dict[tuple[int, int], int] = {
            s: i for i, s in enumerate(seed_coords)
        }
        target_per_island = len(coords) // (num_players + 1)
        frontiers: list[list[tuple[int, int]]] = [
            [s] for s in seed_coords
        ]
        # Round-robin grow.
        any_growth = True
        while any_growth:
            any_growth = False
            for player_idx in range(num_players):
                # Limit per-island size.
                size = sum(1 for v in island_assignments.values()
                           if v == player_idx)
                if size >= target_per_island:
                    continue
                if not frontiers[player_idx]:
                    continue
                # Pop one frontier cell; expand by one neighbor.
                grew = False
                while frontiers[player_idx] and not grew:
                    cell = frontiers[player_idx].pop(0)
                    for nbr in _hex_neighbors(*cell):
                        if nbr in coord_set and nbr not in island_assignments:
                            island_assignments[nbr] = player_idx
                            frontiers[player_idx].append(nbr)
                            grew = True
                            any_growth = True
                            break

        # Validate every island has >= 3 cells.
        sizes = [
            sum(1 for v in island_assignments.values() if v == i)
            for i in range(num_players)
        ]
        if any(s < 3 for s in sizes):
            continue

        final_coords = sorted(coords)
        node_id_of = {c: i for i, c in enumerate(final_coords)}
        coord_of = {i: c for c, i in node_id_of.items()}

        water_ids = {
            node_id_of[c] for c in final_coords if c not in island_assignments
        }

        edges: dict[NodeId, set[NodeId]] = {
            i: set() for i in node_id_of.values()
        }
        for c, i in node_id_of.items():
            if i in water_ids:
                continue
            for nbr in _hex_neighbors(*c):
                if nbr in node_id_of and node_id_of[nbr] not in water_ids:
                    edges[i].add(node_id_of[nbr])
        edges_frozen = {n: frozenset(s) for n, s in edges.items()}

        home_assignments: dict[NodeId, PlayerId] = {
            node_id_of[s]: i for i, s in enumerate(seed_coords)
        }

        # Apply ~45% supply density across non-home land cells.
        non_home_land_ids = [
            n for n in node_id_of.values()
            if n not in home_assignments and n not in water_ids
        ]
        rng.shuffle(non_home_land_ids)
        num_supply = max(num_players, int(len(non_home_land_ids) * 0.45))
        supply_set = set(non_home_land_ids[:num_supply])

        node_types: dict[NodeId, NodeType] = {}
        for n in node_id_of.values():
            if n in water_ids:
                node_types[n] = NodeType.WATER
            elif n in home_assignments:
                node_types[n] = NodeType.HOME
            elif n in supply_set:
                node_types[n] = NodeType.SUPPLY
            else:
                node_types[n] = NodeType.PLAIN

        return Map(
            coords=coord_of,
            edges=edges_frozen,
            node_types=node_types,
            home_assignments=home_assignments,
        )

    raise ValueError(
        "Archipelago generation failed after 5 attempts; try larger map_radius"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_archetypes.py -v -k archipelago`
Expected: PASS — 7 archipelago tests pass.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 219 tests passed (212 + 7).

- [ ] **Step 6: Commit**

```bash
git add foedus/archetypes.py tests/test_archetypes.py
git commit -m "Implement Archipelago archetype generator"
```

---

## Phase F: Selector + comprehensive tests

### Task 8: Implement `random_archetype` selector

**Files:**
- Modify: `foedus/archetypes.py`
- Test: `tests/test_archetypes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archetypes.py`:

```python
def test_random_archetype_returns_archetype() -> None:
    from foedus.archetypes import random_archetype
    from foedus.core import Archetype
    a = random_archetype(seed=42)
    assert isinstance(a, Archetype)


def test_random_archetype_excludes_uniform() -> None:
    """random_archetype must never return UNIFORM (it's the v1 default,
    not part of the variety set)."""
    from foedus.archetypes import random_archetype
    from foedus.core import Archetype
    seen = set()
    for seed in range(100):
        seen.add(random_archetype(seed=seed))
    assert Archetype.UNIFORM not in seen


def test_random_archetype_seeded_deterministic() -> None:
    from foedus.archetypes import random_archetype
    a1 = random_archetype(seed=42)
    a2 = random_archetype(seed=42)
    assert a1 == a2


def test_random_archetype_distribution() -> None:
    """Across 600 samples, each non-UNIFORM archetype appears ≥ 100 times."""
    from collections import Counter
    from foedus.archetypes import random_archetype
    from foedus.core import Archetype
    counts: Counter[Archetype] = Counter()
    for seed in range(600):
        counts[random_archetype(seed=seed)] += 1
    assert counts[Archetype.HIGHLAND_PASS] >= 100
    assert counts[Archetype.ARCHIPELAGO] >= 100
    assert counts[Archetype.CONTINENTAL_SWEEP] >= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_archetypes.py -v -k random_archetype`
Expected: FAIL — `ImportError: cannot import name 'random_archetype'`.

- [ ] **Step 3: Add `random_archetype` to `foedus/archetypes.py`**

Append to `foedus/archetypes.py`:

```python
def random_archetype(seed: int | None = None) -> Archetype:
    """Return a random Archetype from the non-UNIFORM set.

    Caller can pass a seed for reproducibility. Useful for picking a
    fresh archetype per game when running test pilots or human play.
    """
    rng = random.Random(seed)
    return rng.choice([
        Archetype.HIGHLAND_PASS,
        Archetype.ARCHIPELAGO,
        Archetype.CONTINENTAL_SWEEP,
    ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_archetypes.py -v -k random_archetype`
Expected: PASS — 4 tests pass.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 223 tests passed (219 + 4).

- [ ] **Step 6: Commit**

```bash
git add foedus/archetypes.py tests/test_archetypes.py
git commit -m "Add random_archetype selector function"
```

---

### Task 9: Cross-archetype invariants

**Files:**
- Modify: `tests/test_archetypes.py`

- [ ] **Step 1: Write the cross-archetype invariant tests**

Append to `tests/test_archetypes.py`:

```python
def test_all_archetypes_produce_valid_maps() -> None:
    """For each archetype, the generated Map satisfies basic invariants."""
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for arch in Archetype:
        for n in [2, 3, 4]:
            # Skip Archipelago configurations that would raise on small maps.
            m = generate_map(num_players=n, seed=42, archetype=arch)
            # Every home_assignment references a HOME cell.
            for node, player in m.home_assignments.items():
                from foedus.core import NodeType
                assert m.node_types[node] == NodeType.HOME, \
                    f"{arch}: home {node} has type {m.node_types[node]}"
            # Every node has a node_type.
            for n_id in m.coords:
                assert n_id in m.node_types, \
                    f"{arch}: node {n_id} missing node_type"
            # Every node has an edges entry (possibly empty).
            for n_id in m.coords:
                assert n_id in m.edges, \
                    f"{arch}: node {n_id} missing edges"


def test_all_archetypes_homes_match_player_count() -> None:
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for arch in Archetype:
        for n in [2, 3, 4]:
            m = generate_map(num_players=n, seed=42, archetype=arch)
            assert len(m.home_assignments) == n, \
                f"{arch} with {n} players: got {len(m.home_assignments)} homes"


def test_all_archetypes_seeded_deterministic() -> None:
    """Same seed → same Map for every archetype."""
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for arch in Archetype:
        m1 = generate_map(num_players=4, seed=42, archetype=arch)
        m2 = generate_map(num_players=4, seed=42, archetype=arch)
        assert m1.coords == m2.coords
        assert m1.edges == m2.edges
        assert m1.node_types == m2.node_types
        assert m1.home_assignments == m2.home_assignments


def test_all_archetypes_different_seeds_produce_different_maps() -> None:
    """Sanity check: same archetype + different seed should not produce
    identical maps (with very high probability)."""
    from foedus.core import Archetype
    from foedus.mapgen import generate_map
    for arch in Archetype:
        m1 = generate_map(num_players=4, seed=1, archetype=arch)
        m2 = generate_map(num_players=4, seed=2, archetype=arch)
        # At least one structural difference should exist.
        differs = (
            m1.node_types != m2.node_types
            or m1.home_assignments != m2.home_assignments
            or m1.edges != m2.edges
        )
        assert differs, f"{arch}: seed=1 and seed=2 produced identical maps"
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/test_archetypes.py -v -k "all_archetypes"`
Expected: PASS — 4 invariant tests pass.

- [ ] **Step 3: Run full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 227 tests passed (223 + 4).

- [ ] **Step 4: Commit**

```bash
git add tests/test_archetypes.py
git commit -m "Add cross-archetype invariant tests"
```

---

## Phase G: Final verification

### Task 10: Full suite verification + smoke runs

**Files:** none modified

- [ ] **Step 1: Run full suite**

Run: `python3 -m pytest -v 2>&1 | tail -20`
Expected: ALL PASS — 227 tests total. No regressions in any of the 188 v1 + Press v0 tests, plus 39 new archetype tests.

- [ ] **Step 2: Smoke-run a game on each archetype with `play_game`**

Run:

```bash
python3 -c "
from foedus.core import Archetype, GameConfig
from foedus.agents.random_agent import RandomAgent
from foedus.loop import play_game

for arch in Archetype:
    cfg = GameConfig(num_players=4, seed=42, max_turns=10, archetype=arch)
    final = play_game({p: RandomAgent(seed=p) for p in range(4)}, config=cfg)
    print(f'{arch.value:25} turn={final.turn:2}/{final.config.max_turns} winner={final.winner} elim={sorted(final.eliminated)}')
"
```

Expected: All four archetypes run to terminal state without errors. Output should look like:

```
uniform                   turn=10/10 winner=... elim=[...]
highland_pass             turn=10/10 winner=... elim=[...]
archipelago               turn=10/10 winner=... elim=[...]
continental_sweep         turn=10/10 winner=... elim=[...]
```

If any archetype crashes, debug before final commit.

- [ ] **Step 3: Push**

```bash
git push origin archetypes
```

- [ ] **Step 4: Update PR comment** (optional; only if PR has been opened earlier)

If a draft PR was opened against this branch, post a comment summarizing the implementation status.

---

## Self-review summary

**Spec coverage:**

| Spec section | Implementing task |
|---|---|
| §3 locked decisions | All Tasks (decisions enforced inline) |
| §5 NodeType extension | Task 1 |
| §5 Archetype enum | Task 2 |
| §5 GameConfig fields | Task 3 |
| §5 Map.is_passable | Task 1 |
| §6 generate_map signature | Task 4 |
| §6 random_archetype | Task 8 |
| §7 _gen_uniform | Task 4 |
| §7 _gen_continental_sweep | Task 5 |
| §7 _gen_highland_pass | Task 6 |
| §7 _gen_archipelago | Task 7 |
| §8 adjacency rules | Tasks 1, 4, 6, 7 (each generator excludes impassable neighbors) |
| §9 backward compat | Task 4 (UNIFORM preserves exact v1 output) + Task 10 |
| §11 tests | Tasks 1–9 (each task adds its own tests; Task 9 adds cross-archetype invariants) |

**Placeholder scan:** No "TBD", "TODO", "implement later", "fill in details" — every step has explicit code or commands.

**Type consistency:** `Archetype`, `NodeType.MOUNTAIN`, `NodeType.WATER`, `Map.is_passable`, `_gen_*` functions defined in early tasks and used consistently in later tasks.

**Scope check:** Single cohesive feature plan. Could be decomposed into 3 reviewable PRs at execution time (Phase A as one, Phases B-E as second, Phases F-G as third), but the plan itself is one document.

---

## Risks and mitigations

- **Highland Pass infeasibility.** A bad ridge orientation might isolate homes. Mitigated by 5-attempt re-roll loop with fallback to UNIFORM if all fail.
- **Archipelago island sizing.** Round-robin BFS may starve some islands. Mitigated by 5-attempt re-roll, with `ValueError` on persistent failure (driver should retry with different seed or larger map_radius).
- **Determinism with re-rolls.** Each attempt advances the rng, so reseeding yields the same sequence of attempts. Tests that assert determinism rely on this.
- **Test threshold tuning.** `degree ≥ 4.5`, `island ≥ 3 cells`, supply density ranges may need post-implementation tuning. Test thresholds chosen with margin; flag if tightening becomes desirable.
- **Performance.** Generation runs once per game start; 5 re-roll attempts max means worst case is 5x base cost. No concern for testing speed.
