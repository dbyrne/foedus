# Alliance / Support / Intent redesign

**Status:** design
**Date:** 2026-04-30
**Supersedes:** parts of `docs/design/mechanics.md` §III.J (multi-round negotiation)

## Motivation

Three pain points surfaced from playtest feedback:

1. **Intents conflict with ally actions, no way to renegotiate.** Players declare intent during negotiation; once orders submit, mismatches become "betrayals" detected after the fact. There is no coordination valve when an ally's situation changes between intent declaration and order lock-in.
2. **Support feels unwieldy.** `SupportMove(target, target_dest)` is exact-match: if the ally moves anywhere other than the declared destination, support silently normalizes to Hold with no agent feedback. Adjacency-locked, single-target, brittle. The Haiku playtest agents flagged "no failure feedback" as the single biggest explain-failure gap.
3. **Low game-to-game variety / shallow strategic thinking.**

This spec addresses (1) and (2) with two coupled mechanic changes. Variety (3) is deferred to follow-up specs (globe topology, richer deal-making) — punting net-new variety mechanics until this redesign ships and we can see what's still missing.

## Design summary

Two coupled changes:

1. **Live intents + dependency-aware done.** Intent submissions/revisions emit events to authorized viewers in real time during the negotiation phase. When a player revises an intent, the engine consults an intent dependency graph and auto-clears `signal_done` only for players whose committed plans mechanically depend on the revised intent. The round closes the moment all players are simultaneously done; no engine-side timers.
2. **Reactive support.** Replace `SupportHold` + `SupportMove(target, target_dest)` with a single `Support(target_unit, require_dest=None)`. By default, support adapts to whatever the target unit actually does at finalize. Optional `require_dest` pin reproduces today's exact-match behavior. `AidSpend` gets the same treatment for symmetry.

Together, these eliminate the "ally rug-pulled my support" failure mode (support adapts; intents are visible live; dependents auto-unlock) while keeping early-game turns fast (no dependencies → no auto-clears → instant round close).

This is a clean break, not backwards-compatible. Old saved games and press_play artifacts will not deserialize. Wire-protocol version bumps.

## Architecture

### Module touch list

| File | Change |
|---|---|
| `foedus/core.py` | Replace `SupportHold` + `SupportMove` with unified `Support`. Add `IntentRevised`, `SupportLapsed`, `DoneCleared` event types. Add intent-dependency-graph helper. |
| `foedus/legal.py` | Update legal-order enumeration to emit unified `Support`. `require_dest` is opt-in pin, not part of default candidate enumeration. |
| `foedus/resolve.py` | Rewrite support normalization (lines ~97–137): resolve target unit's actual order at finalize, validate adjacency against the *result*, lapse with reason on geometry break. Same treatment for `AidSpend` (lines ~196–218). |
| `foedus/press.py` | Live-intent emission on every intent mutation. New helper `intent_dependencies(state)`. `signal_done` auto-clears for affected dependents on revision. |
| `foedus/loop.py` | Negotiation phase: process token submissions in arrival order, emit events, check all-done after each, advance when satisfied. |
| `foedus/agents/heuristics/*.py` | Cooperator / TrustfulCooperator / Patron updated to use unified `Support`. Logic simplifies (no more "guess the exact destination"). |
| `foedus/remote/wire.py` | Serialize new `Support` order, `IntentRevised` event, `SupportLapsed` event, `DoneCleared` event. Bump protocol version. |
| `foedus/game_server/` | Surface live intent events on the player's event stream so UI clients can render them. |

### Data model

```python
# foedus/core.py — new / changed types

@dataclass(frozen=True)
class Support:
    """Reactive support order. Adapts to target_unit's actual order at finalize.

    require_dest: if set, support only lands when target moves to exactly that node
    (today's SupportMove semantics). If None, support adapts to whatever target does.
    """
    target: UnitId
    require_dest: NodeId | None = None

@dataclass(frozen=True)
class IntentRevised:
    """Emitted when a player submits or modifies an intent during negotiation."""
    turn: int
    player: PlayerId
    intent: Intent
    previous: Intent | None  # None = first declaration
    visible_to: frozenset[PlayerId] | None  # mirrors intent.visible_to

@dataclass(frozen=True)
class SupportLapsed:
    """Emitted at finalize when a Support could not land."""
    turn: int
    supporter: UnitId
    target: UnitId
    reason: Literal[
        "target_held_unsupportable",  # target's order is one Support cannot back
        "geometry_break",              # supporter not adjacent to target's actual result
        "target_destroyed",            # target dislodged before its order resolved
        "pin_mismatch",                # require_dest set, target went elsewhere
        "self_dislodge_blocked",       # support would dislodge supporter's own unit
    ]

@dataclass(frozen=True)
class DoneCleared:
    """Emitted when a player's signal_done flag auto-clears due to ally intent revision."""
    turn: int
    player: PlayerId           # player whose done flag cleared
    source_player: PlayerId    # whose revision caused this
    source_unit: UnitId        # which unit's intent was revised
```

