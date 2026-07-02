# Foedus Phase 0b / F5 — binding joint intents (the "Pact" primitive)

**Date:** 2026-07-01
**Status:** Implemented (minimal, ratified two-party pact). Conditional orders deferred.
**Driven by:** `2026-07-01-foedus-phase0-arena-fixes-design.md` §F5 and
`2026-07-01-foedus-arena-playtest-findings.md` finding ②.

## Problem

Today `Intent` (`foedus/core.py`) is single-unit, own-unit, unconditional. Two allies
cannot form a *binding, synchronized, multi-party commitment* — "I move `u_a` onto X the
same turn your `u_b` supports it." The playtest showed rich diplomacy and coordinated
maneuver but **no decisive combat/betrayal fired**, because the press layer had nothing
concrete enough to *ratify* or *betray*. F5 adds that primitive.

## Scope

**Minimal (shipped):** a ratified two-party **Pact** — a proposed joint commitment
describing coordinated orders for the upcoming resolution, which the counterparty can
accept, and whose breach is observable at `finalize_round`.

**Deferred (stretch, NOT shipped):** conditional orders ("Move u→X IF ally u_b supports,
else Hold"). Higher risk (resolution-order semantics); kept out to preserve the "a Pact is
a commitment record, not a new combat rule" invariant. Deferred to a later dispatch.

**Also deferred (separate dispatches, per §0b):** private stance (F4), betrayal mechanical
penalty (F6), build agency (F7). F5 only *emits* the breach signal; F6 will attach the
mechanical cost to it.

## Types (`foedus/core.py`)

```python
class PactStatus(Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"

@dataclass(frozen=True)
class PactTerm:
    player: PlayerId          # obligated party (proposer or counterparty)
    unit_id: UnitId           # one of player's units
    declared_order: Order     # the order player commits to issue

@dataclass(frozen=True)
class Pact:
    pact_id: int
    proposer: PlayerId
    counterparty: PlayerId
    terms: tuple[PactTerm, ...]   # spans BOTH parties
    status: PactStatus
    proposed_turn: int            # state.turn when proposed (drives expiry)

@dataclass(frozen=True)
class PactBreach:
    turn: int                 # resolved turn (state.turn + 1), matches BetrayalObservation
    pact_id: int
    breacher: PlayerId
    term: PactTerm            # the obligation that was broken
    actual_order: Order       # what breacher actually submitted
```

## GameState fields

- `pacts: list[Pact]` — live pacts (proposed + accepted). Persist across rounds under the
  lifecycle below; NOT round scratch.
- `next_pact_id: int` — monotonic id source (deterministic; no RNG/clock).
- `pact_breaches: dict[PlayerId, list[PactBreach]]` — cumulative ledger, keyed by the
  *observing* (non-breaching) party. Mirrors `betrayals`.

## Lifecycle (engine functions, `foedus/press.py`)

- `propose_pact(state, proposer, counterparty, terms) -> GameState`
  - No-op (returns state unchanged) unless: phase == NEGOTIATION, both players active,
    proposer != counterparty, proposer not in `round_done`.
  - Terms filtered silently: each `term.player` must be `proposer` or `counterparty`, and
    `term.unit_id` must be owned by `term.player` at propose time. A Pact is created only
    if ≥1 valid term remains for **each** party (a genuine joint commitment); otherwise
    dropped (matches the silent-normalization invariant — degenerate submissions vanish,
    no raise).
  - Assigns `pact_id = state.next_pact_id`, increments the counter, appends a PROPOSED
    Pact with `proposed_turn = state.turn`.

- `accept_pact(state, pact_id, accepter) -> GameState`
  - No-op unless: phase == NEGOTIATION, accepter active, accepter not in `round_done`, a
    PROPOSED pact with `pact_id` exists whose `counterparty == accepter`.
  - Flips that pact to ACCEPTED. Idempotent (already-ACCEPTED → unchanged).

- At `finalize_round`, before resetting round scratch:
  - **Breach check** every ACCEPTED pact against the RAW submitted orders (`flat`), exactly
    as `_verify_intents` compares intents. For each term: if the unit is gone or no longer
    owned by `term.player` → **void** (no breach). Else breach iff
    `submitted_order != term.declared_order`. Each breach emits a `PactBreach` into
    `pact_breaches[other_party]` (the non-breaching party of the pact).
  - **Consume** every ACCEPTED pact (removed; its orders were for this resolution).
  - **Expire** PROPOSED pacts with `proposed_turn < state.turn` (proposed last round, not
    accepted this round). Keep PROPOSED pacts with `proposed_turn == state.turn` (proposed
    this round → one more round to accept). This is exactly "same or next round to accept."
  - Carry `pacts`, `next_pact_id`, `pact_breaches` forward through the `replace(s_after,…)`
    (like `betrayals`/`aid_given`), since `_resolve_orders` builds a fresh state that drops
    press-layer fields.

## Resolution invariant (correctness bar)

A Pact touches **only** breach detection and the pacts ledger — never `_resolve_orders`.
Therefore honoring a supported-move under a Pact resolves **identically** to issuing the
same orders with no Pact present. Verified by a dedicated test.

## Fog (`foedus/fog.py`)

`visible_state_for` gains:
- `your_pacts`: live pacts where `player ∈ {proposer, counterparty}`.
- `your_pact_breaches`: `pact_breaches.get(player, [])`.

## Rendering (`foedus/render_common.py`, reused by game_server + orchestrator)

- `render_active_pacts(state, player)` — "ACTIVE PACTS" block: each pact's id, parties,
  status, pending-acceptor, and per-term `(player, unit, order_to_str)`.
- `render_pact_breach_ledger(state, player)` — cumulative pact-breach ledger, alongside the
  existing betrayal ledger.

Wired into both `foedus/game_server/render.py` and `scripts/foedus_press_play.py` prompts.

## Agent interface

Optional hooks (hasattr-checked, like `choose_aid`, to preserve the `runtime_checkable`
`Agent` membership check):
- `choose_pacts(state, player) -> list[PactProposal]` — proposals to make this round.
- `accept_pacts(state, player) -> list[int]` — pact_ids to accept this round.

`PactProposal` is a small frozen carrier `(counterparty, terms)`. `play_game` (loop.py)
runs a proposals pass for all players, then an acceptances pass (so a player can accept a
same-round proposal), then done. `scripts/foedus_press_play.py` gains a `pacts` block in the
commit JSON (`{"propose": [...], "accept": [...]}`) with matching parser.

## Wire protocol (`foedus/remote/wire.py`)

Pacts are **deliberately omitted** from the wire format, matching the existing precedent for
Press v0 fields (`press_history`, `betrayals`, …) and `last_turn_score_delta`: they are
press-layer social state, not needed for the remote `choose_orders` decision. Documented in
`wire.py`. Deserialize defaults them empty, so states round-trip cleanly.
