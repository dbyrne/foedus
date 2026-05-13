# Async Web-Play MVP — Design

**Date:** 2026-05-12
**Status:** Approved, awaiting implementation plan
**Authors:** David Erner

## Goal

Ship a hosted foedus server + web client so David and dbyrne can play foedus
asynchronously from their phones, with multiple concurrent games and bots
filling empty seats.

## Non-Goals (MVP)

- Web Push notifications (Discord webhook only)
- Email notifications
- Spectator mode / public game viewing
- Game replay viewer
- Mid-game human seat replacement
- Multi-region deploy / horizontal scaling
- Custom map upload
- Rate limiting beyond the host's defaults
- Polished error pages

## Decisions

| # | Decision |
|---|---|
| Q1 | Scope: small multi-user, multiple concurrent games |
| Q2 | Auth: GitHub OAuth |
| Q3 | Seat assignment: configurable per-seat at game creation (human/bot dropdowns, any GitHub user can fill a human seat) |
| Q4 | Async pacing: per-game deadline picked at creation (12h / 24h / 48h / 72h / none); background worker auto-advances expired phases by substituting `HoldAgent` for missing humans |
| Q5 | Notifications: Discord webhook only |
| Q6 | Frontend: **pure-Godot SPA + minimal htmx launcher shell** — see "Frontend (revised)" below |
| Q7 | Press/chat UI: lives inside the Godot client (CouncilNegotiation already implements it) |
| Q8 | Persistence: sqlite + sqlalchemy |

### Q6 revision history

Initial decision was a hybrid (htmx chrome + Godot HTML5 embed for the map only). A static read of `/home/david/foedus-godot/` after the spec was first written showed that the Godot client is materially more complete than assumed — CouncilNegotiation, PressController, OrderController, and the resolution playback are all implemented, and `GameClient.gd` already speaks the existing `foedus.game_server` JSON API. The hybrid would have meant rebuilding chat/orders UI in htmx and bridging it to Godot via `postMessage` — duplicate work plus a sync surface area we don't need. Revised approach: keep htmx only for the bits Godot doesn't do (OAuth landing, multi-game lobby), use Godot for everything in-game. A planned implementation-phase spike (Phase 0 below) verifies bundle size and mobile touch behaviour before we commit further.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Browser (Android Chrome)                                 │
│  ┌──────────────────────┐                                │
│  │ htmx launcher shell  │   served at /, /login, /games  │
│  │ (OAuth, lobby,       │   — thin Jinja pages only      │
│  │  "New game" form)    │                                │
│  └──────────┬───────────┘                                │
│             │ link / redirect to /games/{gid}            │
│  ┌──────────▼───────────────────────────────────────┐    │
│  │ Godot HTML5 SPA (full Council UI: map, chat,    │    │
│  │ press, orders, resolution playback)              │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────┬───────────────────────────────────────────┘
               │ HTTPS (cookie-auth sessions)
┌──────────────▼───────────────────────────────────────────┐
│ FastAPI (`foedus.web`)                                   │
│  auth (GH OAuth) │ html views (Jinja) │ json api         │
│  ┌────────────────────────────────────────────────────┐  │
│  │ deadline_worker (asyncio task on app startup)      │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────┬───────────────────────────────────────────┘
               │
        ┌──────▼──────────────┐
        │ sqlite (Fly volume) │     ──→ Discord webhook (outbound)
        └─────────────────────┘
```

**Engine purity is preserved.** `foedus.web` is a thin HTTP + persistence
layer over the existing pure-function engine. No changes to
`foedus/press.py`, `foedus/resolve.py`, `foedus/loop.py`, etc. are required.
The existing `foedus.game_server` JSON endpoints are mounted under the new
app and reused by the Godot embed.

## Data Model (sqlite)

```
users
  id              INTEGER PRIMARY KEY
  github_id       INTEGER UNIQUE NOT NULL
  github_login    TEXT NOT NULL
  created_at      TIMESTAMP

games
  id              TEXT PRIMARY KEY        -- short slug, e.g. "tame-fox-7k2"
  created_by      INTEGER → users.id
  created_at      TIMESTAMP
  status          TEXT                    -- 'pending'|'active'|'finished'
  map_seed        INTEGER
  map_preset      TEXT
  max_turns       INTEGER
  phase_deadline_hours       INTEGER NULL  -- null = no deadline
  current_phase_deadline_at  TIMESTAMP NULL
  discord_webhook_url        TEXT NULL
  state_json      TEXT                    -- serialized GameState (wire format)
  finished_at     TIMESTAMP NULL

game_seats
  game_id         TEXT → games.id
  player_idx      INTEGER                 -- 0..N-1
  kind            TEXT                    -- 'human'|'bot'
  user_id         INTEGER NULL → users.id  -- iff kind='human'
  bot_class       TEXT NULL                -- iff kind='bot'
  PRIMARY KEY (game_id, player_idx)

