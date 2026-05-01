# Aid-Given Cap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cap `aid_given[(A,B)]` at a configurable per-pair maximum (default 3) to bound the long-term leverage stockpile that Patron weaponizes for late-game combat-bonus attacks.

**Architecture:** Single change point in `foedus/press.py` `finalize_round`'s aid-ledger increment loop, plus a new `GameConfig.aid_given_cap` field, plus a `--aid-given-cap` CLI flag on the sim sweep. Per-turn aid effects (+1 strength, alliance-bonus eligibility, token consumption) are unchanged. Only the long-term ledger increment is clamped.

**Tech Stack:** Python 3.11+, dataclasses, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-30-aid-given-cap.md`

---

## File Structure

### Files to modify

| File | Change |
|---|---|
| `foedus/core.py` | Add `aid_given_cap: int = 3` to `GameConfig`. |
| `foedus/press.py` | One-line clamp in `finalize_round` aid-ledger update loop (currently line 578). |
| `scripts/foedus_sim_sweep.py` | Add `--aid-given-cap` CLI flag mirroring the existing `--aid-cap` / `--aid-divisor` pattern. |
| `CHANGELOG.md` | Note the new config knob. |

### Files to create

| File | Responsibility |
|---|---|
| `tests/test_aid_given_cap.py` | 6 tests covering clamp behavior + unchanged tactical effects + leverage bound |
| `research_runs/2026-04-30-aid-given-cap-3.json` | Sweep with default cap=3 |
| `research_runs/2026-04-30-aid-given-cap-3.md` | Analysis of the cap=3 sweep |
| `research_runs/2026-04-30-aid-given-cap-999.json` | Regression check sweep with effectively-uncapped value |
| `research_runs/2026-04-30-aid-given-cap-999.md` | Analysis of the regression sweep |

---

## Branch setup

- [ ] **Step 0.1: Confirm clean working tree**

```bash
git status
git log --oneline -3
```

Expected: clean tree (or only the CLAUDE.md modification, which is unrelated). HEAD at `6ca3d3c` (the spec commit).

- [ ] **Step 0.2: Create feature branch**

```bash
git checkout -b aid-given-cap
```

---

## Task 1: Add `aid_given_cap` field to `GameConfig`

**Files:**
- Modify: `foedus/core.py` (around lines 274-277 where other Bundle 4 aid fields live)
- Test: `tests/test_aid_given_cap.py` (new)

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_aid_given_cap.py`:

```python
"""Tests for the aid_given cap (Patron remediation)."""
from dataclasses import replace

import pytest

from foedus.core import AidSpend, GameConfig


def test_default_cap_is_3():
    cfg = GameConfig()
    assert cfg.aid_given_cap == 3


def test_cap_is_configurable():
    cfg = GameConfig(aid_given_cap=5)
    assert cfg.aid_given_cap == 5
```

- [ ] **Step 1.2: Run the test to confirm it fails**

```bash
pytest tests/test_aid_given_cap.py -v
```

