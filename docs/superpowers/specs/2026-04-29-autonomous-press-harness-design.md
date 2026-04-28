# Bundle 6 — Autonomous press playtest harness

**Status:** Design approved. Ready for implementation plan.
**Date:** 2026-04-29
**Author:** David Erner + Claude (Opus)

## Why

The current press playtest harness (`scripts/foedus_press_play.py`) requires
the controller (the main agent) to mediate every round: render prompts,
dispatch subagents, collect their JSON, apply via CLI commands, call
`advance`. That's ~28 controller bash invocations per 7-turn game, plus
the cognitive load of conducting two phases × two seats per round.

This bundle moves the orchestration into a long-running game server.
Subagents run a single blocking client command per player; the server
auto-advances rounds when all surviving players have signaled done. The
controller starts the server, dispatches subagents, and watches until
the game terminates.

This also lays foundation for foedus-godot's eventual press support —
the same HTTP endpoints the LLM client uses will serve the Godot frontend.

## Out of scope

- Game-mechanic changes (Bundle 5: heuristic strategy revision; Bundle 4:
  alliance multipliers)
- Persistent server state (games are in-memory only; lost on restart;
  matches existing `game_server` semantics)
- Authentication / multi-tenancy
- Replay / rewind (out of scope for this bundle; `/history` endpoints
  already exist for it independently)

## Architecture

```
                  ┌──── controller (main agent) ────┐
                  │                                  │
                  │ 1. uvicorn foedus.game_server &  │
                  │ 2. POST /games (create)          │
                  │ 3. dispatch subagent ×2          │
                  │ 4. poll /games/{gid} until term  │
                  │ 5. dispatch feedback subagents   │
                  └──────────────┬───────────────────┘
                                 │
                                 ▼
              ┌─────── foedus.game_server ────────┐
              │                                    │
              │  POST   /chat       (one per turn) │
              │  POST   /commit     (one per turn) │
              │  GET    /chat-prompt/{p}           │
              │  GET    /commit-prompt/{p}         │
              │  GET    /wait/{p}/{phase}  (poll)  │
              │                                    │
              │  Auto-advance on round_complete:   │
              │  - call HeuristicAgent for agent   │
              │    seats (press + orders)          │
              │  - finalize_round                  │
              │  - reset chat_done + round_done    │
              └────────┬───────────────────────────┘
                       │
                       ▼
              ┌── foedus.press / .resolve engine ──┐
              │  unchanged from Bundle 2            │
              │  + 2 new helpers (see below)        │
              └─────────────────────────────────────┘

         ┌──── subagent client (one per LLM seat) ───┐
         │                                            │
         │  python scripts/foedus_press_client.py    │
         │    --server URL --game GID --player N     │
         │                                            │
         │  Loop until terminal:                      │
         │   1. GET /wait/{p}/chat  (long-poll)       │
         │   2. GET /chat-prompt/{p} → stdout         │
         │   3. read stdin → POST /chat               │
         │   4. GET /wait/{p}/commit (long-poll)      │
         │   5. GET /commit-prompt/{p} → stdout       │
         │   6. read stdin → POST /commit             │
         │   7. check terminal; loop                  │
         └────────────────────────────────────────────┘
```

## Engine API additions

Two small additions to `foedus/press.py`:

```python
def signal_chat_done(state: GameState, player: PlayerId) -> GameState:
    """Mark a player as done with the chat phase. Idempotent.
    Cannot be undone within a round.

    Returns state unchanged if phase is not NEGOTIATION or player is
    eliminated.
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if player in state.eliminated:
        return state
    new_chat_done = set(state.chat_done)
    new_chat_done.add(player)
    return replace(state, chat_done=new_chat_done)


def is_chat_phase_complete(state: GameState) -> bool:
    """True iff every surviving player has signaled chat-done."""
    survivors = {
        p for p in range(state.config.num_players)
        if p not in state.eliminated
    }
    return survivors.issubset(state.chat_done)
```