chat_messages
  id              INTEGER PRIMARY KEY
  game_id         TEXT → games.id
  turn            INTEGER
  sender_idx      INTEGER
  recipients_mask INTEGER                 -- bitmask of recipient player_idx; -1 = broadcast
  body            TEXT
  created_at      TIMESTAMP

sessions
  token           TEXT PRIMARY KEY
  user_id         INTEGER → users.id
  expires_at      TIMESTAMP
```

**Indexes:** `games(status, current_phase_deadline_at)` for the deadline
worker; `game_seats(user_id)` for "my games."

`state_json` is the existing wire-format `GameState`. The engine remains the
source of truth; sqlite persists snapshots between requests. Chat is
broken out so we can render history without deserializing GameState.

## Routes

### HTML pages (Jinja, launcher shell only)

| Route | Purpose |
|---|---|
| `GET /` | Landing — redirect to `/games` if logged in, else `/login` |
| `GET /login` | "Sign in with GitHub" button |
| `GET /auth/github/login` → `GET /auth/github/callback` | OAuth dance |
| `POST /auth/logout` | Clear session |
| `GET /games` | List of your games (active / pending / finished tabs) |
| `GET /games/new` | Game creation form (preset, max_turns, deadline, seats, webhook URL) |
| `POST /games` | Create game; redirect to `/games/{gid}` |
| `GET /games/{gid}` | Wrapper page that loads the Godot SPA with `?gid=…&player_idx=…&token=…` |
| `POST /games/{gid}/jwt` | Mint a short-lived JWT for the Godot SPA from the session cookie |

### JSON API (consumed by Godot SPA)

The existing `foedus.game_server` endpoints are mounted under
`/api/v1/games/{gid}/…` with a thin auth wrapper that accepts EITHER a
session cookie OR a bearer JWT (Godot uses the JWT), then resolves
`user → seat → player_idx`. These endpoints include chat post, intent
set, signal-done, orders submit, fog-filtered state read, and the
long-poll wait already implemented in Bundle 6.

## Server-Side Flows

### Phase advance (driver)

After every human action (chat done, orders submit), the driver checks
`engine.is_*_phase_complete(state)`. If the phase is complete and bots
are next, it runs their `choose_press` / `choose_orders` synchronously
(cheap for `HeuristicAgent`), then `finalize_round`, persists, and pings
the next-up humans via Discord.

### Deadline worker

A single asyncio task started at app startup, ticking every 60 seconds:

```python
while True:
    expired = db.fetch(
      "SELECT id FROM games WHERE status='active' "
      "AND current_phase_deadline_at IS NOT NULL "
      "AND current_phase_deadline_at < now()")
    for gid in expired:
        async with game_lock(gid):
            for missing_human_seat in find_overdue_seats(gid):
                substitute_hold_orders(gid, missing_human_seat)
            advance_phase(gid)   # same path as the human-driven driver
    await asyncio.sleep(60)