Expected: AttributeError on `aid_given_cap` (field doesn't exist yet).

- [ ] **Step 1.3: Add the field to `GameConfig`**

In `foedus/core.py`, locate the Bundle 4 aid section (around line 274-278 with `aid_generation_divisor` and `aid_token_cap`). After `aid_token_cap`, add:

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

- [ ] **Step 1.4: Run the test to confirm it passes**

```bash
pytest tests/test_aid_given_cap.py -v
```

Expected: 2 passed.

Also confirm the broader suite still passes (the new field is additive):

```bash
pytest -x
```

Expected: all green.

- [ ] **Step 1.5: Commit**

```bash
git add foedus/core.py tests/test_aid_given_cap.py
git commit -m "core: add GameConfig.aid_given_cap field (default 3)

New per-pair cap on aid_given ledger entries. Bounds the long-term
leverage stockpile without affecting per-turn aid effects. Default 3
constrains leverage(A,B) to [-3, +3], producing at most +1 combat bonus
(vs +2 when uncapped). The clamp itself is applied in Task 2."
```

---

## Task 2: Apply clamp in `finalize_round`'s aid-ledger update + behavior tests

**Files:**
- Modify: `foedus/press.py:578` (the `new_aid_given[key] = ... + 1` line)
- Test: extend `tests/test_aid_given_cap.py`

- [ ] **Step 2.1: Write the failing tests**

Append to `tests/test_aid_given_cap.py`:

```python
from foedus.core import (
    AidSpend,
    GameState,
    Hold,
    Map,
    Move,
    NodeType,
    Press,
    Stance,
    Unit,
)
from foedus.press import (
    finalize_round,
    signal_chat_done,
    signal_done,
    submit_aid_spends,
    submit_press_tokens,
)


def _two_player_state_with_press_history(aid_given_init=None,
                                          aid_tokens_init=None,
                                          cap=3):
    """Build a 2-player state suitable for aid-cap testing.

    Layout: P0 unit at node 0, P1 unit at node 1; nodes 0/1/2 fully connected.
    Sets up press_history with mutual ALLY so submit_aid_spends accepts.
    """
    nodes = [0, 1, 2]
    coords = {n: (n, 0) for n in nodes}
    edges = {0: frozenset({1, 2}), 1: frozenset({0, 2}), 2: frozenset({0, 1})}
    node_types = {0: NodeType.HOME, 1: NodeType.HOME, 2: NodeType.SUPPLY}
    home_assignments = {0: 0, 1: 1}
    m = Map(coords=coords, edges=edges, node_types=node_types,
            home_assignments=home_assignments)
    units = {
        0: Unit(id=0, owner=0, location=0),
        1: Unit(id=1, owner=1, location=1),
    }
    cfg = GameConfig(num_players=2, max_turns=10, seed=0,
                     aid_given_cap=cap)
    # Synthetic prior turn with mutual ALLY so submit_aid_spends accepts
    # spends on turn 1 (the gate checks press_history[-1]).
    prior_press = {
        0: Press(stance={1: Stance.ALLY}, intents=[]),
        1: Press(stance={0: Stance.ALLY}, intents=[]),
    }
    state = GameState(
        turn=0, map=m, units=units,
        ownership={0: 0, 1: 1, 2: None},
        scores={0: 0.0, 1: 0.0},
        eliminated=set(),
        next_unit_id=2,
        config=cfg,
        press_history=[prior_press],
        aid_tokens=aid_tokens_init or {0: 5, 1: 0},
        aid_given=aid_given_init or {},
    )
    return state


def test_aid_given_clamps_at_cap():
    """Pre-populate aid_given[(0,1)]=3 (cap); land one more aid; ledger stays at 3."""
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 3},
        aid_tokens_init={0: 1, 1: 0},
        cap=3,
    )
    # P0 spends one aid token on P1's unit 1.
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    # Both players Hold; P1's unit 1 still has a canon order so aid lands.
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    assert s2.aid_given[(0, 1)] == 3, "ledger should clamp at cap"


def test_token_still_consumed_past_cap():
    """At cap, the spend still consumes the token."""
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 3},
        aid_tokens_init={0: 1, 1: 0},
        cap=3,
    )
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    # P0 had 1 token; spent 1; should be 0 (modulo regeneration). Even with
    # regeneration from 1 controlled supply (n=1 home // divisor=3 = 0),
    # final balance = 0.
    assert s2.aid_tokens.get(0, 0) == 0, "token still consumed at cap"


def test_aid_strength_bonus_still_fires_past_cap():
    """At cap, the +1 strength bonus still applies to the recipient's order."""
    from foedus.resolve import _compute_aid_per_unit
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 3},
        aid_tokens_init={0: 1, 1: 0},
        cap=3,
    )
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    # Synthesize a canon dict where unit 1 has a Hold; compute aid_per_unit.
    canon = {0: Hold(), 1: Hold()}
    aid_per_unit = _compute_aid_per_unit(s, canon)
    assert aid_per_unit.get(1) == 1, "strength bonus fires regardless of cap"


def test_custom_cap_via_config():
    """A non-default cap value is respected by the clamp."""
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 5},
        aid_tokens_init={0: 1, 1: 0},
        cap=5,
    )
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    assert s2.aid_given[(0, 1)] == 5, "cap=5 should clamp at 5"


def test_leverage_bonus_naturally_bounded_by_cap():
    """With cap=3, leverage_bonus(A,B) cannot exceed 1."""
    s = _two_player_state_with_press_history(
        aid_given_init={(0, 1): 3, (1, 0): 0},
        cap=3,
    )
    # leverage(0, 1) = 3 - 0 = 3; bonus = min(2, 3//2) = 1.
    assert s.leverage(0, 1) == 3
    assert s.leverage_bonus(0, 1) == 1
    # Even after another spend lands at cap, leverage doesn't grow beyond 3.
    s = replace(s, aid_given={(0, 1): 3, (1, 0): 0}, aid_tokens={0: 1, 1: 0})
    s = submit_aid_spends(s, 0, [AidSpend(target_unit=1)])
    s = submit_press_tokens(s, 0, Press(stance={}, intents=[]))
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s2 = finalize_round(s, orders)
    assert s2.leverage_bonus(0, 1) == 1, "bonus stays at +1 with cap=3"
```

- [ ] **Step 2.2: Run the tests to confirm they fail**

```bash
pytest tests/test_aid_given_cap.py -v
```

Expected: `test_aid_given_clamps_at_cap` and `test_custom_cap_via_config` fail (ledger increments past cap because the clamp isn't applied yet). The other tests likely pass already (they don't depend on the clamp).

- [ ] **Step 2.3: Apply the clamp in `finalize_round`**

Edit `foedus/press.py` line 578 (inside the aid-ledger update loop). Replace:

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

(Use `grep -n "new_aid_given\[key\]" foedus/press.py` to confirm the line if it has shifted.)

- [ ] **Step 2.4: Run the tests to confirm they pass**

```bash
pytest tests/test_aid_given_cap.py -v
```

Expected: 7 passed (2 from Task 1 + 5 from Task 2).

Run the full suite to confirm no regressions:

```bash
pytest -x
```

Expected: all green.

- [ ] **Step 2.5: Commit**

```bash
git add foedus/press.py tests/test_aid_given_cap.py
git commit -m "press: clamp aid_given ledger at config.aid_given_cap

One-line clamp in finalize_round's aid-ledger update loop. Per-turn aid
effects (+1 strength via _compute_aid_per_unit, alliance-bonus
eligibility, token consumption) all unchanged — only the long-term
ledger increment is bounded.

5 behavior tests added: clamp fires at cap, token still consumed,
strength bonus still applies, custom cap respected, leverage_bonus
naturally bounded."
```

---

## Task 3: Add `--aid-given-cap` CLI flag to the sim sweep

**Files:**
- Modify: `scripts/foedus_sim_sweep.py` (around lines 257-262 where other Bundle 4 flags live; lines 341-346 where overrides are assembled)

- [ ] **Step 3.1: Add the argparse flag**

In `scripts/foedus_sim_sweep.py`, locate the Bundle 4 section (line 257 starts "# --- Bundle 4: trust, aid, and combat incentives ---"). After the `--aid-divisor` argument (around line 262), add:

```python
    parser.add_argument("--aid-given-cap", type=int, default=None,
                        help="Bundle 4: per-pair cap on aid_given ledger "
                             "entries (default 3). Bounds the long-term "
                             "leverage stockpile without affecting per-turn "
                             "aid effects. Pass 999 to effectively disable.")
```

- [ ] **Step 3.2: Pipe the flag into `bundle4_overrides`**

In the same file, locate the `bundle4_overrides` assembly (around line 341-355). After the `--aid-divisor` mapping, add:

```python
    if args.aid_given_cap is not None:
        bundle4_overrides["aid_given_cap"] = args.aid_given_cap
```

- [ ] **Step 3.3: Verify the flag works**

Run a tiny sweep to confirm:

```bash
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py --num-games 5 --aid-given-cap 999 --workers 1 --out /tmp/sanity-check.json
```

Expected: writes 5 games, no errors. Cleanup: `rm /tmp/sanity-check.json`.

- [ ] **Step 3.4: Commit**

```bash
git add scripts/foedus_sim_sweep.py
git commit -m "sim_sweep: --aid-given-cap CLI flag

Mirrors the existing --aid-cap / --aid-divisor pattern. Used in Task 4
to compare default cap=3 vs effectively-uncapped (999) sweeps."
```

---

## Task 4: Empirical sweep validation

**Files:**
- Create: `research_runs/2026-04-30-aid-given-cap-3.json` + `.md`
- Create: `research_runs/2026-04-30-aid-given-cap-999.json` + `.md`

- [ ] **Step 4.1: Run the default-cap sweep**

```bash
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
  --num-games 1000 --seed-offset 1000 --max-turns 25 --num-players 4 \
  --workers 4 \
  --out research_runs/2026-04-30-aid-given-cap-3.json
```

Expected: ~5-7s runtime, "Wrote 1000 games" message.

- [ ] **Step 4.2: Generate the cap-3 analysis**

```bash
python3 scripts/foedus_sim_analyze.py \
  research_runs/2026-04-30-aid-given-cap-3.json \
  > research_runs/2026-04-30-aid-given-cap-3.md
```

Inspect the leaderboard:

```bash
head -27 research_runs/2026-04-30-aid-given-cap-3.md
```

Note the values for **Patron**, **DishonestCooperator**, **Cooperator**, and **TrustfulCooperator**. Expected acceptance:
- Patron mean drops at least 10 points from current main baseline (~166)
- DishonestCooperator mean does NOT exceed Patron's mean
- Cooperator/TrustfulCooperator within ±10 of their post-v3 band

If acceptance fails, the cap value or formula needs revisiting — but proceed to step 4.3 first to capture the regression baseline before tuning.

- [ ] **Step 4.3: Run the regression-baseline sweep (effectively uncapped)**

```bash
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
  --num-games 1000 --seed-offset 1000 --max-turns 25 --num-players 4 \
  --workers 4 \
  --aid-given-cap 999 \
  --out research_runs/2026-04-30-aid-given-cap-999.json
```

```bash
python3 scripts/foedus_sim_analyze.py \
  research_runs/2026-04-30-aid-given-cap-999.json \
  > research_runs/2026-04-30-aid-given-cap-999.md
```

This sweep should reproduce the current main baseline (Patron ~166, etc.) within sweep noise — confirming the cap (when set very high) is mathematically equivalent to the prior behavior.

- [ ] **Step 4.4: Compare and confirm acceptance criteria**

Use `diff` or visual comparison of the two `.md` files. Specifically check:

| Acceptance | Pass condition |
|---|---|
| Patron drops ≥10 from cap-999 baseline | Patron(cap=3) − Patron(cap=999) ≤ −10 |
| DishonestCooperator does NOT inherit crown | Patron(cap=3) > DishonestCooperator(cap=3) |
| Cooperator/TrustfulCooperator within ±10 | |Cooperator(cap=3) − Cooperator(cap=999)| ≤ 10 (same for TC) |

If all three pass, proceed to commit. If Patron doesn't drop enough, the spec's "Open questions" tuning table suggests trying cap=2 (re-run step 4.1 with `--aid-given-cap 2`). If DishonestCooperator inherits the crown, try cap=4 instead.

- [ ] **Step 4.5: Commit research artifacts**

```bash
git add research_runs/2026-04-30-aid-given-cap-3.json \
        research_runs/2026-04-30-aid-given-cap-3.md \
        research_runs/2026-04-30-aid-given-cap-999.json \
        research_runs/2026-04-30-aid-given-cap-999.md
git commit -m "research: aid-given-cap empirical validation

cap=3 (new default) vs cap=999 (regression baseline) on identical seeds.

Compare the two .md files for the agent leaderboard shift. Acceptance
criteria from the spec:
- Patron drops ≥10 points from cap-999 baseline
- DishonestCooperator does NOT exceed Patron's mean
- Cooperator/TrustfulCooperator within ±10 of cap-999 values"
```

---

## Task 5: Update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md` (root of repo)

- [ ] **Step 5.1: Add CHANGELOG entry**

Find the existing CHANGELOG (added in the alliance-support-intent redesign). Open it; the most recent entry header is likely "## Unreleased — alliance/support/intent redesign (2026-04-30)" or similar. Above that, prepend a new section:

```markdown
## Unreleased — aid-given cap (2026-04-30)

**New config knob:**

- `GameConfig.aid_given_cap: int = 3` — per-pair cap on `aid_given[(A,B)]`
  ledger entries. Bounds the long-term leverage stockpile without
  affecting per-turn aid effects (+1 strength, alliance-bonus eligibility,
  token consumption all fire normally for spends past cap).

  With default cap=3, `leverage(A, B) ∈ [-3, +3]`, producing at most +1
  combat bonus (vs +2 when uncapped). Halves Patron's late-game weapon
  while preserving leverage as a smaller asymmetric edge.

  Sim sweep flag: `--aid-given-cap N`. Set to 999 to recover prior behavior.
```

- [ ] **Step 5.2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG entry for aid-given cap"
```

---

## Task 6: Final verification + push

- [ ] **Step 6.1: Full suite green**

```bash
pytest
```

Expected: all green; should be the prior count + 7 new tests (2 from Task 1, 5 from Task 2).

- [ ] **Step 6.2: Sanity check git log**

```bash
git log --oneline 6ca3d3c..HEAD
```

Expected: 5 commits (Task 1, 2, 3, 4, 5).

- [ ] **Step 6.3: Push to origin**

```bash
git push -u origin aid-given-cap
```

Note: do NOT auto-merge or open a PR yet — surface the leaderboard comparison numbers to the user first so they can decide whether to merge or tune the cap value.

---

## Done criteria

- All checkboxes ticked.
- `pytest` is green.
- `git grep "aid_given_cap" foedus/ scripts/ tests/` shows references in core.py (definition), press.py (clamp), foedus_sim_sweep.py (CLI), and tests/test_aid_given_cap.py.
- Empirical sweep meets acceptance criteria (Patron −10 ≥, DC doesn't inherit crown, Cooperator/TC within ±10).
- Branch pushed to origin awaiting decision on PR.
