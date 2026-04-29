# Bundle 4 — Trust, Aid, and Combat Incentives

**Status:** Plan, ready for implementation.
**Date:** 2026-04-29.

## 1. Motivation

Bundle 7's depth-and-balance work (5000-game post-fix sweep, 11 heuristics; see `docs/research/2026-04-29-depth-and-balance.md`) surfaced five empirical findings:

1. **Tier-1 collapse.** GreedyHold, Bandwagon, TitForTat all play GreedyHold orders under the hood; the score-victory regime has *one* optimal strategy.
2. **War aversion.** 91% of games have zero dislodgements.
3. **Cooperation absence.** SupportMove 2.2%, SupportHold 0.6%.
4. **Cheap talk.** Sycophant ≡ OpportunisticBetrayer to within stat noise. Intent-breaks have zero engine consequence.
5. **Détente by lying.** Peaceful collective victories close on tables of all-Sycophant declaring ALLY but secretly racing for supplies.

Bundle 4 introduces six mechanics under one design principle: **make press signals load-bearing for gameplay and make combat directly rewarded**.

## 2. Goals and non-goals

### Goals
- Make declared alliances (mutual ALLY stance) mechanically valuable.
- Create a permanent, accumulating cost to accepting cooperation that isn't reciprocated.
- Reward both attackers and supporters for successful combat.
- Fix the détente-by-lying bug.
- Preserve the engine-as-pure-state-transition discipline.
- Preserve `RandomAgent`-style backward compatibility for the no-press path.

### Non-goals
- Modifying SupportMove/SupportHold semantics. They remain tactical primitives.
- Penalizing Intent-breaks not backed by aid. (Deferred — see §11.)
- Variable supply values, adjacency tax, unit specialization. (Separate bundles.)

## 3. Locked design decisions

| Dimension | Decision |
|---|---|
| Aid resource | Per-player integer counter, generated each turn |
| Generation rate | `floor(supply_count / aid_generation_divisor)` per surviving player at end of turn |
| `aid_generation_divisor` (default) | 3 |
| Token cap | `aid_token_cap` (default 10) |
| Decay | None — tokens persist |
| Spending action | `AidSpend(target_unit, target_order)` — locks +1 strength on the named ally unit's declared order |
| Eligibility | Recipient must be mutual ALLY in the previous turn's locked press |
| Geographic constraint | None — token spends from anywhere |
| Trust ledger | `aid_given[(A, B)]` — cumulative, never decays |
| Leverage formula | `leverage(A→B) = aid_given[(A, B)] - aid_given[(B, A)]` |
| Combat bonus from leverage | `+min(LEV_BONUS_MAX, max(0, leverage // LEV_RATIO))` strength on A's Move targeting a hex B controls or B's unit |
| `leverage_bonus_max` (default) | 2 |
| `leverage_ratio` (default) | 2 |
| Leverage consumption | None — permanent until reciprocated |
| Alliance bonus | Same value (`FOEDUS_ALLIANCE_BONUS`, default 3), but gated on `alliance_requires_aid` |
| `alliance_requires_aid` (default) | True |
| Combat reward — attacker | `+combat_reward` per successful dislodgement (default 1.0) |
| Combat reward — supporter | `+supporter_combat_reward` per dislodgement to each uncut supporter of the dislodging attack (default 1.0) |
| Détente reset | `mutual_ally_streak = 0` on any BetrayalObservation in the current turn |
| `betrayal_resets_detente` (default) | True |

## 4. State and config additions

```python
# foedus/core.py
@dataclass(frozen=True)
class AidSpend:
    target_unit: UnitId
    target_order: Order  # the order being aided; must match recipient's canon to apply

@dataclass
class GameState:
    # ... existing fields ...
    aid_tokens: dict[PlayerId, int] = field(default_factory=dict)
    aid_given: dict[tuple[PlayerId, PlayerId], int] = field(default_factory=dict)
    round_aid_pending: dict[PlayerId, list[AidSpend]] = field(default_factory=dict)

@dataclass
class GameConfig:
    # ... existing ...
    aid_generation_divisor: int = 3
    aid_token_cap: int = 10
    leverage_bonus_max: int = 2
    leverage_ratio: int = 2
    combat_reward: float = 1.0
    supporter_combat_reward: float = 1.0
    alliance_requires_aid: bool = True
    betrayal_resets_detente: bool = True
```

## 5. Engine API additions

```python
# foedus/press.py
def submit_aid_spends(state: GameState, player: PlayerId,
                     spends: list[AidSpend]) -> GameState:
    """Set/replace player's pending aid spends for the current round.

    Validates: phase is NEGOTIATION, player alive, hasn't signaled done,
    each recipient (intent.target_unit's owner) has mutual-ALLY stance with
    `player` in the last archived press_history entry, player has at least
    len(spends) tokens.
    Multiple calls overwrite. Spends targeting eliminated players,
    non-existent units, or units the player owns themselves are dropped.
    """
```

No new public function in `foedus/resolve.py`; all new behavior is internal to `_resolve_orders` and `finalize_round`.

## 6. Resolution pipeline changes

`finalize_round` (in `foedus/press.py`) calls `_resolve_orders` from `resolve.py`. The Bundle 4 hooks are inserted as follows.

### Inside `_resolve_orders`:
1. Existing canon construction.
2. Existing support-cut detection.
3. **(MODIFIED)** Strength computation extended by:
   - For each `AidSpend(unit, target_order)` in `state.round_aid_pending` whose recipient's canon order matches `target_order`: add +1 to that unit's strength.
   - For each Move issued by A whose `dest` is owned by B (or contains a B-unit), add `min(leverage_bonus_max, max(0, leverage(A→B) // leverage_ratio))` to the move's strength.
