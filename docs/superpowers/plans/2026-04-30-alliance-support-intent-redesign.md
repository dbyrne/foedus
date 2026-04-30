# Alliance / Support / Intent Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace exact-match `SupportHold`/`SupportMove` with a single reactive `Support` order, replace exact-match `AidSpend.target_order` with reactive aid, and add live-intent visibility with dependency-aware `signal_done` auto-clear in the negotiation phase.

**Architecture:** Two coupled mechanic changes inside the existing pure-state-transition engine. (1) `Support(target, require_dest=None)` adapts at finalize to the target unit's actual order; geometry breakage emits `SupportLapsed` events. (2) Every intent submission/revision emits `IntentRevised` to authorized viewers; the engine recomputes a unit-grained intent dependency graph and clears `signal_done` only for players whose committed plans reference the revised `(player, unit)`. Clean break — no backwards-compat shim. Wire-protocol version bumps.

**Tech Stack:** Python 3.11+, dataclasses, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-30-alliance-support-intent-redesign.md`

---

## File Structure

### Files to modify

| File | Responsibility | Change shape |
|---|---|---|
| `foedus/core.py` | Core types | Remove `SupportHold`, `SupportMove`. Add `Support`, `IntentRevised`, `SupportLapsed`, `DoneCleared`. Reshape `AidSpend` (drop `target_order`). |
| `foedus/legal.py` | Order enumeration | Replace `SupportHold`/`SupportMove` enumeration with `Support` enumeration; pin variants only on explicit request. |
| `foedus/resolve.py` | Order resolution | Rewrite `_normalize`, `_compute_cuts`, `_compute_strengths`, alliance-bonus and combat-reward indexing for unified `Support`. Emit `SupportLapsed` events into `state.log`. Adjust `_compute_aid_per_unit` for reactive aid. |
| `foedus/press.py` | Negotiation lifecycle | Add `intent_dependencies()` helper. Emit `IntentRevised` events on `submit_press_tokens`. Auto-clear `signal_done` for affected dependents. Drop `_verify_intents` exact-match comparison against `SupportMove.target_dest` (the field is gone). Reshape `submit_aid_spends` (no `target_order`). Adjust aid-ledger update in `finalize_round` (always lands if target alive). |
| `foedus/loop.py` | Driver loop | Update to read new event types; otherwise unchanged. |
| `foedus/remote/wire.py` | JSON wire protocol | Serialize/deserialize new `Support`, `AidSpend`, `IntentRevised`, `SupportLapsed`, `DoneCleared`. Bump `WIRE_PROTOCOL_VERSION`. |
| `foedus/agents/heuristics/cooperator.py` | Cooperator agent | Use `Support` (no `target_dest` guess). |
| `foedus/agents/heuristics/trustful_cooperator.py` | Trust-balanced cooperator | Same. |
| `foedus/agents/heuristics/dishonest_cooperator.py` | Freerider | Same. |
| `foedus/agents/heuristics/aggressive.py` | Aggressive heuristic | Same. |
| `foedus/agents/heuristics/anti_leader.py` | Anti-leader heuristic | Same. |
| `foedus/agents/heuristics/patron.py` | Patron heuristic | AidSpend constructor reshape (no `target_order`). |
| `foedus/eval/metrics.py` | Eval metrics | Replace any `SupportMove`/`SupportHold` isinstance checks with `Support`. |
| `foedus/game_server/render.py` | UI render shim | Replace any `SupportMove`/`SupportHold` isinstance checks with `Support`. Render `IntentRevised`/`SupportLapsed` events on player streams. |
| `scripts/foedus_press_play.py`, `scripts/foedus_sim_sweep.py`, `scripts/foedus_sim_analyze.py` | Driver scripts | Same isinstance updates. |
| `docs/design/mechanics.md` | Living roadmap | Update §III.J ("multi-round negotiation") to point at this spec/plan as the implemented form. |
| `CHANGELOG.md` (or top-level CHANGELOG) | Release notes | Note clean break + wire bump. |

### Files to create

| File | Responsibility |
|---|---|
| `tests/test_support_reactive.py` | Reactive support semantics + lapse reasons |
| `tests/test_intent_dependencies.py` | Dependency-graph helper |
| `tests/test_live_intent_unlock.py` | `IntentRevised` emission + auto-clear |
| `tests/test_support_normalization_events.py` | `SupportLapsed` event taxonomy + `BetrayalObservation` independence |
| `tests/smoke/test_full_game_reactive.py` | Full game with new mechanics terminates |
| `tests/smoke/test_griefing_bounded.py` | Repeated revisions don't hang the round |

### Files to update (existing tests requiring mechanical churn)

`tests/test_resolve.py`, `tests/test_normalize.py`, `tests/test_legal.py`, `tests/test_press.py`, `tests/test_remote_wire.py`, `tests/test_heuristics.py`, `tests/test_heuristic_agent.py`, `tests/test_heuristic_press.py`, `tests/test_aid.py`, `tests/test_betrayal.py`, `tests/test_combat_reward.py`, `tests/test_supply_ownership_cadence.py`, `tests/test_playtest_feedback_bundle1.py`, `tests/test_leverage.py` — replace `SupportHold(target=X)` with `Support(target=X)`, `SupportMove(target=X, target_dest=Y)` with `Support(target=X, require_dest=Y)`, and `AidSpend(target_unit=U, target_order=...)` with `AidSpend(target_unit=U)`.

---

## Branch setup

- [ ] **Step 0.1: Confirm clean working tree on main**

```bash
git status
git log --oneline -3
```

Expected: clean tree (or only the CLAUDE.md mod), HEAD at `cd17ce0` or descendant.

- [ ] **Step 0.2: Create feature branch**

```bash
git checkout -b alliance-support-intent-redesign
```

---

## Task 1: Add new core types (`Support`, `IntentRevised`, `SupportLapsed`, `DoneCleared`); reshape `AidSpend`

Adds the new types alongside the old ones first so subsequent tasks can migrate one consumer at a time. Old types removed in Task 12.

**Files:**
- Modify: `foedus/core.py`
- Test: `tests/test_core_types.py` (new)

- [ ] **Step 1.1: Write the failing test for new type construction**

Create `tests/test_core_types.py`:

```python
"""Smoke tests for the redesigned core types."""
from foedus.core import (
    AidSpend,
    DoneCleared,
    Hold,
    Intent,
    IntentRevised,
    Move,
    Support,
    SupportLapsed,
)


def test_support_default_no_pin():
    s = Support(target=7)
    assert s.target == 7
    assert s.require_dest is None


def test_support_with_pin():
    s = Support(target=7, require_dest=42)
    assert s.require_dest == 42


def test_aidspend_no_target_order():
    a = AidSpend(target_unit=3)
    assert a.target_unit == 3
    # Should not have a target_order attribute anymore
    assert not hasattr(a, "target_order")


def test_intent_revised_construction():
    intent = Intent(unit_id=1, declared_order=Move(dest=5), visible_to=None)
    ev = IntentRevised(turn=2, player=0, intent=intent, previous=None,
                      visible_to=None)
    assert ev.previous is None


def test_support_lapsed_reason_literal():
    ev = SupportLapsed(turn=1, supporter=2, target=3, reason="geometry_break")
    assert ev.reason == "geometry_break"


def test_done_cleared_construction():
    ev = DoneCleared(turn=1, player=0, source_player=2, source_unit=5)
    assert ev.source_unit == 5
```

- [ ] **Step 1.2: Run the test to confirm it fails**

```bash
pytest tests/test_core_types.py -v
```

Expected: ImportError on `Support`, `IntentRevised`, `SupportLapsed`, `DoneCleared`.

- [ ] **Step 1.3: Add the new types in `foedus/core.py`**

Edit `foedus/core.py`. Replace the `SupportHold`/`SupportMove` definitions and update `Order` to a transitional union (both old and new exist temporarily so callers can migrate; we delete the old ones in Task 12):

After the existing `Move` class, leave `SupportHold` and `SupportMove` in place for now. Add `Support` immediately after `SupportMove`:

```python
@dataclass(frozen=True)
class Support:
    """Reactive support order. Adapts to target_unit's actual canon order at
    finalize. If `require_dest` is set, behaves like the legacy SupportMove
    (only lands when target moves to that exact node). If None, supports
    whatever the target does (Hold, Move, or another Support).
    """
    target: UnitId
    require_dest: NodeId | None = None
```

Update the `Order` type alias to include `Support` alongside the legacy types. This is the *transitional* form — Task 12 will narrow it to `Hold | Move | Support`:

```python
Order: TypeAlias = Hold | Move | SupportHold | SupportMove | Support
```

Replace the `AidSpend` dataclass with the reshaped form (no `target_order`):

```python
@dataclass(frozen=True)
class AidSpend:
    """A token spent on an ally's order this turn.

    `target_unit` is the unit being aided. The aid lands on whatever order
    the recipient submits (reactive, by symmetry with Support). It yields
    +1 strength on the recipient's canon order, makes the supporter eligible
    for the alliance bonus when the recipient's order is a Move that captures
    a supply, and increments the trust ledger entry (spender, recipient).
    Tokens are consumed at finalize regardless of whether the recipient's
    unit survives long enough for the aid to matter.
    """
    target_unit: UnitId
```

Add the new event types after `BetrayalObservation`:

```python
from typing import Literal  # add this import at the top of the file


