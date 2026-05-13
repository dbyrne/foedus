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
| Q6 | Frontend: **hybrid** — htmx + Jinja for chrome, Godot HTML5 embed for the map view only |
| Q7 | Press/chat UI: htmx panel rendered alongside the Godot map embed on the same page (side-by-side on desktop, stacked on mobile) |
| Q8 | Persistence: sqlite + sqlalchemy |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Browser (Android Chrome)                                 │
│  ┌──────────────────────┐  ┌──────────────────────────┐  │
│  │ htmx + Jinja chrome  │  │ Godot HTML5 map embed    │  │
│  │ (login, lobby,       │  │ (one <iframe> per game)  │  │
│  │  chat, settings,     │  └──────────────────────────┘  │
│  │  game-list, results) │                                │
│  └──────────────────────┘                                │
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

### HTML pages (Jinja + htmx)

| Route | Purpose |
|---|---|
| `GET /` | Landing — redirect to `/games` if logged in, else "Sign in with GitHub" |
| `GET /auth/github/login` → `GET /auth/github/callback` | OAuth dance |
| `POST /auth/logout` | Clear session |
| `GET /games` | List of your games (active / pending / finished tabs) |
| `GET /games/new` | Game creation form (preset, max_turns, deadline, seats, webhook URL) |
| `POST /games` | Create game; redirect to `/games/{gid}` |
| `GET /games/{gid}` | Main game page: Godot iframe + htmx chat/orders panel |
| `POST /games/{gid}/chat` | Append chat message (htmx fragment swap) |
| `POST /games/{gid}/intents` | Set/update press intents |
| `POST /games/{gid}/done` | Signal done with negotiation phase |
| `POST /games/{gid}/orders` | Submit orders (also callable by Godot embed) |
| `GET /games/{gid}/state.json` | Fog-filtered GameState (Godot polls this) |
| `GET /games/{gid}/events` | Server-sent events stream (optional) |

### JSON API

The existing `foedus.game_server` endpoints are mounted under
`/api/v1/games/{gid}/…` with a thin auth wrapper that resolves
`session → user → seat → player_idx`.

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

## Frontend

### Chrome (htmx + Jinja)

- Jinja templates rendered server-side.
- htmx attributes (`hx-post`, `hx-target`) for partial updates — chat
  append, intent save, "done" button, refresh state.
- One CSS file, mobile-first. No build step.
- Avoid red/green status colors (David is red/green colorblind); use
  blue/orange/yellow plus icons/labels.

### Map embed (Godot HTML5)

- A static export of foedus-godot lives under `foedus/web/static/godot/`.
- The game page wraps it in an `<iframe>` whose query string carries
  `gid` + a short-lived JWT.
- The embed polls `/api/v1/games/{gid}/state` (SSE if straightforward,
  else 5s poll).
- The embed POSTs orders to `/games/{gid}/orders` with the JWT in the
  `Authorization:` header.

**Assumption to verify in plan:** foedus-godot has touch-friendly
node-tap order entry. If not, that work must precede integration.

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
      pages.py          # HTML routes (htmx + Jinja)
      api.py            # JSON API wrappers around game_server endpoints
    templates/
    static/             # CSS, htmx.min.js, godot export bundle
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

1. **foedus-godot touch UX** — verify (or build) touch-friendly
   node-tap order entry before integrating the embed.
2. **Wire-protocol coverage** — persisting `state_json` may surface
   `GameState` fields that don't round-trip cleanly through
   `foedus/remote/wire.py`.
3. **Per-game async lock** — verify the lock prevents lost updates
   under concurrent human actions and the deadline worker firing
   simultaneously.

## Future (post-MVP)

- Web Push notifications (Android Chrome supports the standard cleanly)
- Spectator mode / public game URLs
- Replay viewer using the existing resolution log
- Mid-game human seat replacement
- Multiple map presets / custom map upload
