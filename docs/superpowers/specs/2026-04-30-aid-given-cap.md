# Aid-given cap (Patron remediation)

**Status:** design
**Date:** 2026-04-30
**Related:** `docs/superpowers/specs/2026-04-30-alliance-support-intent-redesign.md` (Bundle 4 originally introduced the leverage mechanic this spec constrains)
**Research:** `research_runs/2026-04-30-no-leverage-bonus.md` (counterfactual showing leverage_bonus is the dominant lever); `research_runs/scripts/patron_analysis.py` (per-pairing breakdown)

## Motivation

Patron currently dominates the post-redesign meta with a 173-mean win-rate of 57.8%, +15.9 ahead of pre-redesign baseline. Per-pairing analysis shows Patron specifically crushes the new heuristics (vs Opportunist 232, vs CoalitionBuilder 217) without gaining anything against the existing top cooperators. A counterfactual sweep with `leverage_bonus_max=0` drops Patron 39 points but hands the crown to DishonestCooperator (no countervailing punishment for freeriders).

Diagnosis: the `leverage_bonus` mechanic was designed to discipline Sycophant-style intent-breakers, but the *same* mechanic enables Patron's late-game asymmetric attack. Patron gives aid early to build positive `leverage(patron, target)`, then weaponizes for +2 combat strength on attacks against the same target.

Agent-level defense (the inverse-leverage gate added in v3 of the new heuristics) helped modestly (Patron −5 to −7) but plateaued because Patron's leverage stockpile is permanent — once accumulated in turns 1-N, it remains weaponizable forever regardless of mid-game defenses.

## Design summary

Cap `aid_given[(A, B)]` at a configurable per-pair maximum (default 3). The cap clamps the long-term leverage stockpile without affecting aid's per-turn tactical effects: the +1 strength bonus on the recipient's order, alliance-bonus eligibility, and token consumption all continue to fire normally for spends past the cap.

With cap=3, `leverage(A, B) = aid_given[(A,B)] - aid_given[(B,A)]` is bounded in `[-3, +3]`, so `leverage_bonus = min(2, lev // 2)` produces at most +1 (vs. the previous +2). Patron's late-game weapon halves; honest reciprocity dynamics are unaffected.

This separates aid's two roles cleanly:
- **Tactical** (immediate +1 strength, alliance-bonus eligibility): always works at full strength.
- **Strategic** (leverage stockpile): caps at the configured value.

## Architecture

### Single change point

`foedus/press.py` `finalize_round` — the aid-ledger increment loop (currently around line 425). Replace:

```python
key = (spender, recipient)
new_aid_given[key] = new_aid_given.get(key, 0) + 1
```

with:

```python
key = (spender, recipient)
new_aid_given[key] = min(
    state.config.aid_given_cap,
    new_aid_given.get(key, 0) + 1,
)
```

### New config field

`foedus/core.py` `GameConfig`:

```python
# Per-pair cap on aid_given[(A, B)] entries. Bounds the long-term
# leverage stockpile without capping per-turn aid effects: the +1
# strength bonus on the recipient's order, alliance-bonus eligibility,
# and token consumption all fire regardless of cap. With default cap=3,
# leverage(A,B) is bounded in [-3, +3], producing at most +1 combat
# bonus (vs the +2 max when uncapped).
#
# Set to a large value (e.g., 999) to recover the pre-cap behavior. Set
# to 1 to effectively disable the leverage_bonus mechanic.
aid_given_cap: int = 3
```

### Unchanged surfaces

- `submit_aid_spends` — accepts spends as before. Token balance still gates the spend count; cap does not.
- `_compute_aid_per_unit` (resolve.py) — still returns +1 per landed aid spend regardless of ledger state.
- Alliance-bonus eligibility — still triggered by aid-backed support, regardless of ledger state.
- `leverage()` and `leverage_bonus()` — formulas unchanged; their output naturally bounded by the cap.
- Wire protocol — `aid_given_cap` is a new int field in `GameConfig`. Existing serializers handle it via `**data` unpacking. No version bump needed.

### Sim sweep CLI

`scripts/foedus_sim_sweep.py` gets a new `--aid-given-cap` flag matching the existing `--aid-cap` / `--aid-divisor` pattern, so we can compare values without code changes.

## Edge cases