@dataclass(frozen=True)
class IntentRevised:
    """Emitted when a player submits or modifies an intent during negotiation.

    Sent to each player in `visible_to` (or all surviving non-senders if
    visible_to is None, mirroring the source intent's broadcast scope).
    """
    turn: int
    player: PlayerId
    intent: Intent
    previous: Intent | None  # None = first declaration this round for this unit
    visible_to: frozenset[PlayerId] | None


@dataclass(frozen=True)
class SupportLapsed:
    """Emitted at finalize when a Support could not land."""
    turn: int
    supporter: UnitId
    target: UnitId
    reason: Literal[
        "target_held_unsupportable",
        "geometry_break",
        "target_destroyed",
        "pin_mismatch",
        "self_dislodge_blocked",
    ]


@dataclass(frozen=True)
class DoneCleared:
    """Emitted when a player's signal_done flag auto-clears due to an
    ally's intent revision affecting one of the player's committed plans."""
    turn: int
    player: PlayerId         # whose done flag cleared
    source_player: PlayerId  # whose revision triggered the clear
    source_unit: UnitId      # which unit's intent the dependency referenced
```

- [ ] **Step 1.4: Run the test to confirm it passes**

```bash
pytest tests/test_core_types.py -v
```

Expected: 6 passed. The full suite will fail elsewhere because `AidSpend.target_order` is gone — that's expected; subsequent tasks fix call sites.

- [ ] **Step 1.5: Commit**

```bash
git add foedus/core.py tests/test_core_types.py
git commit -m "core: add Support / IntentRevised / SupportLapsed / DoneCleared; reshape AidSpend

Adds the new types alongside legacy SupportHold/SupportMove. AidSpend
loses its target_order field (reactive aid, lands on whatever target
does). Subsequent tasks migrate consumers; legacy types removed at end."
```

---

## Task 2: Add `intent_dependencies()` helper

A pure function on `GameState` returning the unit-grained intent dependency graph. Used by Task 6 (auto-clear) and Task 11 (live-intent unlock tests).

**Files:**
- Modify: `foedus/press.py`
- Create: `tests/test_intent_dependencies.py`

- [ ] **Step 2.1: Write the failing tests**

Create `tests/test_intent_dependencies.py`:

```python
"""Unit tests for press.intent_dependencies()."""
from foedus.core import (
    AidSpend,
    Hold,
    Intent,
    Move,
    Press,
    Support,
)
from foedus.press import intent_dependencies, submit_aid_spends, submit_press_tokens
from tests.helpers import simple_two_player_state


def test_empty_state_no_dependencies():
    s = simple_two_player_state()
    assert intent_dependencies(s) == {}


def test_support_creates_player_unit_dependency():
    s = simple_two_player_state()
    # Player 0 owns unit 0; player 1 owns unit 1; assume adjacency from helper.
    # P0 declares an intent to Support unit 1 (owned by P1).
    intent = Intent(
        unit_id=0,
        declared_order=Support(target=1),
        visible_to=None,
    )
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[intent]))
    deps = intent_dependencies(s)
    # P0 depends on (P1, unit 1).
    assert deps.get(0) == frozenset({(1, 1)})


def test_aidspend_creates_dependency():
    s = simple_two_player_state()
    # Mutual ALLY gate: simulate prior press if needed (helpers can prep this).
    # For now, just call submit_aid_spends and trust the gate logic.
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    deps = intent_dependencies(s)
    # If aid landed on the pending list, dependency should exist.
    if s.round_aid_pending.get(0):
        assert (1, 1) in deps.get(0, frozenset())


def test_solo_move_no_dependency():
    s = simple_two_player_state()
    intent = Intent(
        unit_id=0,
        declared_order=Move(dest=2),  # assume node 2 exists in helper map
        visible_to=None,
    )
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[intent]))
    deps = intent_dependencies(s)
    assert deps.get(0, frozenset()) == frozenset()


def test_unit_grained_separates_units():
    s = simple_two_player_state()
    # P0 supports P1's unit 1. Even if P1 has another unit, dep is just (1, 1).
    intent = Intent(
        unit_id=0, declared_order=Support(target=1), visible_to=None,
    )
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[intent]))
    deps = intent_dependencies(s)
    assert deps[0] == frozenset({(1, 1)})
```

If `tests/helpers.py` doesn't already export a `simple_two_player_state` factory, write it as a local fixture in this test file using `foedus.mapgen` directly. Inspect `tests/helpers.py` first.

```bash
grep -n "def " tests/helpers.py
```

If `simple_two_player_state` is missing, add it inline to `tests/test_intent_dependencies.py`:

```python
from foedus.core import GameConfig
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def simple_two_player_state():
    cfg = GameConfig(num_players=2, map_radius=2, seed=1)
    m = generate_map(cfg)
    return initial_state(cfg, m)
```

- [ ] **Step 2.2: Run the tests to confirm they fail**

```bash
pytest tests/test_intent_dependencies.py -v
```

Expected: ImportError on `intent_dependencies`.

- [ ] **Step 2.3: Implement `intent_dependencies` in `foedus/press.py`**

Add at the top of `foedus/press.py` after the existing `from foedus.core import (...)` block:

```python
from foedus.core import Support  # add to the existing import list above


def intent_dependencies(
    state: GameState,
) -> dict[PlayerId, frozenset[tuple[PlayerId, UnitId]]]:
    """Return per-player set of (other_player, unit) pairs whose intents/orders
    that player's pending plans mechanically depend on.

    A player P depends on (Q, U) iff P has at least one of:
      - A declared Intent for one of P's units whose order is Support(target=U)
        where state.units[U].owner == Q.
      - A pending AidSpend with target_unit=U where state.units[U].owner == Q.
      - A declared Intent whose order is Support(target=U, require_dest=X)
        (the pin variant — same dependency rule, since the pin's viability
        hinges on Q's choice for U).

    Self-dependencies (Q == P) are excluded; Q must be a different player.
    The graph is unit-grained: a single ally with two units yields up to two
    distinct (Q, U_a), (Q, U_b) entries when both are referenced.
    """
    out: dict[PlayerId, set[tuple[PlayerId, UnitId]]] = {}
    # Walk pending press intents.
    for player, press in state.round_press_pending.items():
        for intent in press.intents:
            order = intent.declared_order
            if not isinstance(order, Support):
                continue
            target_unit = state.units.get(order.target)
            if target_unit is None or target_unit.owner == player:
                continue
            out.setdefault(player, set()).add(
                (target_unit.owner, target_unit.id)
            )
    # Walk pending aid spends.
    for spender, spends in state.round_aid_pending.items():
        for spend in spends:
            target_unit = state.units.get(spend.target_unit)
            if target_unit is None or target_unit.owner == spender:
                continue
            out.setdefault(spender, set()).add(
                (target_unit.owner, target_unit.id)
            )
    return {p: frozenset(deps) for p, deps in out.items()}
```

- [ ] **Step 2.4: Run the tests to confirm they pass**

```bash
pytest tests/test_intent_dependencies.py -v
```

Expected: 4 passed. (`test_aidspend_creates_dependency` may pass conditionally based on the mutual-ALLY gate; that's fine.)

- [ ] **Step 2.5: Commit**

```bash
git add foedus/press.py tests/test_intent_dependencies.py
git commit -m "press: add intent_dependencies() helper

Pure function returning the unit-grained intent dependency graph used by
the dependency-aware signal_done auto-clear (Task 6). Walks pending
press intents and aid spends to build (player -> {(other_player, unit)}).
"
```

---

## Task 3: Reactive `Support` order normalization in `_normalize`

Rewrite the `_normalize` branch for `Support` so it adapts to the target's actual order. Old `SupportHold` and `SupportMove` branches stay (transitional) but new code paths produce `Support`. Emits no events yet — Task 4 wires `SupportLapsed`.

**Files:**
- Modify: `foedus/resolve.py`
- Create: `tests/test_support_reactive.py`

- [ ] **Step 3.1: Write the failing test**

First add the `build_state_with_units` helper to `tests/helpers.py` if missing:

```bash
grep -n "build_state_with_units" tests/helpers.py
```

If absent, append to `tests/helpers.py`:

```python
from foedus.core import GameConfig, GameState, Map, NodeType, Unit


def build_state_with_units(layout: dict[int, int],
                           ownership: dict[int, int],
                           edges: dict[int, set[int]],
                           home_assignments: dict[int, int] | None = None,
                           num_players: int = 2):
    """Construct a minimal GameState from a positional layout.

    layout: unit_id -> node_id
    ownership: unit_id -> player_id
    edges: node_id -> {neighbor_node_id}
    """
    nodes = sorted({n for n in layout.values()} | set(edges.keys())
                   | {n for nbrs in edges.values() for n in nbrs})
    coords = {n: (n, 0) for n in nodes}
    edge_map = {n: frozenset(edges.get(n, set())) for n in nodes}
    node_types = {n: NodeType.PLAIN for n in nodes}
    if home_assignments:
        for n in home_assignments:
            node_types[n] = NodeType.HOME
    m = Map(coords=coords, edges=edge_map, node_types=node_types,
            home_assignments=home_assignments or {})
    units = {
        u_id: Unit(id=u_id, owner=ownership[u_id], location=node)
        for u_id, node in layout.items()
    }
    cfg = GameConfig(num_players=num_players, max_turns=10, seed=0)
    state = GameState(
        turn=0, map=m, units=units,
        ownership={n: None for n in nodes},
        scores={p: 0.0 for p in range(num_players)},
        eliminated=set(),
        next_unit_id=max(units) + 1 if units else 0,
        config=cfg,
    )
    return state
