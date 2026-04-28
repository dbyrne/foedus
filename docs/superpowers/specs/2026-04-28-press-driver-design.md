# Bundle 3 — Press v0 driver wiring

**Status:** Design approved. Ready for implementation plan.
**Date:** 2026-04-28
**Author:** David Erner + Claude (Opus)

## Why

Press v0 (PR #1) added structured negotiation primitives — stance tokens,
declared intents with per-recipient visibility, free-text chat,
betrayal observations, and a mutual-ALLY détente streak — but **no
LLM-facing driver currently exposes them**. Both the Sonnet playtest
(Dave's) and the Haiku-vs-heuristic playtest (this branch's) ran with
`advance_turn`, which is the no-press shim that auto-submits empty
`Press` for every survivor.

In the previous Haiku playtest, `press_history` showed seven turns of
`Press(stance={}, intents=[])` for every player. Press v0 is
shipped-but-untested-in-the-wild.

This bundle wires up a press-aware driver, runs a fresh 4-player
playtest, and **answers the question: does Press v0 actually shift
gameplay vs. the press-less baseline?** That's the single learning goal.

## Out of scope

Deliberately deferred to keep the next playtest's signal attributable to
the press knob alone:

- **D** — fog-respecting `legal_orders_for_unit` (don't reveal off-fog
  support targets in the legal-orders enumeration).
- **H** — threat-context in per-player view (highlight enemy units
  adjacent to your supplies).
- Other bundle 2 design calls (walk-in capture, strict-majority).

These can ride in a follow-up bundle once we see how press alone affects
play.

## Scope

1. **HeuristicAgent press support** — implement `choose_press` /
   `chat_drafts` so the silent-by-default heuristic baseline becomes a
   minimally-participating player in negotiation. Without this, half the
   table is mute and the LLMs have no one to negotiate with.
2. **Press-aware driver** — replace `/tmp/foedus_haiku_play.py` with a
   committed `scripts/foedus_press_play.py` that drives the two-phase
   round (chat phase → commit phase) via subagent calls.
3. **Smoke test** — full 4-player heuristic-only game runs through the
   press driver, with non-empty `press_history` and clean `finalize_round`.
4. The actual LLM playtest, run after merge, is the integration test for
   the bundle. Findings get logged to Nexus and inform Bundle 2.

## Round flow

The engine never actually transitions `phase` to `Phase.ORDERS` —
`finalize_round` resets back to `NEGOTIATION` at the end of every
turn, and `Phase.ORDERS` is only used in tests as a sentinel meaning
"engine should reject press now." The driver is therefore responsible
for sequencing the two phases.

Per turn, the driver runs:

1. **Chat phase** — for each active LLM seat:
   - Render a chat prompt showing inbound chat from earlier in this
     round (if any), public stance matrix from last round, inbound
     intents from last round, and any betrayal observations.
   - Dispatch a Haiku subagent. Subagent returns one of:
     - `{"recipients": null | [pid, ...], "body": "<=500 chars"}` →
       call `record_chat_message`.
     - `{}` → skip (no chat sent).
   - **Limit is one chat message per LLM seat per turn**, enforced by
     the driver (the engine's `record_chat_message` itself accepts
     unlimited per-round chats; we keep it bounded for cost control
     and to stay close to the "one chat round, then commit" Q2-B
     decision). Easy to relax later by accepting a list of drafts.
   - Heuristic seats skip chat entirely (they're silent).
2. **Commit phase** — for each active LLM seat:
   - Render a commit prompt that adds: all visible same-turn chat,
     map (with bundle-1 ASCII view), legal orders.
   - Dispatch a Haiku subagent. Subagent returns:
     - `{"press": {"stance": {...}, "intents": [...]}, "orders": {...}}`
   - Driver calls `submit_press_tokens(state, player, parsed_press)`
     and writes parsed orders to a per-player pickle for `advance`.
   - Heuristic seats: driver calls `HeuristicAgent.choose_press` →
     `submit_press_tokens` directly during `advance`.
3. **Finalize** — `advance` calls `signal_done` for everyone and then
   `finalize_round(orders_by_player)`.

LLMs do NOT see any other player's stance, intents, or orders before
committing their own — those are revealed at end-of-round through
`press_history`. They DO see all visible same-turn chat in phase 2.

## Heuristic press behavior

`HeuristicAgent.choose_press(state, player) -> Press`:

- **stance**: ALLY toward the active opponent whose `state.supply_count(o)`
  is closest to `state.supply_count(player)`. Ties broken by lower
  `player_id`. All other opponents get omitted (= NEUTRAL by default).
  If `player` has no active opponents (last-standing or all eliminated),
  returns empty stance.
- **intents**: empty list. Heuristics don't pre-commit publicly; this
  also avoids leaking heuristic moves to LLMs.

`HeuristicAgent.chat_drafts(state, player) -> list[ChatDraft]`:

- Returns `[]` (silent). Heuristics do not chat.

This rule creates a "consensus among similar-scoring peers" dynamic.
It is intentionally not anti-leader — we want to observe what coalition
shape emerges, not bake one in. If the playtest shows it's too dull
we can revise in a follow-up.

## Driver: `scripts/foedus_press_play.py`

Picks up the existing `/tmp/foedus_haiku_play.py` design (pickle-backed
state, per-player JSON I/O, subagent-driven). Promoted out of `/tmp`
into the repo so it's reviewable, version-controlled, and runnable by
anyone cloning the project.

State persists in `/tmp/foedus_press_state.pickle`. Per-player files:
`/tmp/foedus_press_chat_p{N}.json`, `/tmp/foedus_press_commit_p{N}.json`.

### Commands

```
init                  # initial_state, phase=NEGOTIATION
prompt_chat P         # emit phase-1 chat prompt for player P
apply_chat P FILE     # parse chat draft → record_chat_message
prompt_commit P       # emit phase-2 commit prompt for player P
apply_commit P FILE   # parse {press, orders}
                      #   → submit_press_tokens(player, press)
                      #   → store orders to disk for advance
advance               # heuristic seats: choose_press + submit_press_tokens
                      # all surviving seats: signal_done
                      # then finalize_round(orders_by_player)
status                # turn / scores / eliminated / winners
log                   # full state.log
feedback P            # post-game feedback prompt for player P
```

### Per-turn loop (orchestrator perspective)

```
for each LLM seat P in {0, 1}:
  prompt_chat P → /tmp/p{P}_chat_prompt.txt
  dispatch Haiku subagent on that prompt
  subagent JSON → /tmp/p{P}_chat_orders.json
  apply_chat P /tmp/p{P}_chat_orders.json

for each LLM seat P in {0, 1}:
  prompt_commit P → /tmp/p{P}_commit_prompt.txt
  dispatch Haiku subagent on that prompt
  subagent JSON → /tmp/p{P}_commit_orders.json
  apply_commit P /tmp/p{P}_commit_orders.json

advance
```

### JSON schemas

Chat draft:

```json
{"recipients": null, "body": "I propose we both attack P2 next turn."}
```
or `{"recipients": [0, 2], "body": "..."}` for private group chat,
or `{}` to skip.

Commit:

```json
{
  "press": {
    "stance": {"0": "ally", "2": "neutral", "3": "hostile"},
    "intents": [
      {"unit_id": 3,
       "declared_order": {"type": "Move", "dest": 5},
       "visible_to": null}
    ]
  },
  "orders": {
    "3": {"type": "Move", "dest": 5},
    "5": {"type": "Hold"}
  }
}
```

Both `stance` and `intents` are optional (default empty/empty).
`orders` is required (default-Hold for any owned units the LLM omits,
to keep the engine's expected schema). `visible_to` follows the engine
convention: `null` = public broadcast, list of pids = private group,
empty list = silently dropped.

## Components and data flow

```
              ┌─ orchestrator (scripts/foedus_press_play.py) ─┐
              │                                               │
              │   init / prompt_* / apply_* / advance         │
              └────────────┬──────────────────────────────────┘
                           │
                           ▼
            ┌──────────── pickle ─────────────┐
            │   /tmp/foedus_press_state.pickle │
            └─────────────┬───────────────────┘
                          │
       ┌──────────────────┴──────────────────┐
       │                                     │
       ▼                                     ▼
┌─ press.py engine ─┐         ┌─ HeuristicAgent ─┐
│ submit_press_tokens          │ choose_press      │
│ record_chat_message          │ chat_drafts       │
│ signal_done                  │ choose_orders     │
│ finalize_round               │                   │
└──────────────────┘           └───────────────────┘
       │
       ▼
   (Haiku subagent prompts via Agent tool, model="haiku")
```

The engine and HeuristicAgent are pure; only the orchestrator does I/O.

## Error handling

- **Malformed JSON in apply_chat / apply_commit**: orchestrator emits
  `WARN: bad <field>: <reason>; skipping <action>`. For commit, missing
  `orders` defaults to all-Hold; missing `press` defaults to empty
  Press. This matches bundle-1 orchestrator's policy of leniency.
- **LLM submits intents for units it doesn't own**: filtered by
  `submit_press_tokens` (existing behavior). Driver does not need to
  pre-validate.
- **LLM submits intents with empty `visible_to` list**: silently dropped
  by `submit_press_tokens` (existing behavior).
- **Player tries to chat in phase 2 (commit)**: not supported by this
  driver; commit prompt only accepts orders+press, not chat.
  `record_chat_message` would silently drop a phase-2 chat anyway via
  the existing `if state.phase != Phase.NEGOTIATION` guard, so no
  driver-level enforcement needed.
- **Heuristic with no active opponents** (e.g. last-standing): empty
  stance, empty intents. Game is already terminal; doesn't matter.

## Testing

### Unit tests — `tests/test_heuristic_press.py` (new)

- `test_choose_press_allies_closest_supply_count`
- `test_choose_press_tiebreaks_by_lower_pid`
- `test_choose_press_empty_when_last_standing`
- `test_choose_press_returns_empty_intents`
- `test_chat_drafts_returns_empty_list`

### Smoke test — `tests/smoke/test_press_driver_smoke.py` (new)

Runs a full 4-player **heuristic-only** game (no LLM subagents) through
the orchestrator's press path:

```python
# Pseudo:
state = initial_state(cfg, m)
while not state.is_terminal():
    for p in survivors:
        press = HeuristicAgent().choose_press(state, p)
        state = submit_press_tokens(state, p, press)
        state = signal_done(state, p)
    orders = {p: HeuristicAgent().choose_orders(state, p)
              for p in survivors}
    state = finalize_round(state, orders)
assert len(state.press_history) > 0
assert any(any(p.stance for p in turn.values())
           for turn in state.press_history)
```

This verifies the full press lifecycle works end-to-end and that
heuristic press isn't all-empty.

### Existing engine tests

`test_press.py`, `test_round_lifecycle.py`, `test_chat.py`,
`test_press_types.py` already cover the engine functions. They must
continue to pass; no changes expected.

### Manual integration test

The Haiku playtest, run after merge by spawning Haiku subagents
through the new driver. Findings logged to Nexus.

## Backward compatibility

- `advance_turn` (the no-press shim) is **untouched**. Existing
  callers (`play_game`, the game_server, training paths) continue to
  work without ever exercising press. This bundle adds a new code
  path; it doesn't alter the old one.
- `HeuristicAgent.choose_press` already exists as a Protocol-default
  no-op (PR #4). Replacing it with a real implementation is
  transparent to existing callers.

## Open questions

None. All four design questions resolved during brainstorming:

| # | Resolution |
|---|---|
| 1 | Scope: P-only. D and H deferred. |
| 2 | Chat shape: B (one chat round, then commit). |
| 3 | Composition: A (2 Haiku + 2 Heuristic). |
| 3' | Heuristic press: closest-supply-count rule, no intents, no chat. |

## Success criteria

1. All existing tests pass; new heuristic press tests pass; smoke test
   runs to terminal with non-empty `press_history`.
2. Driver can be invoked manually (e.g. `python scripts/foedus_press_play.py
   init / prompt_chat 0 / ...`) and emits sensible prompts.
3. Haiku playtest runs end-to-end. We have empirical answer to "does
   Press v0 affect gameplay?" — even if the answer is "not much," that
   informs Bundle 2 priorities (e.g. is press-as-shipped the right
   shape? do we need richer primitives?).