| ID | Case | Behavior |
|---|---|---|
| C1 | Spend lands when `aid_given[(A,B)]` already at cap | Token consumed; +1 strength applied; alliance bonus eligible; ledger stays at cap. |
| C2 | Both A and B saturate at cap reciprocally | `aid_given[(A,B)] = aid_given[(B,A)] = cap`; `leverage = 0`; stable equilibrium. |
| C3 | Cap = 1 (effectively disabled bonus) | Max leverage = 1; max bonus = 0. Equivalent to `leverage_bonus_max=0` counterfactual. |
| C4 | Cap = 999 (uncapped) | Equivalent to pre-spec behavior; useful for sweep regression checks. |
| C5 | Cap reduced mid-game (config change) | Existing `aid_given` values can already exceed the new cap. The clamp only applies on subsequent increments — existing values stay above cap until reciprocal aid pulls them under via `leverage` arithmetic. (Acceptable: configs aren't mutated mid-game in practice.) |

## Testing

### New tests in `tests/test_aid_given_cap.py`

1. `test_aid_given_clamps_at_cap`: pre-populate `aid_given[(0,1)] = 3` (default cap), run a finalize_round with one landing AidSpend from P0 → P1; assert `aid_given[(0,1)] == 3`.

2. `test_aid_strength_bonus_still_fires_past_cap`: same setup as test 1; assert `_compute_aid_per_unit` returns `{recipient_unit_id: 1}` (the strength bonus still applies).

3. `test_alliance_bonus_still_fires_past_cap`: full round-trip with `aid_given` at cap, an aided cross-player SupportMove leading to a supply capture; assert the alliance bonus delta is applied to scores.

4. `test_token_still_consumed_past_cap`: pre-populate `aid_tokens={0: 1}` and `aid_given[(0,1)] = 3`; submit + finalize one aid spend; assert `aid_tokens[0] == 0` post-resolution.

5. `test_custom_cap_via_config`: GameConfig with `aid_given_cap=5`; pre-populate `aid_given[(0,1)] = 5`; submit landing spend; assert ledger stays at 5.

6. `test_leverage_bonus_naturally_bounded_by_cap`: with default cap=3, build `aid_given[(0,1)]` to cap via repeated turns; assert `state.leverage_bonus(0, 1) <= 1` throughout.

### Updated existing tests

- `tests/test_aid.py` — current tests don't push `aid_given` past 3 in any scenario, so they should pass unchanged. Spot-check after implementation.
- `tests/test_leverage.py` — same. The leverage_bonus formula is unchanged; only its inputs are bounded.

### Empirical validation

Post-implementation sweep comparison, all on identical seed/configuration except `aid_given_cap`:

- **`research_runs/2026-04-30-aid-given-cap-3.json`** (default cap=3)
- **`research_runs/2026-04-30-aid-given-cap-999.json`** (uncapped baseline regression)

Compare per-agent means via the existing `foedus_sim_analyze.py`.

## Acceptance criteria

- All new tests pass; full suite stays green.
- Total unit-test runtime stays under 2s.
- 1k-game sweep with cap=3 produces:
  - **Patron mean drops at least 10 points** from current main baseline (~166).
  - **DishonestCooperator mean does NOT exceed Patron's mean** (i.e., no crown transfer to pure freeriders, as happened with `leverage_bonus_max=0`).
  - Cooperator / TrustfulCooperator stay within ±10 points of their current band (the cap shouldn't punish honest reciprocators).
- 1k-game sweep with cap=999 reproduces current main baseline within sweep noise (regression check).

## Out of scope

- **Decay** of `aid_given` over time (the alternative theory: aid given on turn 1 still weaponizes on turn 25). Could be a future tuning if cap alone proves insufficient.
- **Stance-conditional `leverage_bonus`** (only fires vs currently-NEUTRAL/HOSTILE targets). Strategically expressive but a larger redesign; revisit if cap+gate combo doesn't bring Patron to the cooperative band.
- **Asymmetric cap per role** (e.g., higher cap on aid received from allies vs. enemies). YAGNI until evidence requires it.
- **Recomputing existing tests' fixtures** for higher-cap exploration scenarios. Defer until the cap default is validated in playtest.

## Open questions

None at spec time. The cap value (3) was chosen to constrain max leverage_bonus to +1 (down from +2 when uncapped). Reference table for tuning:

| Cap | Max leverage | Max bonus | Notes |
|---:|---:|---:|---|
| 1 | 1 | 0 | Effectively disables the bonus (= `leverage_bonus_max=0` counterfactual) |
| 2 | 2 | 1 | Same max bonus as cap=3, but tighter ledger ceiling |
| 3 | 3 | 1 | **Default.** Halves Patron's punch; preserves leverage as a discriminator |
| 4 | 4 | 2 | Allows full bonus only at maximum saturation |
| 999 | unbounded | 2 | Pre-spec behavior |

If the empirical sweep shows Patron still dominant, lower to 2 or 1. If DishonestCooperator inherits the crown, raise toward 4. The config knob makes this tuning trivial.