4. Existing strength comparison + dislodgement decision.
5. Existing ownership transitions, supply scoring (unchanged).
6. **(NEW)** Combat reward: for each dislodgement, +`combat_reward` to the attacker; for each uncut supporter of the dislodging attack, +`supporter_combat_reward` per supporter.
7. **(MODIFIED)** Alliance bonus: if `config.alliance_requires_aid`, bonus only fires for a SupportMove when an `AidSpend(target_unit=mover_id, target_order=mover_canon_order)` was spent by the supporter for the mover's order. Otherwise behaves as before.

### Inside `finalize_round` (post-resolve):
8. **(NEW)** Update `aid_given`: for each AidSpend whose recipient's canon matched, increment `aid_given[(spender, recipient)] += 1`.
9. Existing intent verification → `BetrayalObservation` emission.
10. **(NEW)** If `config.betrayal_resets_detente` and any betrayal was observed this turn, set `new_streak = 0` (overrides the streak increment from §6 step 4 in press.py's existing code).
11. Existing détente check, eliminations.
12. **(NEW)** Token regeneration: for each survivor `p`, `new_aid_tokens[p] = min(cap, prev_aid_tokens[p] - tokens_spent_by_p + floor(supply_count[p] / divisor))`.

## 7. Visibility / fog

- `aid_tokens[p]` visible only to `p`.
- `aid_given[(A, B)]` **public** — the trust ledger is news everyone reads.
- `round_aid_pending` not visible to non-spenders during NEGOTIATION; revealed atomically at finalize.

## 8. Required heuristics for validation

Two new heuristics:

- **TrustfulCooperator** — like Cooperator, plus reciprocates aid roughly 1:1 with mutual-ALLY partners. Targets net leverage ≈ 0 with each partner.
- **Patron** — aggressive giver: spends max tokens per turn on the highest-supply mutual ally. Late-game switches to attacking the most-leveraged former ally.

## 9. Tests

New modules:
- `tests/test_aid.py` — generation, spending, validation, mutual-ALLY gate, cap.
- `tests/test_leverage.py` — ledger correctness, combat-bonus calc, cap behavior.
- `tests/test_combat_reward.py` — attacker reward, supporter reward, cut-supporter exclusion.
- `tests/test_detente_reset.py` — B5: streak resets on observed betrayal.

Updates:
- `tests/test_resolve.py` — alliance bonus now gated on AidSpend (where exercised).
- `tests/test_press.py` — `aid_given` ledger persistence across turns.

## 10. Sweep validation plan

Sweep flag additions to `scripts/foedus_sim_sweep.py`:
- `--aid-cap`, `--aid-divisor`
- `--leverage-bonus-max`, `--leverage-ratio`
- `--combat-reward`, `--supporter-combat-reward`
- `--alliance-requires-aid` (default true; "0" to disable)
- `--betrayal-resets-detente` (default true; "0" to disable)

Regression matrix:

| Test | Setup | Expectation |
|---|---|---|
| DC freerider closed | `--seats DishonestCooperator,Cooperator,Cooperator,Cooperator` | DC's prior +10.7 fixed-seat advantage drops below 0 |
| DC random pool | full pool, n=5000 | DC mean below Cooperator mean |
| Détente by lying fixed | `--seats Sycophant,Sycophant,Sycophant,Sycophant --peace-threshold 0` | Détente rate drops from 100% to ~0% |
| Combat rate up | full pool, n=5000 | ≥1-dislodgement games rise from 9% to 30%+ |
| Coalition pressure | `--seats GreedyHold,AntiLeader,AntiLeader,AntiLeader` | AntiLeader mean rises (now scoring on supporter rewards) |
| Sycophant ≠ OB | full pool, n=5000 | mean diff stat distinguishable at p<0.05 |
| Tier diversity | full pool with TrustfulCooperator + Patron added | top cluster contains 2+ structurally-distinct strategies |

## 11. What's deferred

- **B1** (score deduction per Intent break): defer pending measurement.
- **B4** (withhold support from observed betrayer): **dropped** — superseded by leverage.
- **D2** (stagnation cost): defer pending measurement.
- **C3** (variable supply values, +2 first pass): separate bundle.
- **A3** (adjacency tax): deferred.

## 12. Backward compatibility

- `RandomAgent` and existing heuristics emit no AidSpends; tokens accumulate unused. Their existing `choose_orders` and `choose_press` are unchanged.
- The `advance_turn` no-press shortcut works unchanged — no AidSpend submissions, all Bundle 4 mechanics remain dormant.
- Alliance bonus *behavior changes* under defaults: `alliance_requires_aid=True` means a SupportMove without an AidSpend no longer fires the bonus. Set `alliance_requires_aid=False` to revert.
- Combat reward defaults to 1.0; set to 0.0 for v1 behavior.
- Détente reset defaults to True (it's a bug fix); set `betrayal_resets_detente=False` for v1 behavior.

## 13. Open questions

1. **Token cap of 10** — is this right? Sweep should explore 5/10/20.
2. **Leverage decay** — locked as none in this spec, but a knob like `leverage_decay_rate` could be added if late-game leverage proves too persistent. Defer until measured.
3. **SupportHold reward** — successful defense via SupportHold doesn't yield reward in this design (only dislodgements). Reconsider if defense looks under-incentivized.
4. **Aid spend visibility** — locked-then-public at finalize. Could be exposed during NEGOTIATION; defer.