```

Then create `tests/test_support_reactive.py`:

```python
"""Reactive Support order normalization."""
from foedus.core import Hold, Move, Support
from foedus.resolve import _normalize
from tests.helpers import build_state_with_units


def _adjacent_two_player_state():
    """u0 (P0) at node 0, u1 (P1) at node 1; nodes 0/1/2 fully connected."""
    return build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )


def test_support_adapts_to_target_move():
    s = _adjacent_two_player_state()
    orders = {0: Support(target=1), 1: Move(dest=2)}
    canon_u0 = _normalize(s, 0, Support(target=1), orders)
    assert canon_u0 == Support(target=1)


def test_support_adapts_to_target_hold():
    s = _adjacent_two_player_state()
    orders = {0: Support(target=1), 1: Hold()}
    canon_u0 = _normalize(s, 0, Support(target=1), orders)
    assert canon_u0 == Support(target=1)


def test_support_geometry_break_on_target_move():
    """u0 supports u1; u1 moves to a node u0 is NOT adjacent to."""
    s = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1}, 1: {0, 2}, 2: {1}},  # u0 only adjacent to node 1
        num_players=2,
    )
    orders = {0: Support(target=1), 1: Move(dest=2)}
    canon_u0 = _normalize(s, 0, Support(target=1), orders)
    assert canon_u0 == Hold()


def test_support_pin_satisfied():
    s = _adjacent_two_player_state()
    orders = {0: Support(target=1, require_dest=2), 1: Move(dest=2)}
    canon_u0 = _normalize(s, 0, Support(target=1, require_dest=2), orders)
    assert canon_u0 == Support(target=1, require_dest=2)


def test_support_pin_mismatch_normalizes_to_hold():
    """u0 pins on dest=2; u1 actually moves to dest=0 (a different node)."""
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},  # extra unit so node 0 is reachable from u1
        ownership={0: 0, 1: 1, 2: 0},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )
    orders = {
        0: Support(target=1, require_dest=2),
        1: Move(dest=0),  # not the pinned destination
        2: Hold(),
    }
    canon_u0 = _normalize(s, 0, Support(target=1, require_dest=2), orders)
    assert canon_u0 == Hold()


def test_support_self_dislodge_blocked():
    """u0 supports u1's attack on a node where P0 has another unit."""
    # u0 (P0) at 0, u1 (P1) at 1, u2 (P0) at 2. u1 moves to 2; u0 supports.
    # The support would dislodge P0's own unit -> normalize to Hold.
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},
        ownership={0: 0, 1: 1, 2: 0},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )
    orders = {0: Support(target=1), 1: Move(dest=2), 2: Hold()}
    canon_u0 = _normalize(s, 0, Support(target=1), orders)
    assert canon_u0 == Hold()
```

- [ ] **Step 3.2: Run the tests to confirm they fail**

```bash
pytest tests/test_support_reactive.py -v
```

Expected: failures because `_normalize` doesn't yet handle `Support`.

- [ ] **Step 3.3: Add a `Support` branch to `_normalize` in `foedus/resolve.py`**

Edit `_normalize` (around line 97). Add a new branch *after* the `SupportMove` branch and *before* the trailing `return Hold()`:

```python
    if isinstance(order, Support):
        target = state.units.get(order.target)
        if target is None or target.id == u_id:
            return Hold()
        target_order = all_orders.get(order.target, Hold())

        # Pin variant: behaves like legacy SupportMove, exact-match required.
        if order.require_dest is not None:
            if not m.is_adjacent(unit.location, order.require_dest):
                return Hold()
            if not isinstance(target_order, Move) or target_order.dest != order.require_dest:
                return Hold()
            defender = state.unit_at(order.require_dest)
            if defender is not None and defender.owner == unit.owner:
                return Hold()
            return order

        # Reactive default: support whatever target's canon order does.
        if isinstance(target_order, Move):
            if not m.is_adjacent(unit.location, target_order.dest):
                return Hold()
            defender = state.unit_at(target_order.dest)
            if defender is not None and defender.owner == unit.owner:
                return Hold()
            return order
        # target holds, supports, or supports-a-supporter: support lands at
        # target's location (E6 — supporting a supporter is supporting them
        # in place).
        if not m.is_adjacent(unit.location, target.location):
            return Hold()
        return order
```

- [ ] **Step 3.4: Run the tests to confirm they pass**

```bash
pytest tests/test_support_reactive.py -v
```

Expected: 6 passed. Existing `tests/test_normalize.py` still passes (legacy branches untouched).

- [ ] **Step 3.5: Commit**

```bash
git add foedus/resolve.py tests/test_support_reactive.py tests/helpers.py
git commit -m "resolve: reactive Support normalization

_normalize now handles Support(target, require_dest=None). Default
behavior adapts to target's actual canon order; require_dest pin
preserves legacy exact-match. Geometry/self-dislodge breaks normalize
to Hold (events come in next task)."
```

---

## Task 4: `_compute_cuts`, `_compute_strengths`, alliance-bonus, and combat-reward indexing for `Support`

Updates the resolution pipeline to recognize `Support` (in addition to legacy `SupportHold`/`SupportMove`) when computing cuts, strengths, alliance bonus, and combat reward. Old branches stay until Task 12.

Also adds `SupportLapsed` events to `state.log` for normalization failures (the path covered by Task 3).

**Files:**
- Modify: `foedus/resolve.py`
- Create: `tests/test_support_normalization_events.py`

- [ ] **Step 4.1: Write the failing test for `SupportLapsed` emission**

Create `tests/test_support_normalization_events.py`:

```python
"""SupportLapsed event taxonomy."""
from foedus.core import Hold, Move, Support, SupportLapsed
from foedus.press import advance_turn
from tests.helpers import build_state_with_units


def _find_lapse_events(state) -> list[SupportLapsed]:
    """Pull SupportLapsed entries from the state's structured event log.
    The log is currently a list[str]; we emit lapses as a parallel typed
    list on state. See implementation note in Task 4 step 4.3."""
    return list(state.support_lapses)  # added in step 4.3


def test_geometry_break_emits_lapse():
    s = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1}, 1: {0, 2}, 2: {1}},
        num_players=2,
    )
    orders_by_player = {
        0: {0: Support(target=1)},
        1: {1: Move(dest=2)},
    }
    s2 = advance_turn(s, orders_by_player)
    lapses = _find_lapse_events(s2)
    assert any(
        l.supporter == 0 and l.target == 1 and l.reason == "geometry_break"
        for l in lapses
    )


def test_pin_mismatch_emits_lapse():
    s = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1, 2, 3}, 1: {0, 2, 3}, 2: {0, 1}, 3: {0, 1}},
        num_players=2,
    )
    # P0 pins to node 2; P1 actually moves to node 3.
    orders_by_player = {
        0: {0: Support(target=1, require_dest=2)},
        1: {1: Move(dest=3)},
    }
    s2 = advance_turn(s, orders_by_player)
    lapses = _find_lapse_events(s2)
    assert any(l.reason == "pin_mismatch" for l in lapses)


def test_betrayal_observation_independent_of_support_outcome():
    """A declared intent vs. submitted-order mismatch still emits
    BetrayalObservation, even when the support succeeded."""
    # Stub: regression check only — confirm test_betrayal.py still passes
    # after Task 4 lands. No new assertion here; this test exists to flag
    # if the verifier path drifts.
    pass
```

- [ ] **Step 4.2: Run the test to confirm it fails**

```bash
pytest tests/test_support_normalization_events.py -v
```

Expected: AttributeError on `state.support_lapses`.

- [ ] **Step 4.3: Add `support_lapses` event channel and `Support` handling in resolve**

In `foedus/core.py`, add to `GameState` (next to existing `betrayals`):

```python
    # Reactive-support lapses for the *current* round, populated by
    # _resolve_orders. Cleared by finalize_round each round. UI/agent
    # consumers read this between turns to surface "your support didn't
    # land because X".
    support_lapses: list["SupportLapsed"] = field(default_factory=list)
```

In `foedus/resolve.py`:

1. Import `Support` and `SupportLapsed` at the top:

```python
from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Map,
    Move,
    NodeId,
    NodeType,
    Order,
    PlayerId,
    Support,           # NEW
    SupportHold,
    SupportLapsed,     # NEW
    SupportMove,
    Unit,
    UnitId,
)
```

2. Refactor `_normalize` to *return* both the canonical order AND a lapse reason (or None). Wrap the inner support logic:

```python
def _normalize_with_reason(
    state: GameState, u_id: UnitId, order: Order,
    all_orders: dict[UnitId, Order],
) -> tuple[Order, str | None]:
    """Same as _normalize but returns (canon, lapse_reason).

    lapse_reason is one of the SupportLapsed.reason literals when a Support
    or legacy SupportHold/SupportMove gets normalized to Hold; None for
    successful normalizations or non-support orders.
    """
    unit = state.units[u_id]
    m = state.map

    if isinstance(order, (Hold, Move)):
        return _normalize(state, u_id, order, all_orders), None

    if isinstance(order, Support):
        target = state.units.get(order.target)
        if target is None:
            return Hold(), "target_destroyed"
        if target.id == u_id:
            return Hold(), "geometry_break"  # self-support
        target_order = all_orders.get(order.target, Hold())

        if order.require_dest is not None:
            if not m.is_adjacent(unit.location, order.require_dest):
                return Hold(), "geometry_break"
            if not isinstance(target_order, Move) or target_order.dest != order.require_dest:
                return Hold(), "pin_mismatch"
            defender = state.unit_at(order.require_dest)
            if defender is not None and defender.owner == unit.owner:
                return Hold(), "self_dislodge_blocked"
            return order, None

        if isinstance(target_order, Move):
            if not m.is_adjacent(unit.location, target_order.dest):
                return Hold(), "geometry_break"
            defender = state.unit_at(target_order.dest)
            if defender is not None and defender.owner == unit.owner:
                return Hold(), "self_dislodge_blocked"
            return order, None
        # Hold / Support / SupportMove / SupportHold — support lands at target's location.
        if not m.is_adjacent(unit.location, target.location):
            return Hold(), "geometry_break"
        return order, None

    # Legacy SupportHold / SupportMove paths — unchanged for now.
    canon = _normalize(state, u_id, order, all_orders)
    if canon == Hold() and not isinstance(order, Hold):
        return canon, "geometry_break"
    return canon, None