`SupportHold` and `SupportMove` are removed from the order union. No serialization shim.

### Intent dependency graph

```python
def intent_dependencies(state: GameState) -> dict[PlayerId, frozenset[tuple[PlayerId, UnitId]]]:
    """For each player P, the set of (other_player, unit) pairs whose intents
    P's own committed orders/intents/aid-spends depend on.

    Unit-grained: a player only auto-unlocks when an ally revises the SPECIFIC unit
    that player has a dependency on, not any intent that ally has declared.
    """
```

Dependency rule: P depends on `(Q, U)` iff P has at least one of:
- `Support(target=U)` where `state.unit_owner(U) == Q`
- `AidSpend(target=U, ...)` where `state.unit_owner(U) == Q`
- `Support(target=U, require_dest=X)` whose viability hinges on Q's unit U reaching X

Recomputed on every press-state mutation. O(orders) and deterministic.

`signal_done` auto-clear: when Q revises an intent for unit U, clear `signal_done` for every player P where `(Q, U) ∈ intent_dependencies(state)[P]`. Other players' done flags untouched. Each clear emits a `DoneCleared` event.

### Negotiation phase event flow

```
PhaseEntered(NEGOTIATION) → all players

loop until all_done:
    Player submits intent/stance via submit_press_tokens:
      - write to round_press_pending
      - emit IntentRevised(turn, player, intent, previous, visible_to)
      - recompute intent_dependencies
      - for each P with dependency on (revising_player, revised_unit):
          if signal_done[P]:
              clear signal_done[P]
              emit DoneCleared(P, source_player=Q, source_unit=U)
      - if all_done now → advance to ORDERS

    Player submits AidSpend → same dependency-recompute + done-clear logic
    Player submits chat → emit ChatPosted (existing behavior)
    Player calls signal_done → set flag; if all_done, advance to ORDERS

ORDERS phase: collect orders, run finalize_round
    - resolve.py reads each Support; resolves target's actual order
    - support that can't land → emit SupportLapsed(reason)
    - aid that can't land → emit AidLapsed (existing pattern, extended)
    - _verify_intents emits BetrayalObservation for declared-vs-submitted mismatches (unchanged)
```

## Edge cases

