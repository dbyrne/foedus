# Changelog

## Unreleased — aid-given cap (2026-04-30)

**New config knob:**

- `GameConfig.aid_given_cap: int = 3` — per-pair cap on `aid_given[(A,B)]`
  ledger entries. Bounds the long-term leverage stockpile that Patron
  weaponizes for late-game asymmetric attacks. Per-turn aid effects
  (+1 strength, alliance-bonus eligibility, token consumption) all fire
  normally for spends past cap; only the long-term ledger increment is
  clamped.

  With default cap=3, `leverage(A, B) ∈ [-3, +3]`, producing at most +1
  combat bonus (vs +2 when uncapped).

  Sim sweep flag: `--aid-given-cap N`. Set to 999 to recover prior behavior;
  set to 1 to effectively disable the leverage_bonus mechanic.

**Empirical effect (1k-game sweep, 19-agent pool):**

- Patron mean: 166.6 → 159.7 (−6.9). No longer monopoly leader; now
  clusters with Cooperator (160.7) and TrustfulCooperator (156.2).
- DishonestCooperator does NOT inherit the crown (154.6 < 159.7).
- Honest cooperators stay within ±10 of pre-cap baseline.

**Known limitation:** the cap alone is partial mitigation. The leverage_bonus
formula `min(2, lev//2)` floors via integer division, so any cap ≥ 2 still
allows max bonus +1; Patron's exploit rarely needs the full +2, so the
ledger ceiling has a soft effect that plateaus around −7 points. Sharper
Patron containment would require combining the cap with another lever
(decay over time, or stance-conditional bonus trigger). Future spec.

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
  `self_dislodge_blocked`. Closes the
  "silent failure" UX gap flagged by Haiku playtest agents.
- `DoneCleared` — emitted when a player's `signal_done` flag auto-clears
  due to an ally revising an intent that the player's committed plans
  depended on.

**New behavior:**

- Live-intent visibility + dependency-aware `signal_done` auto-clear
  during NEGOTIATION. Rounds with no inter-player dependencies still
  close instantly. See spec for full semantics.