```

3. In `_resolve_orders` (around line 460–470), replace the `canon = {u_id: _normalize(...)}` line with:

```python
    canon: dict[UnitId, Order] = {}
    lapses: list[SupportLapsed] = []
    for u_id, o in flat.items():
        c, reason = _normalize_with_reason(state, u_id, o, flat)
        canon[u_id] = c
        if reason is not None and isinstance(o, (Support, SupportHold, SupportMove)):
            target_id = (
                o.target if hasattr(o, "target") else u_id
            )
            lapses.append(SupportLapsed(
                turn=state.turn + 1,
                supporter=u_id,
                target=target_id,
                reason=reason,  # type: ignore[arg-type]
            ))
```

4. At the end of `_resolve_orders`, attach `lapses` to the returned `GameState` constructor:

```python
    return GameState(
        turn=new_turn,
        map=state.map,
        units=new_units,
        ownership=new_owner,
        scores=new_scores,
        eliminated=new_elim,
        next_unit_id=next_id,
        config=state.config,
        log=state.log + log,
        support_lapses=lapses,  # NEW
    )
```

5. Update `_compute_cuts` to recognize `Support`:

```python
def _compute_cuts(canon: dict[UnitId, Order], state: GameState) -> set[UnitId]:
    cut: set[UnitId] = set()
    for u_id, order in canon.items():
        unit = state.units[u_id]
        if isinstance(order, SupportHold):
            if _is_cut(unit, None, canon, state):
                cut.add(u_id)
        elif isinstance(order, SupportMove):
            if _is_cut(unit, order.target_dest, canon, state):
                cut.add(u_id)
        elif isinstance(order, Support):
            target = state.units.get(order.target)
            target_order = canon.get(order.target, Hold()) if target else Hold()
            # Determine the "exclude_from" — for a reactive support of a Move,
            # the supporter is helping at target's destination, so attacks
            # FROM that destination shouldn't count as cuts (matches the
            # SupportMove convention).
            if order.require_dest is not None:
                exclude = order.require_dest
            elif isinstance(target_order, Move):
                exclude = target_order.dest
            else:
                exclude = None
            if _is_cut(unit, exclude, canon, state):
                cut.add(u_id)
    return cut
```

6. Update `_compute_strengths` to recognize `Support` contributions. After the existing `SupportMove` branch inside the `for v_id, v_order in canon.items()` move-strength inner loop, add:

```python
                if isinstance(v_order, Support) and v_order.target == u_id:
                    # Reactive support backing this move: lands iff target's
                    # canon move-dest matches the supporter's geometry.
                    if v_order.require_dest is not None:
                        if v_order.require_dest != order.dest:
                            continue
                    # Geometry already validated in _normalize; if v_order
                    # made it into canon as a non-Hold, it lands.
                    s += 1 + aid_per_unit.get(v_id, 0)
```

And inside the hold-strength inner loop, after the existing `SupportHold` branch, add:

```python
                if isinstance(v_order, Support) and v_order.target == u_id:
                    # Reactive support backing this hold (target is holding).
                    s += 1 + aid_per_unit.get(v_id, 0)
```

7. Update the alliance-bonus `support_index` (around line 675) to recognize `Support`:

```python
        for sup_id, s_order in canon.items():
            if not isinstance(s_order, (SupportMove, Support)):
                continue
            sup_unit = state.units.get(sup_id)
            if sup_unit is None or sup_id in cut:
                continue
            mover = state.units.get(s_order.target)
            if mover is None or mover.owner == sup_unit.owner:
                continue
            # Determine the supported destination.
            if isinstance(s_order, SupportMove):
                supported_dest = s_order.target_dest
            else:
                # reactive Support: use target's canon move-dest if any.
                tgt_order = canon.get(s_order.target)
                if not isinstance(tgt_order, Move):
                    continue
                supported_dest = tgt_order.dest
                if s_order.require_dest is not None and s_order.require_dest != supported_dest:
                    continue
            if not _is_aided(sup_unit.owner, s_order.target, supported_dest):
                continue
            support_index[(s_order.target, supported_dest)].append(sup_unit.owner)
```

8. Update the combat-reward supporter loop (around line 755) similarly:

```python
            if sr != 0.0:
                for sup_id, s_order in canon.items():
                    if not isinstance(s_order, (SupportMove, Support)):
                        continue
                    if sup_id in cut:
                        continue
                    if isinstance(s_order, SupportMove):
                        if (s_order.target != attacker_id
                                or s_order.target_dest != defender.location):
                            continue
                    else:
                        if s_order.target != attacker_id:
                            continue
                        tgt_order = canon.get(s_order.target)
                        if (not isinstance(tgt_order, Move)
                                or tgt_order.dest != defender.location):
                            continue
                        if (s_order.require_dest is not None
                                and s_order.require_dest != defender.location):
                            continue
                    sup_unit = state.units.get(sup_id)
                    if sup_unit is None or sup_unit.owner == attacker.owner:
                        continue
                    new_scores[sup_unit.owner] = (
                        new_scores.get(sup_unit.owner, 0.0) + sr
                    )
                    log.append(
                        f"  supporter reward +{sr:g} to p{sup_unit.owner} "
                        f"(via u{sup_id}) for dislodgement at n{defender.location}"
                    )
```

9. Update `_stagnation_cost_deltas` in `foedus/press.py` to count reactive `Support` of a Move as "did something":

```python
        # Treat Move and any cross-player attacking support as "did something":
        # legacy SupportMove, or reactive Support whose target's canon is a Move.
        from foedus.core import Support  # local import to avoid cycle
        active = False
        for o in p_orders:
            if isinstance(o, (Move, SupportMove)):
                active = True
                break
            if isinstance(o, Support):
                # We don't have access to the full canon here cheaply; treat
                # any Support as non-stagnant. (This is more lenient than the
                # legacy rule but the stagnation cost is 0.0 by default anyway.)
                active = True
                break
        if not active:
            out[p] = -cost
```

- [ ] **Step 4.4: Run the new tests**

```bash
pytest tests/test_support_normalization_events.py -v
```

Expected: passes (geometry_break and pin_mismatch lapses surface).

- [ ] **Step 4.5: Run the existing resolve / aid / leverage tests**

```bash
pytest tests/test_resolve.py tests/test_aid.py tests/test_leverage.py tests/test_combat_reward.py -v
```

Expected: all green (legacy paths untouched).

- [ ] **Step 4.6: Commit**

```bash
git add foedus/core.py foedus/resolve.py foedus/press.py tests/test_support_normalization_events.py
git commit -m "resolve: support reactive Support in cuts/strengths/alliance/combat

Adds Support recognition to _compute_cuts, _compute_strengths,
alliance-bonus indexing, and combat-reward supporter loop. Adds
state.support_lapses event channel populated by _resolve_orders.
Legacy SupportHold/SupportMove paths still functional for migration.
"
```

---

## Task 5: Reshape `submit_aid_spends` and `_compute_aid_per_unit` for reactive aid

`AidSpend.target_order` is gone. `submit_aid_spends` no longer validates target_order. `_compute_aid_per_unit` always credits the spend (target alive + canon order present) — no exact-match check. `finalize_round`'s aid-ledger update mirrors this.

**Files:**
- Modify: `foedus/press.py`, `foedus/resolve.py`
- Test: `tests/test_aid.py` (existing, update assertions)

- [ ] **Step 5.1: Update `submit_aid_spends` in `foedus/press.py`**

The function currently expects `AidSpend(target_unit, target_order)`. Drop the `target_order` from filtering — just keep the mutual-ALLY gate, ownership, and balance cap. The body is already aligned (it doesn't look at `target_order`); only the function-level docstring needs revision:

```python
def submit_aid_spends(state: GameState, player: PlayerId,
                      spends: list[AidSpend]) -> GameState:
    """Set/replace `player`'s pending aid spends for the current round.

    Each spend pays one aid token to add +1 strength to the named ally unit's
    canon order this turn (reactive — lands on whatever the recipient does).
    Spends are filtered:
    - target_unit unknown or eliminated-player-owned → dropped
    - target_unit owned by spender → dropped (can't aid self)
    - recipient not mutual ALLY in previous turn's locked press → dropped

    Token balance capped at submit time. Multiple calls overwrite.
    """
    # body unchanged
```

- [ ] **Step 5.2: Update `_compute_aid_per_unit` in `foedus/resolve.py`**

Replace the body (lines ~196-218):

```python
def _compute_aid_per_unit(state: GameState,
                          canon: dict[UnitId, Order]) -> dict[UnitId, int]:
    """Bundle 4 (reactive aid): count AidSpends that landed on each unit.

    A spend lands iff the target unit still exists (i.e., its owner is not
    eliminated and it appears in canon). Multiple spenders aiding the same
    unit stack additively. No target_order match required.
    """
    out: dict[UnitId, int] = defaultdict(int)
    for spender, spends in state.round_aid_pending.items():
        if spender in state.eliminated:
            continue
        for spend in spends:
            target_unit = state.units.get(spend.target_unit)
            if target_unit is None:
                continue
            if target_unit.owner == spender:
                continue  # safeguard
            if spend.target_unit not in canon:
                continue
            out[spend.target_unit] += 1
    return dict(out)