```

### Concurrency

Each game has a per-game `asyncio.Lock`. Any handler that mutates state
(chat, intents, done, orders) takes the lock for the duration of the
read-modify-write. Two humans pressing "done" simultaneously serialize
through the lock.

## Frontend (revised)

### Launcher shell (htmx + Jinja)

Owns only the screens Godot doesn't already do well. Three pages, each
a single Jinja template:

- `GET /` → landing. Redirects to `/games` if logged in, else to
  `/login`.
- `GET /login` → "Sign in with GitHub" button. OAuth dance lands the
  user on `/games`.
- `GET /games` → list of the user's games (active / pending / finished
  tabs) plus a "New game" button.
- `GET /games/new` → seat-assignment form (preset / max_turns /
  deadline / per-seat human-or-bot / Discord webhook URL).
- `POST /games` → creates the row, redirects to `/games/{gid}`.

All other actions happen inside the Godot SPA. No htmx chat panel, no
htmx orders panel, no `postMessage` bridge.

CSS notes: mobile-first, one file, no build step. Avoid red/green
status colors (David is red/green colorblind); use blue/orange/yellow
plus icons/labels.

### Game SPA (Godot HTML5)

- A static export of foedus-godot is served from
  `foedus/web/static/godot/`.
- `GET /games/{gid}` returns a minimal HTML page that loads
  `static/godot/index.html` with query-string parameters: `gid`,
  `player_idx`, and a short-lived JWT minted by `foedus.web` from the
  user's session cookie.
- The SPA calls the existing `foedus.game_server` endpoints (mounted
  under `/api/v1/games/{gid}/…`) for state, chat, intents, done, and
  orders. `GameClient.gd` already speaks this API; only the JWT
  bearer-auth wiring is new.
- COOP/COEP headers (`Cross-Origin-Opener-Policy: same-origin`,
  `Cross-Origin-Embedder-Policy: require-corp`) are required by Godot
  4 HTML5 for `SharedArrayBuffer` (threads). FastAPI middleware sets
  them.

### What's not in foedus-godot yet (build during MVP)

- Reading `gid` / `player_idx` / JWT from the URL query string instead
  of from environment defaults.
- A "back to lobby" link in the SPA that navigates the browser to
  `/games`.
- Whatever the Phase 0 spike (below) reveals as mobile-blocking.

## Phase 0: foedus-godot mobile spike (FIRST TASK)

Before any backend work, the implementation plan's first task is a
time-boxed spike that produces evidence — not architecture analysis —
about whether the Godot client is mobile-ready. The decision to go
pure-Godot was made on a static read of the codebase; this spike
verifies that read with real bytes and real touches.

**Deliverables:**

1. HTML5 release export of foedus-godot produced via
   `godot --headless --export-release` (set up the web preset and CI
   step now; download the official 4.3-stable export templates).
2. Bundle size measurement: `du -sh` of the export directory + per-file
   breakdown of the top 5 largest files. Pass criterion: total
   gzipped/brotli'd transfer under ~30 MB.
3. A throwaway local harness that runs the existing
   `foedus.game_server` against a fresh 4-seat game, serves the Godot
   export with COOP/COEP headers, and opens it in a real mobile
   browser (Android Chrome on David's phone) or a phone-emulated
   desktop browser.
4. A walkthrough of one full negotiation→orders→resolution round on
   that mobile viewport. Record: cold-start time to first
   interaction; tap responsiveness on hex nodes; pinch/pan behaviour;
   whether the Android keyboard cooperates with the in-canvas chat
   input; any console errors.

**Decision gate:**

- If the spike passes (bundle within budget, taps land, chat keyboard
  works, no fatal console errors): proceed with pure-Godot SPA as
  specified.
- If touch/keyboard issues are minor: log them as Godot-side tasks in
  the implementation plan and proceed.
- If the bundle is over budget or chat input is unusable on mobile:
  revisit the frontend decision before writing any backend code. The
  fallback is the original hybrid (htmx chat panel + Godot map embed)
  — the backend design is unchanged either way.

## Code Layout

```
foedus/
  web/
    __init__.py
    app.py              # FastAPI app factory, mounts existing game_server router
    auth.py             # GitHub OAuth + session middleware
    db.py               # sqlalchemy engine, session
    models.py           # User, Game, GameSeat, ChatMessage, Session
    driver.py           # advance_phase(), substitute_hold_orders(), notify()
    deadline_worker.py  # background asyncio task
    notify.py           # Discord webhook poster
    routes/
      pages.py          # HTML launcher routes (Jinja)
      api.py            # JSON API: cookie-or-JWT auth wrapper around game_server endpoints
    templates/
    static/
      css/              # one mobile-first stylesheet
      htmx.min.js
      godot/            # HTML5 export of foedus-godot (built in CI)
migrations/             # alembic
tests/web/              # FastAPI TestClient integration tests
```

## Deployment

- `Dockerfile.web` — Python 3.12 slim, installs `foedus[web,remote]`,
  runs `uvicorn foedus.web.app:app`.
- `fly.toml` — single-region, 1 shared-cpu VM, `[[mounts]]` volume at
  `/data` for sqlite.
- GitHub Actions: on push to `main`, run `pytest` then `flyctl deploy`.
- Secrets via `flyctl secrets set`: `GITHUB_OAUTH_CLIENT_ID`,
  `GITHUB_OAUTH_CLIENT_SECRET`, `SESSION_SECRET`.

## Testing

- Unit-test new modules (driver, deadline_worker, notify) against a
  temp sqlite.
- Integration test using FastAPI TestClient: create game, walk one full
  turn as two simulated humans, verify state advances correctly.
- Stub Discord webhook in tests (no real network calls).
- Manual smoke test (documented in README): one real game with both
  humans on phones, deadline=24h, run to completion.

## Open Implementation Risks

1. **foedus-godot mobile readiness** — bundle size, pinch/pan touch
   behaviour, and Android-keyboard-vs-in-canvas-chat-input are all
   unverified. Phase 0 spike (above) is the gating check.
2. **Wire-protocol coverage** — persisting `state_json` may surface
   `GameState` fields that don't round-trip cleanly through
   `foedus/remote/wire.py`.
3. **Per-game async lock** — verify the lock prevents lost updates
   under concurrent human actions and the deadline worker firing
   simultaneously.
4. **JWT-to-Godot handoff** — `GameClient.gd` will need a small change
   to read `gid` / `player_idx` / token from `window.location.search`
   and use the token as a bearer header. Mechanical, but a foedus-godot
   change is on the critical path.
5. **COOP/COEP headers + OAuth callback** — the OAuth callback page
   (htmx) and the Godot SPA page (Godot) need different header
   policies; COOP/COEP for the SPA can break GitHub's OAuth popup if
   applied site-wide. Apply per-route.

## Future (post-MVP)

- Web Push notifications (Android Chrome supports the standard cleanly)
- Spectator mode / public game URLs
- Replay viewer using the existing resolution log
- Mid-game human seat replacement
- Multiple map presets / custom map upload
