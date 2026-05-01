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
  `self_dislodge_blocked`. Closes the
  "silent failure" UX gap flagged by Haiku playtest agents.
- `DoneCleared` — emitted when a player's `signal_done` flag auto-clears
  due to an ally revising an intent that the player's committed plans
  depended on.

**New behavior:**

- Live-intent visibility + dependency-aware `signal_done` auto-clear
  during NEGOTIATION. Rounds with no inter-player dependencies still
  close instantly. See spec for full semantics.