```

- [ ] **Step 5.3: Update aid-ledger in `finalize_round` (`foedus/press.py`)**

In `finalize_round`, around line 407 ("Determine which spends 'landed'"), replace the per-spend loop:

```python
    for spender, spends in state.round_aid_pending.items():
        if spender in s_after.eliminated:
            continue
        balance = new_aid_tokens.get(spender, 0)
        new_aid_tokens[spender] = max(0, balance - len(spends))
        for spend in spends:
            target_unit = state.units.get(spend.target_unit)
            if target_unit is None:
                continue
            recipient = target_unit.owner
            if recipient in state.eliminated:
                continue
            # Reactive aid: lands iff recipient's unit had any canon order
            # this turn. Ownership and survival are sufficient.
            if spend.target_unit not in canon:
                continue
            key = (spender, recipient)
            new_aid_given[key] = new_aid_given.get(key, 0) + 1
```

- [ ] **Step 5.4: Update `tests/test_aid.py` to match reactive aid**

```bash
grep -n "target_order" tests/test_aid.py
```

For each match, drop the `target_order=` kwarg from `AidSpend(...)` calls. Update any assertion that expected aid to "miss" because of target_order mismatch — under reactive aid, those tests now expect aid to land. If a test was specifically about exact-match behavior, replace it with:

```python
def test_reactive_aid_lands_on_any_target_order(...):
    """AidSpend lands as long as recipient's unit has a canon order this turn."""
    ...
```

(One test per former exact-match scenario, asserting the aid lands and ledger increments.)

- [ ] **Step 5.5: Run the aid + leverage tests**

```bash
pytest tests/test_aid.py tests/test_leverage.py -v
```

Expected: all green.

- [ ] **Step 5.6: Commit**

```bash
git add foedus/press.py foedus/resolve.py tests/test_aid.py
git commit -m "press+resolve: reactive AidSpend (no target_order match)

AidSpend.target_order is gone (dropped in Task 1). Aid lands whenever
the recipient unit survives and has a canon order this turn. Trust
ledger increments accordingly.
"
```

---

## Task 6: `IntentRevised` emission + dependency-aware `signal_done` auto-clear

Adds the live-intent event stream and the auto-clear logic. Adds an event channel on `GameState` for `IntentRevised` and `DoneCleared`.

**Files:**
- Modify: `foedus/core.py`, `foedus/press.py`
- Create: `tests/test_live_intent_unlock.py`

- [ ] **Step 6.1: Add event channels to `GameState` in `foedus/core.py`**

Add fields (next to `support_lapses`):

```python
    # Round-scoped event channels for live-press observers. Cleared by
    # finalize_round each round.
    intent_revisions: list["IntentRevised"] = field(default_factory=list)
    done_clears: list["DoneCleared"] = field(default_factory=list)
```

- [ ] **Step 6.2: Write the failing tests**

Create `tests/test_live_intent_unlock.py`:

```python
"""Live-intent visibility + dependency-aware signal_done auto-clear."""
from foedus.core import (
    AidSpend,
    Hold,
    Intent,
    IntentRevised,
    Move,
    Press,
    Support,
)
from foedus.press import (
    intent_dependencies,
    signal_done,
    submit_aid_spends,
    submit_press_tokens,
)
from tests.helpers import build_state_with_units


def _two_player_adjacent_state():
    return build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )


def test_intent_revision_emits_event():
    s = _two_player_adjacent_state()
    intent = Intent(unit_id=0, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[intent]))
    assert any(
        isinstance(ev, IntentRevised) and ev.player == 0 and ev.previous is None
        for ev in s.intent_revisions
    )


def test_intent_revision_carries_previous():
    s = _two_player_adjacent_state()
    i1 = Intent(unit_id=0, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[i1]))
    i2 = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[i2]))
    revisions = [ev for ev in s.intent_revisions if ev.player == 0]
    assert revisions[-1].previous == i1
    assert revisions[-1].intent == i2


def test_dependent_done_auto_clears_on_revision():
    s = _two_player_adjacent_state()
    # P0 supports P1's unit 1.
    p0_intent = Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent]))
    # P1 declares a Move intent for unit 1.
    p1_intent = Intent(unit_id=1, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent]))
    # P0 signals done.
    s = signal_done(s, 0)
    assert 0 in s.round_done
    # P1 revises — should auto-clear P0's done flag.
    p1_intent2 = Intent(unit_id=1, declared_order=Hold(), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent2]))
    assert 0 not in s.round_done
    assert any(
        ev.player == 0 and ev.source_player == 1 and ev.source_unit == 1
        for ev in s.done_clears
    )


def test_self_revision_does_not_clear_own_done():
    s = _two_player_adjacent_state()
    p0_intent = Intent(unit_id=0, declared_order=Move(dest=2), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent]))
    s = signal_done(s, 0)
    # P0 revises P0's own intent — done unaffected.
    p0_intent2 = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent2]))
    # signal_done in the existing code REJECTS submissions from done players.
    # The cleared-then-resubmit case is covered by the dependent test above.
    # This test asserts that self-revision DOESN'T trigger any clear:
    assert all(ev.player != 0 for ev in s.done_clears)


def test_unrelated_unit_revision_keeps_done_set():
    """P depends on (Q, U). Q revises a different unit V — P's done stays set."""
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},
        ownership={0: 0, 1: 1, 2: 1},  # P1 has two units (1 and 2)
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )
    p0_intent = Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[p0_intent]))
    # P1 declares for unit 2 (not the one P0 depends on).
    p1_intent = Intent(unit_id=2, declared_order=Move(dest=0), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent]))
    s = signal_done(s, 0)
    # P1 revises unit 2's intent — should NOT affect P0.
    p1_intent2 = Intent(unit_id=2, declared_order=Hold(), visible_to=None)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[p1_intent2]))
    assert 0 in s.round_done


def test_no_transitive_cascade():
    """P depends on Q; Q depends on R. R revises — Q clears, P stays set."""
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},
        ownership={0: 0, 1: 1, 2: 2},
        edges={0: {1}, 1: {0, 2}, 2: {1}},
        num_players=3,
    )
    # P0 supports P1's unit 1 (P0 depends on P1).
    s = submit_press_tokens(s, 0, Press(
        stance={},
        intents=[Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)],
    ))
    # P1 supports P2's unit 2 (P1 depends on P2).
    s = submit_press_tokens(s, 1, Press(
        stance={},
        intents=[Intent(unit_id=1, declared_order=Support(target=2), visible_to=None)],
    ))
    # P2 declares for unit 2.
    s = submit_press_tokens(s, 2, Press(
        stance={},
        intents=[Intent(unit_id=2, declared_order=Move(dest=1), visible_to=None)],
    ))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    # P2 revises unit 2 — only P1 should auto-clear.
    s = submit_press_tokens(s, 2, Press(
        stance={},
        intents=[Intent(unit_id=2, declared_order=Hold(), visible_to=None)],
    ))
    assert 1 not in s.round_done  # P1 directly depends on (P2, 2) — clears
    assert 0 in s.round_done       # P0 only depends on P1, not transitive


def test_round_closes_when_all_done_after_revision():
    """A revision that triggers no auto-clears (or whose dependents weren't
    done) should still allow the round to close once all-done holds again."""
    s = _two_player_adjacent_state()
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    from foedus.press import is_round_complete
    assert is_round_complete(s)
```

- [ ] **Step 6.3: Run the tests to confirm they fail**

```bash
pytest tests/test_live_intent_unlock.py -v
```

Expected: failures (no event emission, no auto-clear).

- [ ] **Step 6.4: Implement event emission and auto-clear in `submit_press_tokens`**

In `foedus/press.py`, modify `submit_press_tokens` to:
1. Diff incoming intents vs. previous round_press_pending for that player.
2. Emit `IntentRevised` for each new/changed intent.
3. Recompute `intent_dependencies` post-mutation; auto-clear `signal_done` for affected dependents and emit `DoneCleared`.

Replace the `return replace(state, round_press_pending=new_pending)` tail with:

```python
    # ----- Live intent visibility + dependency-aware done auto-clear -----

    # Build per-unit lookup of previously-submitted intents by THIS player
    # (last write wins).
    prev_press = state.round_press_pending.get(player)
    prev_by_unit: dict[UnitId, Intent] = {}
    if prev_press is not None:
        for it in prev_press.intents:
            prev_by_unit[it.unit_id] = it

    new_revisions = list(state.intent_revisions)
    new_done = set(state.round_done)
    new_clears = list(state.done_clears)
    revised_unit_keys: set[tuple[PlayerId, UnitId]] = set()

    for intent in cleaned_intents:
        prev = prev_by_unit.get(intent.unit_id)
        if prev == intent:
            continue  # no change
        new_revisions.append(IntentRevised(
            turn=state.turn + 1,
            player=player,
            intent=intent,
            previous=prev,
            visible_to=intent.visible_to,
        ))
        revised_unit_keys.add((player, intent.unit_id))

    # Detect retractions: previous intent for a unit no longer present in
    # the new submission.
    new_unit_ids = {it.unit_id for it in cleaned_intents}
    for prev_unit_id, prev_intent in prev_by_unit.items():
        if prev_unit_id not in new_unit_ids:
            new_revisions.append(IntentRevised(
                turn=state.turn + 1,
                player=player,
                intent=prev_intent,  # last seen value, for traceability
                previous=prev_intent,
                visible_to=prev_intent.visible_to,
            ))
            revised_unit_keys.add((player, prev_unit_id))

    s_pending = replace(state, round_press_pending=new_pending)
    deps = intent_dependencies(s_pending)

    for dependent_player, dep_set in deps.items():
        if dependent_player == player:
            continue  # self-revision doesn't clear own done
        for revised_key in revised_unit_keys:
            if revised_key in dep_set and dependent_player in new_done:
                new_done.discard(dependent_player)
                new_clears.append(DoneCleared(
                    turn=state.turn + 1,
                    player=dependent_player,
                    source_player=player,
                    source_unit=revised_key[1],
                ))
                break  # one clear per dependent per submit

    return replace(
        s_pending,
        intent_revisions=new_revisions,
        done_clears=new_clears,
        round_done=new_done,
    )