| ID | Case | Behavior |
|---|---|---|
| E1 | Q revises Q's own unit's intent | No external done flags affected (Q can't be a dependency of Q). Q's own done untouched. |
| E2 | Cascading revisions: P depends on Q, Q depends on R, R revises U | Only **direct** dependents of R auto-clear: Q's done clears (Q has `(R, U)` in deps); P's done does **not** clear (P depends on Q, not R). If Q chooses to revise their own intent in response, that revision then clears P normally. No transitive walk — bounds griefing surface and keeps the rule O(direct deps). |
| E3 | New intent declared (no `previous`) | Doesn't auto-clear anyone. Dependencies are P-on-Q; new declarations from Q only matter for players still revising. |
| E4 | Intent retraction (`withdraw_intent`) | Treated as revision, previous → None. Same auto-clear. |
| E5 | Target unit destroyed mid-resolution | `SupportLapsed(reason="target_destroyed")`. |
| E6 | Target's order is itself a Support | Support lands at target's location (supporting a supporter is supporting them in place). Adjacency: supporter must be adjacent to target. Diplomacy convention. |
| E7 | `require_dest` pin geometry mismatch | `SupportLapsed(reason="pin_mismatch")`. Distinct from `geometry_break` so agents can tell "ally went unexpectedly" from "ally moved out of my reach." |
| E8 | Self-dislodge prevention | `SupportLapsed(reason="self_dislodge_blocked")`. |
| E9 | Done-flag thrash / griefing | Bounded by graph reach (only direct dependents affected) and observable (every revision emits `IntentRevised`). No engine throttle. Drivers may rate-limit if playtest reveals abuse. |
| E10 | Q revises a different unit than the dependency | P's done stays set. Unit-grained, not player-grained. |

## Testing strategy

### New unit tests

**`tests/test_support_reactive.py`**
- Support adapts when target moves: `Support(U)` + `U: Move(X)` → +1 strength to U's move to X.
- Support adapts when target holds: `Support(U)` + `U: Hold` → +1 strength to U's hold.
- Support adapts when target supports (E6): `Support(U)` + `U: Support(V)` → +1 strength to U at U's location.
- Geometry break: target moves out of supporter's adjacency → `SupportLapsed(reason="geometry_break")`.
- Pin satisfied: `Support(U, require_dest=X)` + `U: Move(X)` → lands.
- Pin mismatch: `Support(U, require_dest=X)` + `U: Move(Y)` → `SupportLapsed(reason="pin_mismatch")`.
- Self-dislodge blocked: `SupportLapsed(reason="self_dislodge_blocked")`.
- Target destroyed: `SupportLapsed(reason="target_destroyed")`.

**`tests/test_intent_dependencies.py`**
- Empty state: no dependencies.
- P with `Support(target=U)`, `unit_owner(U) == Q` → P depends on `(Q, U)`.
- P with `AidSpend(target=U)`, `unit_owner(U) == Q` → P depends on `(Q, U)`.
- Solo expansion order: no dependencies.
- Mixed: P has support on Q's unit and aid on R's unit → P depends on both, unit-grained.

**`tests/test_live_intent_unlock.py`**
- P depends on `(Q, U)`. P signals done. Q revises U's intent → P's done auto-clears, `DoneCleared` emitted.
- P depends on `(Q, U)`. P signals done. Q revises a different unit V → P's done stays set (E10).
- Q revises own unit's intent → Q's own done unaffected (E1).
- Cascading: P depends on Q, Q depends on R, R revises → Q's done clears, P's done stays set (E2).
- Withdraw: same auto-clear semantics (E4).
- New intent declaration (no `previous`): no auto-clear (E3).
- Round closes the moment all-done holds true after a revision settles.

**`tests/test_support_normalization_events.py`**
- Each `SupportLapsed` reason variant is emitted with correct supporter/target/turn fields.
- `BetrayalObservation` still fires on intent-vs-order mismatch (independent of support outcome).

### Updated existing tests

- `tests/test_resolve.py`: replace `SupportHold`/`SupportMove` with `Support`. Head-to-head bounce assertions updated for reactive resolver.
- `tests/test_press.py`: extend to cover `IntentRevised` emission and `signal_done` auto-clear.
- `tests/test_legal.py`: legal enumeration emits `Support`; `require_dest` pin variants only when explicitly relevant.
- `tests/test_wire.py`: round-trip new `Support`, `IntentRevised`, `SupportLapsed`, `DoneCleared`.
- `tests/test_agents/`: heuristic support-emission paths simplified; assertions updated.

### Smoke tests

- `tests/smoke/test_full_game_reactive.py`: full game with Cooperator agents using new mechanics; assert termination, no hung negotiation, no exceptions.
- `tests/smoke/test_griefing_bounded.py`: one player rapidly toggles intent; assert auto-clears only fire for actual dependents and round still terminates.

### Out of scope for tests

Agent-quality regression analysis is a separate playtest pass after the redesign lands, using the existing Bundle 4 evaluation harness. Not a gate on this PR.

## Rollout

1. **Single PR.** The two mechanics are tightly coupled; splitting them creates an awkward intermediate where reactive support exists but heuristics lack the live-intent visibility to use it well.
2. **Wire-protocol version bump.** Old saved games / press_play artifacts incompatible. Documented in CHANGELOG.
3. **`docs/design/mechanics.md` update**: §III.J "multi-round negotiation" line updated to point at this spec; cross-link added.
4. **Heuristics updated in same PR** — must terminate games and not crash. Quality regression analysis is a follow-up eval pass.
5. **Game server / Godot client**: `IntentRevised` and `DoneCleared` surfaced on player event streams. UI rendering of live intents is a separate task in `foedus-godot` — flagged here, scheduled there.

## Acceptance criteria

- All new + updated tests pass.
- Total unit-test runtime stays under 2s; smoke tests under existing budget.
- A manual press_play orchestrator run completes a full game with new mechanics.
- `pytest -k "support or intent or press"` is green.
- CHANGELOG and `docs/design/mechanics.md` updated.
- No silent failures in support resolution — every lapse path emits a typed `SupportLapsed` event.

## Out of scope (named follow-ups)

- **Globe topology** — replace flat hex with sphere so games stop converging on a center. Separate `foedus/mapgen.py` spec. No engine coupling with this work.
- **Richer deal-making / press surface** — conditional commitments, future-turn promises, info trades. Future spec; want to see what players miss after this lands.
- **Agent roster expansion** — explicitly deferred. Existing heuristics are updated mechanically here but no new archetypes added.
- **Engine-side negotiation timers** — preserves the pure-state-transition invariant. Drivers may impose wallclock timeouts; engine does not.

## Open questions

None at spec time. Two items flagged during design but resolved:
- E2 cascading semantics: ship as-is (no auto-cascade), revisit if playtest reveals friction.
- E6 supporting-a-supporter: Diplomacy convention adopted (lands at supporter's location).