`finalize_round` resets `chat_done` along with the other round-scratch
fields (`round_chat`, `round_press_pending`, `round_done`).

One small `foedus/core.py` addition: `chat_done: set[PlayerId] = field(...)`
on `GameState`. Wire serialization adds it as a new field; backward-compat
default to empty set when missing from older blobs.

## HTTP endpoints

All endpoints are scoped under `/games/{gid}/` (existing pattern).

### POST /games/{gid}/chat

Request body:
```json
{
  "player": 0,
  "draft": null
                                        // OR
  "draft": {"recipients": null, "body": "..."}
                                        // OR
  "draft": {"recipients": [1, 2], "body": "..."}
}
```

If `draft` is `null` or omitted, the player skips chat for this round.
Either way, the server records `chat_done[player] = True`.

If `draft` is provided, the server calls `record_chat_message` with the
`ChatDraft`. If the engine rejects the message (e.g. char-cap exceeded),
the server still marks `chat_done` — the player took their chat turn,
even if the message was dropped. Returns the engine's drop reason.

Response:
```json
{"ok": true, "chat_phase_complete": false}
```

Errors:
- 400 if `player` is unknown or eliminated
- 400 if `player` is not an LLM seat (heuristic seats are filled by server)
- 409 if `player` already in `chat_done` for this round

### POST /games/{gid}/commit

Request body:
```json
{
  "player": 0,
  "press": {
    "stance": {"1": "ally"},
    "intents": [...]
  },
  "orders": {
    "0": {"type": "Move", "dest": 5}
  }
}
```

Server flow:
1. Verify `player` is LLM seat, not eliminated, not already in `round_done`.
2. Verify `is_chat_phase_complete(state) == True`. If not, return 425
   (Too Early) with `"awaiting_chat": [list of pids]`.
3. Parse press and orders (using existing `wire.deserialize_*`).
4. Call `submit_press_tokens(state, player, press)`.
5. Save player's orders into the session's order buffer.
6. Call `signal_done(state, player)`.
7. If `is_round_complete(state)`: server fills agent-seat press +
   orders, calls `finalize_round`, resets round-scratch. (Mirrors the
   existing `auto_advance` machinery in `session.py`.)

Response:
```json
{"ok": true, "round_advanced": false, "is_terminal": false}
```
or, if the commit triggered a round advance:
```json
{"ok": true, "round_advanced": true, "is_terminal": false, "new_turn": 3}
```

### GET /games/{gid}/chat-prompt/{player}

Returns rendered chat-phase prompt as `text/plain`. Server-side render
ports `cmd_prompt_chat` from `scripts/foedus_press_play.py` (~70 lines).

Response: plain text body with the prompt.

Errors:
- 404 unknown game / player
- 400 player not an LLM seat

### GET /games/{gid}/commit-prompt/{player}

Returns rendered commit-phase prompt as `text/plain`. Ports
`cmd_prompt_commit` (~80 lines).

Errors:
- 425 (Too Early) if chat phase not complete — client should call
  `/wait/{p}/commit` first.
- Other errors as above.

### GET /games/{gid}/wait/{player}/{phase}

Long-poll endpoint. `phase` is `"chat"` or `"commit"`. Server holds the
request open (max 30 seconds) until the player's expected next phase
matches the requested one, then returns.

Returns:
```json
{"ready": true, "current_phase": "chat", "turn": 3}
```
or, on timeout:
```json
{"ready": false, "current_phase": "commit", "turn": 3}
```
(Client retries on `ready: false`.)

A player's "expected next phase" is:
- `"chat"` if the round is in chat phase AND `player` not in `chat_done`
- `"commit"` if chat phase complete AND `player` not in `round_done`
- `"chat"` (next round) if `round_done` for current turn (server already
  auto-advanced)
- `null` if game terminal — client should detect this and exit

Implementation: `asyncio.sleep(0.5)` poll loop on the session state with
the 30s timeout. Lightweight. Standard FastAPI async pattern.

## Subagent client: `scripts/foedus_press_client.py`

Single command, single Python file (~150 lines), no dependencies beyond
`urllib` (stdlib).