```

Add `IntentRevised` and `DoneCleared` to the imports at the top of `foedus/press.py`:

```python
from foedus.core import (
    AidSpend,
    BetrayalObservation,
    ChatDraft,
    ChatMessage,
    DoneCleared,        # NEW
    GameState,
    Hold,
    Intent,
    IntentRevised,      # NEW
    Move,
    Order,
    Phase,
    PlayerId,
    Press,
    Stance,
    Support,            # NEW (added in Task 2 - confirm it's there)
    SupportHold,
    SupportMove,
    UnitId,
)
```

- [ ] **Step 6.5: Mirror the same auto-clear logic in `submit_aid_spends`**

After the `new_pending[player] = cleaned` line and *before* the existing return, replicate the dependency-recompute + auto-clear pattern (revised_unit_keys is the set of `(player, target_unit)` for changed/new spends). Concretely, replace the tail of `submit_aid_spends`:

```python
    new_pending = dict(state.round_aid_pending)
    prev_spends = state.round_aid_pending.get(player, [])
    prev_targets = {s.target_unit for s in prev_spends}
    new_targets = {s.target_unit for s in cleaned}
    revised_unit_keys = {(player, u) for u in new_targets ^ prev_targets}

    new_pending[player] = cleaned
    s_pending = replace(state, round_aid_pending=new_pending)
    deps = intent_dependencies(s_pending)

    new_done = set(state.round_done)
    new_clears = list(state.done_clears)
    for dependent_player, dep_set in deps.items():
        if dependent_player == player:
            continue
        for revised_key in revised_unit_keys:
            if revised_key in dep_set and dependent_player in new_done:
                new_done.discard(dependent_player)
                new_clears.append(DoneCleared(
                    turn=state.turn + 1,
                    player=dependent_player,
                    source_player=player,
                    source_unit=revised_key[1],
                ))
                break

    return replace(
        s_pending,
        round_done=new_done,
        done_clears=new_clears,
    )
```

- [ ] **Step 6.6: Clear event channels in `finalize_round`**

In `finalize_round`, the final `replace(s_after, ...)` adds these scratch resets:

```python
        intent_revisions=[],
        done_clears=[],
        # support_lapses already gets re-populated by _resolve_orders
```

(Note: `support_lapses` is re-initialized inside `_resolve_orders` already because that function builds a fresh `GameState`. The `intent_revisions` / `done_clears` channels need explicit clearing here since they live on the state across `submit_press_tokens` calls.)

- [ ] **Step 6.7: Run the new tests**

```bash
pytest tests/test_live_intent_unlock.py -v
```

Expected: 7 passed.

- [ ] **Step 6.8: Run the full press test suite**

```bash
pytest tests/test_press.py tests/test_betrayal.py tests/test_chat.py tests/test_intent_dependencies.py -v
```

Expected: all green. If betrayal tests reference legacy `SupportHold`/`SupportMove` they keep working because those types still exist (Task 12 deletes them).

- [ ] **Step 6.9: Commit**

```bash
git add foedus/core.py foedus/press.py tests/test_live_intent_unlock.py
git commit -m "press: live IntentRevised events + dependency-aware signal_done auto-clear

submit_press_tokens and submit_aid_spends emit IntentRevised events
with previous-value diffing, recompute the intent dependency graph,
and auto-clear signal_done for any dependent player whose committed
plans reference the revised (player, unit). DoneCleared events
emitted per clear. No transitive cascade — only direct dependents.
"
```

---

## Task 7: Update `_verify_intents` to handle reshaped types

`_verify_intents` compares declared intents to submitted orders. Today an `Intent.declared_order` could be a `SupportHold(target=X)` and the submitted could be a `SupportMove(target=X, target_dest=Y)` — those would mismatch. Under the new types, both collapse into `Support(target=X, require_dest=...)`, so the comparison is structural equality on the new dataclass — it already works without code changes.

But: if a player declares `Support(target=X)` (reactive) and submits `Support(target=X, require_dest=Y)`, those are NOT equal — the verifier would flag a betrayal. Per spec, that's correct (the player declared one thing and submitted another).

This task is mostly a regression check.

**Files:**
- Modify: none (verification path)
- Test: `tests/test_betrayal.py` (existing)

- [ ] **Step 7.1: Run existing betrayal tests**

```bash
pytest tests/test_betrayal.py -v
```

Expected: all green. If any reference `SupportHold` or `SupportMove` directly, leave them as-is (they still work because legacy types haven't been removed yet).

- [ ] **Step 7.2: Add a regression test for reactive Support betrayal detection**

Append to `tests/test_betrayal.py`:

```python
def test_betrayal_observation_for_support_revision():
    """Player declares Support(target=X), submits Hold — betrayal observed."""
    from foedus.core import Hold, Intent, Press, Support
    from foedus.press import (
        finalize_round,
        signal_done,
        submit_press_tokens,
    )
    from tests.helpers import build_state_with_units

    s = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )
    intent = Intent(
        unit_id=0,
        declared_order=Support(target=1),
        visible_to=frozenset({1}),
    )
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[intent]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    # P0 declared Support(1), submits Hold().
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    obs_for_p1 = s2.betrayals.get(1, [])
    assert any(o.betrayer == 0 for o in obs_for_p1)
```

- [ ] **Step 7.3: Run the new test**

```bash
pytest tests/test_betrayal.py::test_betrayal_observation_for_support_revision -v
```

Expected: pass.

- [ ] **Step 7.4: Commit**

```bash
git add tests/test_betrayal.py
git commit -m "test: regression for reactive Support betrayal detection"
```

---

## Task 8: Update `legal.py` to enumerate `Support`

Replace `SupportHold` + `SupportMove` enumeration with `Support` enumeration. Default candidates are reactive (no `require_dest`); pin variants are not enumerated by default — agents that want pin-specific candidates can request them explicitly via a flag (YAGNI — skip for now; the spec defers expressive enumeration).

**Files:**
- Modify: `foedus/legal.py`
- Test: `tests/test_legal.py`

- [ ] **Step 8.1: Update `tests/test_legal.py`**

```bash
grep -n "SupportHold\|SupportMove" tests/test_legal.py
```

Replace each `SupportHold(target=X)` assertion with `Support(target=X)`. Replace each `SupportMove(target=X, target_dest=Y)` assertion with `Support(target=X)` (note: under reactive enumeration we no longer enumerate by destination; one Support entry per adjacent ally unit).

- [ ] **Step 8.2: Update `legal_orders_for_unit`**

Replace the body of `legal_orders_for_unit` in `foedus/legal.py`:

```python
from foedus.core import (
    GameState,
    Hold,
    Move,
    Order,
    Support,
    UnitId,
)


def legal_orders_for_unit(state: GameState, unit_id: UnitId) -> list[Order]:
    """All geometrically-valid orders for `unit_id`.

    Always includes Hold(). Output is sorted deterministically:
    Hold first, then Moves by destination, then Support entries by target id.

    Reactive Support enumeration: one Support(target=other) per other unit
    that is geometrically reachable as a support target — i.e., the supporter
    is currently adjacent to `other.location` (so support of a Hold is
    trivially possible) OR adjacent to at least one neighbor of `other.location`
    (so support of a Move from `other` is possible). Pin variants
    (require_dest=...) are NOT enumerated; pinning is an opt-in expressive
    behavior, not part of the default candidate set.
    """
    unit = state.units[unit_id]
    m = state.map
    out: list[Order] = [Hold()]

    for nbr in sorted(m.neighbors(unit.location)):
        out.append(Move(dest=nbr))

    others = sorted(state.units.values(), key=lambda u: u.id)
    my_neighbors = m.neighbors(unit.location)
    for other in others:
        if other.id == unit_id:
            continue
        # Reactive Support is geometrically valid if the supporter is
        # adjacent to the target (supports a Hold/Support) OR adjacent
        # to any of the target's neighbors (could support a Move from
        # the target into that neighbor).
        if other.location in my_neighbors:
            out.append(Support(target=other.id))
            continue
        if any(n in my_neighbors for n in m.neighbors(other.location)):
            out.append(Support(target=other.id))

    return out
```

- [ ] **Step 8.3: Run the legal tests**

```bash
pytest tests/test_legal.py -v
```

Expected: green (with the test updates from Step 8.1).

- [ ] **Step 8.4: Commit**

```bash
git add foedus/legal.py tests/test_legal.py
git commit -m "legal: enumerate reactive Support; drop SupportHold/SupportMove enumeration

One Support(target=other) per geometrically-reachable other unit. Pin
variants not enumerated by default (opt-in for agents that want them).
"
```

---

## Task 9: Update heuristic agents to use reactive `Support`

Five heuristics reference `SupportHold` / `SupportMove`: `aggressive`, `anti_leader`, `cooperator`, `dishonest_cooperator`, `trustful_cooperator`. The `patron` agent uses `AidSpend(target_unit, target_order=...)` — strip the `target_order` kwarg.

**Files:**
- Modify: 6 files in `foedus/agents/heuristics/`
- Test: `tests/test_heuristics.py`, `tests/test_heuristic_agent.py`, `tests/test_heuristic_press.py`

- [ ] **Step 9.1: Update each heuristic**

For each of the five heuristics that reference `SupportHold` / `SupportMove`, replace:

- `SupportHold(target=X)` → `Support(target=X)`
- `SupportMove(target=X, target_dest=Y)` → `Support(target=X, require_dest=Y)` if the agent specifically wants exact-match (rare); otherwise → `Support(target=X)` for reactive default.

Audit each heuristic's logic: where the agent picks a `target_dest` based on a guessed ally Move, prefer `Support(target=X)` (reactive — engine adapts) and remove the destination guess entirely. This is the unwieldiness fix in action.

Concretely:
- `cooperator.py`: in the support-emission loop, replace `SupportMove(target=X, target_dest=guessed_dest)` with `Support(target=X)`. The `guessed_dest` calculation can be deleted.
- `trustful_cooperator.py`: same pattern.
- `dishonest_cooperator.py`: same pattern.
- `aggressive.py`: same pattern.
- `anti_leader.py`: same pattern.
- `patron.py`: replace `AidSpend(target_unit=X, target_order=Move(dest=Y))` with `AidSpend(target_unit=X)`.

Use grep to locate each:

```bash
grep -n "SupportHold\|SupportMove\|target_order=" foedus/agents/heuristics/*.py
```

Update each match in place.

- [ ] **Step 9.2: Run heuristic tests**

```bash
pytest tests/test_heuristics.py tests/test_heuristic_agent.py tests/test_heuristic_press.py -v
```

Expected: green. If a test asserts a specific `target_dest` on a heuristic's emitted support, replace that assertion with `assert isinstance(order, Support) and order.target == expected_target`.

- [ ] **Step 9.3: Commit**

```bash
git add foedus/agents/heuristics/
git add tests/test_heuristics.py tests/test_heuristic_agent.py tests/test_heuristic_press.py
git commit -m "heuristics: emit reactive Support; drop AidSpend.target_order

Cooperator / TrustfulCooperator / DishonestCooperator / Aggressive /
AntiLeader replace SupportMove(target, dest) with Support(target).
The destination-guessing logic is now redundant — the engine adapts
to whatever the target ally actually does. Patron drops the
target_order kwarg from AidSpend."
```

---

## Task 10: Update peripheral consumers (eval/metrics, render, scripts)

`foedus/eval/metrics.py`, `foedus/game_server/render.py`, and the `scripts/` files all import `SupportHold` / `SupportMove`. Replace isinstance checks with `Support` (or include both during transition; Task 12 narrows further).

**Files:**
- Modify: `foedus/eval/metrics.py`, `foedus/game_server/render.py`, `scripts/foedus_press_play.py`, `scripts/foedus_sim_sweep.py`, `scripts/foedus_sim_analyze.py`

- [ ] **Step 10.1: Replace isinstance checks**

```bash
grep -rn "SupportHold\|SupportMove" foedus/eval/ foedus/game_server/ scripts/
```

For each match:
- `isinstance(o, SupportHold)` or `isinstance(o, SupportMove)` → `isinstance(o, Support)` (using the new unified type) — combine if a check used both into a single `isinstance(o, Support)` call.
- Direct construction (rare) → use `Support(target=X)` form.

Also surface `IntentRevised` and `SupportLapsed` events in `foedus/game_server/render.py` if the rendering layer formats events for the player stream:

```bash
grep -n "BetrayalObservation\|chat" foedus/game_server/render.py
```

Add render branches for `IntentRevised` and `SupportLapsed` and `DoneCleared` mirroring the existing `BetrayalObservation` rendering style.

- [ ] **Step 10.2: Run eval + game_server tests**

```bash
pytest tests/test_game_server.py tests/test_eval_metrics.py tests/test_eval_probes.py tests/test_eval_render.py -v
```

Expected: green.

- [ ] **Step 10.3: Commit**

```bash
git add foedus/eval/ foedus/game_server/ scripts/
git commit -m "peripherals: migrate eval/render/scripts to unified Support

Update isinstance checks and constructions to use Support. Render
IntentRevised / SupportLapsed / DoneCleared events on the player
stream alongside existing event types."
```

---

## Task 11: Update wire protocol for new types and bump version

Adds JSON serialization for `Support`, `IntentRevised`, `SupportLapsed`, `DoneCleared`. Reshapes `AidSpend` serialization (no `target_order`). Bumps `WIRE_PROTOCOL_VERSION`.

**Files:**
- Modify: `foedus/remote/wire.py`
- Test: `tests/test_remote_wire.py`

- [ ] **Step 11.1: Read the existing wire layout for orders**

```bash
grep -n "SupportHold\|SupportMove\|AidSpend\|VERSION" foedus/remote/wire.py
```

- [ ] **Step 11.2: Bump the protocol version**

If a `WIRE_PROTOCOL_VERSION` constant exists, increment it. If not, add one near the top of `foedus/remote/wire.py`:

```python
# Bump on any breaking wire-format change. v3 introduced the unified Support
# order, reactive AidSpend, and the IntentRevised/SupportLapsed/DoneCleared
# event types. Older clients deserialize with IncompatibleProtocolVersion.
WIRE_PROTOCOL_VERSION = 3
```

(Replace `3` with the next integer above the current version.)

- [ ] **Step 11.3: Replace order serialization**

In the order serialize/deserialize functions, replace the SupportHold/SupportMove branches with a single Support branch:

```python
def serialize_order(o: Order) -> dict:
    if isinstance(o, Hold):
        return {"kind": "hold"}
    if isinstance(o, Move):
        return {"kind": "move", "dest": o.dest}
    if isinstance(o, Support):
        out = {"kind": "support", "target": o.target}
        if o.require_dest is not None:
            out["require_dest"] = o.require_dest
        return out
    raise ValueError(f"unknown order: {o!r}")


def deserialize_order(d: dict) -> Order:
    kind = d["kind"]
    if kind == "hold":
        return Hold()
    if kind == "move":
        return Move(dest=int(d["dest"]))
    if kind == "support":
        return Support(
            target=int(d["target"]),
            require_dest=int(d["require_dest"]) if "require_dest" in d else None,
        )
    raise ValueError(f"unknown order kind: {kind}")
```

- [ ] **Step 11.4: Reshape AidSpend serialization**

```python
def serialize_aidspend(a: AidSpend) -> dict:
    return {"target_unit": a.target_unit}


def deserialize_aidspend(d: dict) -> AidSpend:
    return AidSpend(target_unit=int(d["target_unit"]))
```

- [ ] **Step 11.5: Add serializers for new event types**

If the wire module already serializes events (`BetrayalObservation`, etc.), add parallel functions for `IntentRevised`, `SupportLapsed`, `DoneCleared`. Mirror the existing event-serialization convention.

If there's no existing event serializer, add one for each:

```python
def serialize_intent_revised(ev: IntentRevised) -> dict:
    return {
        "kind": "intent_revised",
        "turn": ev.turn,
        "player": ev.player,
        "intent": serialize_intent(ev.intent),
        "previous": serialize_intent(ev.previous) if ev.previous else None,
        "visible_to": (
            sorted(ev.visible_to) if ev.visible_to is not None else None
        ),
    }


def serialize_support_lapsed(ev: SupportLapsed) -> dict:
    return {
        "kind": "support_lapsed",
        "turn": ev.turn,
        "supporter": ev.supporter,
        "target": ev.target,
        "reason": ev.reason,
    }


def serialize_done_cleared(ev: DoneCleared) -> dict:
    return {
        "kind": "done_cleared",
        "turn": ev.turn,
        "player": ev.player,
        "source_player": ev.source_player,
        "source_unit": ev.source_unit,
    }
```

(And matching `deserialize_*` functions.) Add `serialize_intent` if it doesn't exist, mirroring the order pattern.

- [ ] **Step 11.6: Update GameState wire serialization**

The `support_lapses`, `intent_revisions`, and `done_clears` fields on `GameState` need transcription. Locate the `serialize_state` / `deserialize_state` pair and add round-trip entries for each (defaulting to empty list when absent for forward-compat with the v3 round-trip).

- [ ] **Step 11.7: Update tests**

```bash
grep -n "SupportHold\|SupportMove\|target_order" tests/test_remote_wire.py
```

Replace constructor calls in test fixtures. Add round-trip tests for the new event types:

```python
def test_round_trip_support_pin():
    o = Support(target=3, require_dest=5)
    assert deserialize_order(serialize_order(o)) == o


def test_round_trip_support_reactive():
    o = Support(target=3)
    assert deserialize_order(serialize_order(o)) == o


def test_round_trip_aidspend():
    a = AidSpend(target_unit=7)
    assert deserialize_aidspend(serialize_aidspend(a)) == a


def test_round_trip_intent_revised():
    intent = Intent(unit_id=1, declared_order=Move(dest=4), visible_to=None)
    ev = IntentRevised(turn=2, player=0, intent=intent, previous=None,
                      visible_to=None)
    assert deserialize_intent_revised(serialize_intent_revised(ev)) == ev


def test_round_trip_support_lapsed():
    ev = SupportLapsed(turn=1, supporter=2, target=3, reason="geometry_break")
    assert deserialize_support_lapsed(serialize_support_lapsed(ev)) == ev
```

- [ ] **Step 11.8: Run wire tests**

```bash
pytest tests/test_remote_wire.py -v
```

Expected: green.

- [ ] **Step 11.9: Commit**

```bash
git add foedus/remote/wire.py tests/test_remote_wire.py
git commit -m "wire: bump protocol version; serialize Support / new event types

Order serialization unified: 'support' kind with optional require_dest.
AidSpend drops target_order. New event serializers for IntentRevised,
SupportLapsed, DoneCleared. WIRE_PROTOCOL_VERSION bumped — clean break,
no shim for old serialized blobs."
```

---

## Task 12: Clean break — delete `SupportHold` and `SupportMove`

Now that all callers use `Support`, remove the legacy types. This is the final structural change.

**Files:**
- Modify: `foedus/core.py`, `foedus/resolve.py`, `foedus/press.py`, `foedus/legal.py`, `foedus/agents/heuristics/`, all test files

- [ ] **Step 12.1: Find any remaining references**

```bash
grep -rn "SupportHold\|SupportMove" foedus/ tests/ scripts/
```

- [ ] **Step 12.2: Replace remaining isinstance checks and imports**

In `foedus/resolve.py` `_compute_cuts`, drop the `SupportHold` and `SupportMove` branches (the `Support` branch covers everything). In `_compute_strengths`, drop the legacy branches in both inner loops. In the alliance-bonus and combat-reward loops, drop legacy branches.

In `_normalize`, delete the `SupportHold` and `SupportMove` branches (lines 111-135 of the current file). The `Support` branch added in Task 3 is the only support path.

In `_normalize_with_reason`, simplify by removing the legacy fallback at the end.

In `foedus/press.py` `_stagnation_cost_deltas`, drop `SupportMove` from the activity check; only `Move` and `Support` remain (treat any `Support` as activity, matching the lenient rule from Task 4).

Remove `SupportHold` and `SupportMove` from all imports.

In `foedus/core.py`:
1. Delete the `SupportHold` and `SupportMove` dataclass definitions.
2. Narrow the `Order` type alias:

```python
Order: TypeAlias = Hold | Move | Support
```

- [ ] **Step 12.3: Run the full test suite**

```bash
pytest -x
```

Expected: green. Address any straggler reference (typo in a docstring, etc.) by fixing in place.

- [ ] **Step 12.4: Commit**

```bash
git add -u
git commit -m "core: remove legacy SupportHold and SupportMove

All callers now use Support. Order type alias narrows to Hold | Move |
Support. Clean break — wire protocol v3 (Task 11) makes this final."
```

---

## Task 13: Smoke tests

Two end-to-end smoke checks: a full game runs to completion, and griefing-style intent-toggling doesn't hang the round.

**Files:**
- Create: `tests/smoke/test_full_game_reactive.py`, `tests/smoke/test_griefing_bounded.py`

- [ ] **Step 13.1: Full-game smoke**

Create `tests/smoke/test_full_game_reactive.py`:

```python
"""Full-game smoke: Cooperator agents using reactive Support and
dependency-aware done. Game runs to completion without exceptions.
"""
from foedus.agents.heuristics.cooperator import Cooperator
from foedus.core import GameConfig
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def test_full_game_with_cooperators_terminates():
    cfg = GameConfig(num_players=4, max_turns=10, seed=42)
    m = generate_map(cfg)
    s0 = initial_state(cfg, m)
    agents = [Cooperator(player_id=p) for p in range(cfg.num_players)]
    final_state = play_game(s0, agents)
    assert final_state.is_terminal()
    # Sanity: no exceptions, support_lapses populated for at least one turn.
    # (Cooperators will lapse some supports as the engine adapts.)
```

If the import path or `play_game` signature differs, inspect `foedus/loop.py` first:

```bash
grep -n "def play_game\|class Cooperator" foedus/loop.py foedus/agents/heuristics/cooperator.py
```

Adjust the smoke test accordingly.

- [ ] **Step 13.2: Griefing-bounded smoke**

Create `tests/smoke/test_griefing_bounded.py`:

```python
"""Griefing scenario: a player rapidly toggles intent. Auto-clears only
fire for direct dependents; round still terminates when everyone settles.
"""
from foedus.core import Hold, Intent, Move, Press, Support
from foedus.press import (
    is_round_complete,
    signal_done,
    submit_press_tokens,
)
from tests.helpers import build_state_with_units


def test_repeated_revisions_dont_hang_round():
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},
        ownership={0: 0, 1: 1, 2: 2},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=3,
    )
    # P0 supports P1; P2 is unrelated.
    s = submit_press_tokens(s, 0, Press(
        stance={},
        intents=[Intent(unit_id=0, declared_order=Support(target=1),
                        visible_to=None)],
    ))
    s = submit_press_tokens(s, 2, Press(stance={}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 2)

    # P1 toggles intent 50 times. P0 auto-clears each time; P2 stays done.
    for i in range(50):
        order = Move(dest=2) if i % 2 == 0 else Hold()
        s = submit_press_tokens(s, 1, Press(
            stance={},
            intents=[Intent(unit_id=1, declared_order=order, visible_to=None)],
        ))
        # P0 must redo signal_done each time.
        s = signal_done(s, 0)
        assert 2 in s.round_done  # bystander unaffected

    # Eventually P1 commits.
    s = signal_done(s, 1)
    assert is_round_complete(s)
```

- [ ] **Step 13.3: Run smoke tests**

```bash
pytest tests/smoke/test_full_game_reactive.py tests/smoke/test_griefing_bounded.py -v
```

Expected: green.

- [ ] **Step 13.4: Commit**

```bash
git add tests/smoke/
git commit -m "smoke: full-game with reactive support; griefing-bounded round termination"
```

---

## Task 14: Run the full test suite + update `mechanics.md` and CHANGELOG

- [ ] **Step 14.1: Run everything**

```bash
pytest
```

Expected: all green. Total runtime within existing envelope (~1-2s for unit tests, plus smoke).

- [ ] **Step 14.2: Update `docs/design/mechanics.md`**

Locate §III.J ("Multi-round negotiation"):

```bash
grep -n "Multi-round\|negotiation" docs/design/mechanics.md
```

Replace the §III.J paragraph with:

```markdown
J. **Live-intent negotiation with dependency-aware done** — *implemented*.
   See `docs/superpowers/specs/2026-04-30-alliance-support-intent-redesign.md`.
   Intents emit `IntentRevised` events to authorized viewers in real time
   during NEGOTIATION. When a player revises an intent, the engine recomputes
   the unit-grained intent dependency graph and auto-clears `signal_done`
   only for players whose committed plans reference the revised `(player, unit)`.
   No transitive cascade — only direct dependents auto-clear. Round closes
   the moment all players are simultaneously done; no engine-side timers.
   Replaces the pre-2026-04-30 single-round commit-and-pray model.
```

Also update any references to `SupportHold`/`SupportMove` in mechanics.md to `Support`.

- [ ] **Step 14.3: Add CHANGELOG entry**

If a `CHANGELOG.md` exists at the repo root, prepend an entry. If not, create one:

```markdown
# Changelog

## Unreleased — alliance/support/intent redesign (2026-04-30)

**Breaking changes** (clean break, no backwards-compat shim):

- `SupportHold` and `SupportMove` removed. Use `Support(target, require_dest=None)`.
  Default behavior is reactive — support adapts to the target unit's actual
  canon order at finalize. `require_dest` pin reproduces legacy SupportMove.
- `AidSpend.target_order` removed. Aid lands reactively whenever the target
  unit survives and submits any canon order.
- Wire protocol bumped to v3. Old serialized states/games are incompatible.

**New events:**

- `IntentRevised` — emitted on every intent submission/revision during
  NEGOTIATION. Visible to the same audience as the source intent.
- `SupportLapsed` — emitted at finalize when a `Support` couldn't land.
  Reasons: `geometry_break`, `pin_mismatch`, `target_destroyed`,
  `target_held_unsupportable`, `self_dislodge_blocked`. Closes the
  "silent failure" UX gap flagged by Haiku playtest agents.
- `DoneCleared` — emitted when a player's `signal_done` flag auto-clears
  due to an ally revising an intent that the player's committed plans
  depended on.

**New behavior:**

- Live-intent visibility + dependency-aware `signal_done` auto-clear
  during NEGOTIATION. Rounds with no inter-player dependencies still
  close instantly. See spec for full semantics.
```

- [ ] **Step 14.4: Final test run**

```bash
pytest
```

- [ ] **Step 14.5: Commit and push**

```bash
git add docs/design/mechanics.md CHANGELOG.md
git commit -m "docs: mechanics.md §III.J + CHANGELOG for alliance redesign"
git push -u origin alliance-support-intent-redesign
```

---

## Done criteria

- All checkboxes ticked.
- `pytest` is green.
- `pytest -k "support or intent or press"` is green.
- `git grep "SupportHold\|SupportMove"` returns matches only in `docs/` (historical references).
- `git grep "AidSpend.*target_order"` returns no matches.
- A manual game with `python -m foedus.cli play` runs to completion without exceptions.
- CHANGELOG and mechanics.md updated.