Usage:
```bash
python scripts/foedus_press_client.py \
    --server http://localhost:8090 \
    --game $GID \
    --player 0 \
    [--max-rounds 7]    # safety cap; defaults to 100
```

Behavior:
- Long-polls `/wait/{p}/chat`. When ready, GETs `/chat-prompt/{p}` and
  prints to stdout.
- Subagent reads the prompt from stdout, decides on JSON, writes to
  stdin (one line, JSON).
- Client POSTs `/chat` with the parsed payload.
- Long-polls `/wait/{p}/commit`. Same loop for commit phase.
- After commit POST, if `is_terminal`, prints final summary
  (final scores, winner) and exits 0.
- If a phase poll returns `null` next-phase (terminal detected during
  wait), exit 0.

Error handling:
- Connection errors: retry 3 times with exponential backoff, then exit 1.
- 4xx errors with player-side mistakes (e.g. malformed JSON): print error
  to stderr, exit 2. Caller (subagent) sees this and can adjust.
- Server-side 5xx: retry 3 times, then exit 1.

The subagent prompt instructs them to keep the bash session open and
exchange one JSON line per phase via stdin.

## Heuristic seats

When the controller creates a game with `seats=[llm, llm, agent.HeuristicAgent,
agent.HeuristicAgent]`, the server distinguishes:
- **LLM seats**: must POST `/chat` and `/commit` for each round.
- **Agent seats**: server auto-fills.

At the **start of each round** (i.e. right after `finalize_round` resets
the round-scratch fields, OR at session creation for the first round),
the server does the following for each surviving agent seat:

1. Compute press via `agent.choose_press(state, player)`.
2. Call `submit_press_tokens(state, player, press)`.
3. Mark the seat in `chat_done` (heuristics don't chat).
4. Mark the seat in `round_done`.
5. Buffer the seat's orders (computed via `agent.choose_orders(state, player)`)
   in the session's order map for use at finalize time.

This means `is_chat_phase_complete` and `is_round_complete` both depend
ONLY on LLM seats — agent seats never block. When the last LLM seat
POSTs `/commit`, `is_round_complete` is True and the server runs
`finalize_round` with the order map (LLM-seat orders from the buffer
and agent-seat orders pre-computed at round start).

This mirrors the existing `auto_advance` machinery in
`game_server/session.py`; the new pieces are the press-submission and
chat-done marking. The orders pre-computation timing change (start of
round vs at advance time) is benign because heuristics are pure
functions of state and don't care about chat that arrives in between.

## Controller (main agent) workflow

The controller's flow per playtest run:

```bash
# 1. Start server in background.
uvicorn foedus.game_server.server:app --host 127.0.0.1 --port 8090 &
SERVER_PID=$!
sleep 1   # let it bind

# 2. POST /games to create the playtest config.
GID=$(curl -s -X POST http://localhost:8090/games -d '{...}' | jq -r '.game_id')

# 3. Dispatch two Haiku subagents in parallel.
#    Each runs press_client, decides per phase via stdin/stdout.
#    They run to game-over.

# 4. Poll /games/{gid}/view/0 every ~5s until is_terminal.

# 5. Capture final state. Dispatch two feedback subagents
#    (one per Haiku) for the post-game prompt.

# 6. Kill server.
kill $SERVER_PID
```

The controller never touches per-round mechanics — just creates, watches,
and tears down.

## Components and data flow

```
foedus/core.py              GameState += chat_done: set[PlayerId]
foedus/press.py             += signal_chat_done, is_chat_phase_complete
                            finalize_round resets chat_done
foedus/remote/wire.py       (de)serialize chat_done as new optional field
foedus/game_server/session.py
                            + chat-phase tracking
                            + commit handler (press + orders + signal_done)
                            + auto-advance trigger after each commit
                            + chat_done auto-mark for agent seats
foedus/game_server/server.py
                            + 5 new endpoints (chat, commit, prompts ×2, wait)
                            + reuse existing wire models for press/orders
foedus/game_server/render.py    (NEW)
                            chat-prompt and commit-prompt rendering
                            (extracted from scripts/foedus_press_play.py)
scripts/foedus_press_client.py  (NEW)
                            blocking subagent client
scripts/foedus_press_server.py  (NEW)
                            wrapper that runs `uvicorn` with sane defaults
                            (purely a convenience for the controller)
tests/test_press_server.py      (NEW)
                            ~10 integration tests for the new endpoints
```

The render extraction is small (~150 lines) but makes the code reusable
between the orchestrator and the server.

## Testing

### Unit tests in `tests/test_press_engine.py` (extend existing)

- `test_signal_chat_done_marks_player`
- `test_signal_chat_done_idempotent`
- `test_signal_chat_done_rejects_eliminated`
- `test_is_chat_phase_complete_with_all_signaled`
- `test_is_chat_phase_complete_skips_eliminated`
- `test_finalize_round_resets_chat_done`

### Integration tests in `tests/test_press_server.py` (new)

Using FastAPI's `TestClient`:

- `test_create_press_game_returns_game_id`
- `test_chat_endpoint_records_message`
- `test_chat_endpoint_skip_with_null_draft`
- `test_chat_endpoint_rejects_double_signal`
- `test_commit_endpoint_blocks_until_chat_phase_complete`
- `test_commit_endpoint_advances_round_when_all_signaled`
- `test_chat_prompt_endpoint_returns_text`
- `test_commit_prompt_endpoint_425_before_chat_done`
- `test_wait_endpoint_returns_ready_immediately_when_phase_open`
- `test_wait_endpoint_times_out_returns_not_ready`
- `test_full_round_via_http_with_2_llm_seats_2_agent_seats`

The last test is end-to-end: it creates a game, walks through one full
round via HTTP calls (chat → commit → auto-advance), and asserts the
final state.

### Smoke

The existing `tests/smoke/test_press_driver_smoke.py` should still pass
unchanged (it tests the engine path, not the server). No new smoke
needed for the server itself — the integration tests cover it.

### Manual verification

After implementation, run a partial playtest by hand:

```bash
# Start server
PYTHONPATH=. python3 scripts/foedus_press_server.py &

# Create game
curl -X POST http://localhost:8090/games -d '{...}'

# Manually drive ONE round via curl from the shell to verify the
# endpoints work as designed before dispatching real subagents.
```

## Backward compatibility

- **Existing endpoints (`POST /orders`, `POST /advance`, etc.) unchanged.**
  Games created without LLM-seat-press will work as before.
- **GameState wire format**: `chat_done` is a new optional field;
  deserializer defaults to empty set when missing. Old saves still load.
- **Engine APIs**: existing functions unchanged. Two new helpers added.
- **HeuristicAgent / RandomAgent**: unchanged. Their press behavior was
  already added in Bundle 3.
- **Orchestrator script (`scripts/foedus_press_play.py`)**: stays as-is
  for now — it's still useful for quick manual testing without a server.
  Could be deprecated later in favor of the server path, but no need to
  remove it as part of this bundle.

## Migration

None needed. This is purely additive (new endpoints, new client, new
tests). The Bundle 5 heuristic-strategy revision can land before or
after this bundle; they're independent.

## Success criteria

1. All 338+ existing tests pass.
2. New integration tests pass (~11 tests).
3. `scripts/foedus_press_server.py` starts a server cleanly on port 8090.
4. `scripts/foedus_press_client.py` runs a single phase end-to-end against
   the server (manual verification).
5. End-to-end playtest: I (controller) run a 4-player Haiku-vs-heuristic
   game with 2 dispatched subagents, watching only `/games/{gid}` for
   `is_terminal`. The two Haikus play 7 turns autonomously. I dispatch
   feedback subagents at the end. **Total controller bash invocations:
   ~10 (server start + create game + ~3 status polls + feedback prompts +
   server kill). Down from ~28 in the current setup.**
6. The new endpoints return reasonable error codes (400/409/425) for
   misuse, not 500s.
