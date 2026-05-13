# Async Web-Play MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a hosted FastAPI + sqlite + thin htmx launcher + Godot HTML5 SPA so David and dbyrne can play foedus asynchronously from their phones, with bots filling empty seats and a deadline worker auto-advancing stalled phases.

**Architecture:** New `foedus.web` package wraps the existing pure-function engine (no engine changes). htmx-served Jinja pages handle GitHub OAuth, multi-game lobby, and game creation. The Godot client (foedus-godot, already feature-complete for in-game UI) is served as a static export from `foedus/web/static/godot/` and authenticates to the JSON API with a short-lived JWT minted from the user's session cookie. sqlite (via sqlalchemy + alembic) persists `User`, `Game`, `GameSeat`, `ChatMessage`, `Session`. A per-game `asyncio.Lock` plus a 60s deadline-tick worker enforce async correctness.

**Tech Stack:** Python 3.12, FastAPI, sqlalchemy 2.x, alembic, authlib (GitHub OAuth), PyJWT, Jinja2, htmx 1.9, Godot 4.3 HTML5 export, sqlite, Fly.io.

**Spec:** `docs/superpowers/specs/2026-05-12-async-web-play-mvp-design.md`

---

## File Structure

```
foedus/
  web/
    __init__.py            # exports make_web_app
    app.py                 # FastAPI factory; lifespan hook starts deadline_worker
    config.py              # env-var-driven Settings (pydantic-settings)
    db.py                  # sqlalchemy engine + session factory
    models.py              # ORM: User, Game, GameSeat, ChatMessage, Session
    session_store.py       # SqliteSessionStore (adapter from GameSession ↔ DB)
    auth.py                # GitHub OAuth + session cookie middleware
    jwt_helper.py          # mint/verify short-lived JWTs for the SPA
    driver.py              # advance_phase, substitute_hold_orders, run_bot_turns
    locks.py               # per-game asyncio.Lock registry
    deadline_worker.py     # asyncio background task
    notify.py              # Discord webhook poster (stub-friendly)
    coop_coep.py           # middleware to attach COOP/COEP per-route
    routes/
      __init__.py
      pages.py             # Jinja-rendered launcher pages
      api.py               # JSON API wrapper (cookie-or-JWT auth)
      game_view.py         # GET /games/{gid} (SPA loader page)
    templates/
      base.html
      login.html
      games_list.html
      games_new.html
      game_spa.html        # 30-line page that boots Godot
    static/
      css/main.css         # one file, mobile-first
      htmx.min.js          # vendored
      godot/               # built artifact (gitignored; built in CI)
migrations/
  alembic.ini
  env.py
  versions/
    0001_initial.py
tests/web/
  conftest.py              # temp-sqlite fixture, fake-GitHub fixture
  test_db_roundtrip.py
  test_session_store.py
  test_auth.py
  test_jwt_helper.py
  test_driver.py
  test_deadline_worker.py
  test_notify.py
  test_routes_pages.py
  test_routes_api.py
  test_full_turn_e2e.py
Dockerfile.web
fly.toml
.github/workflows/deploy.yml
```

---

# Phase 0: foedus-godot Mobile Spike (decision gate)

### Task 0.1: Build foedus-godot HTML5 export and walk through on phone viewport

**Files:**
- Create: `/home/david/foedus-godot/export_presets.cfg` (or modify if exists)
- Create: `/tmp/foedus-eval/notes.md` (spike report)
- Create: `scripts/spike_local_serve.py` (throwaway COOP/COEP server)

This is a spike, not TDD code. Skip the test-first rhythm; produce evidence.

- [ ] **Step 1: Install Godot 4.3 export templates**

```bash
cd /tmp
curl -L -o godot_templates.tpz \
  https://github.com/godotengine/godot/releases/download/4.3-stable/Godot_v4.3-stable_export_templates.tpz
mkdir -p ~/.local/share/godot/export_templates/4.3.stable
cd ~/.local/share/godot/export_templates/4.3.stable
unzip -o /tmp/godot_templates.tpz
mv templates/* . && rmdir templates
ls web*.zip
```
Expected: `web_debug.zip web_dlink_debug.zip web_dlink_release.zip web_release.zip` listed.

- [ ] **Step 2: Add a Web export preset to foedus-godot**

Append to `/home/david/foedus-godot/export_presets.cfg`:

```ini
[preset.0]
name="Web"
platform="Web"
runnable=true
custom_features=""
export_filter="all_resources"
export_path="/tmp/foedus-godot-web/index.html"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
encrypt_directory=false

[preset.0.options]
custom_template/debug=""
custom_template/release=""
variant/extensions_support=false
variant/thread_support=true
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
html/export_icon=true
html/custom_html_shell=""
html/head_include=""
html/canvas_resize_policy=2
html/focus_canvas_on_start=true
html/experimental_virtual_keyboard=true
progressive_web_app/enabled=false
progressive_web_app/ensure_cross_origin_isolation_headers=true
```

- [ ] **Step 3: Run the export**

```bash
mkdir -p /tmp/foedus-godot-web
godot --headless --path /home/david/foedus-godot --export-release "Web" /tmp/foedus-godot-web/index.html
ls -la /tmp/foedus-godot-web/
du -sh /tmp/foedus-godot-web/
du -ah /tmp/foedus-godot-web/ | sort -h | tail -5
```
Expected: `index.html`, `index.js`, `index.wasm`, `index.pck`, `index.audio.worklet.js`, plus icons. Total size on disk (uncompressed) is what we report; transfer size after brotli is roughly 25–40% of that.

- [ ] **Step 4: Create the throwaway COOP/COEP static server**

Write `scripts/spike_local_serve.py`:

```python
"""One-off static server for the Phase 0 spike: serves files with the
COOP/COEP headers Godot 4 HTML5 needs for SharedArrayBuffer."""
from __future__ import annotations
import argparse, http.server, socketserver
from pathlib import Path

class COOPHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/foedus-godot-web")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    import os; os.chdir(args.dir)
    with socketserver.TCPServer(("0.0.0.0", args.port), COOPHandler) as httpd:
        print(f"serving {args.dir} at http://0.0.0.0:{args.port}")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Start the foedus play-server with a fresh 4-seat game**

In one terminal:

```bash
cd /home/david/foedus
pip install -e .[remote]
python -m foedus.game_server.server --port 8765 &
# create a game (2 humans + 2 HeuristicAgent bots)
curl -X POST http://localhost:8765/games -H 'Content-Type: application/json' -d '{
  "config": {"num_players": 4, "max_turns": 5, "seed": 42, "archetype": "CONTINENTAL_SWEEP"},
  "seats": [
    {"type":"human","name":"david"},
    {"type":"human","name":"dbyrne"},
    {"type":"agent","name":"botA","kind":"foedus.agents.heuristic.HeuristicAgent"},
    {"type":"agent","name":"botB","kind":"foedus.agents.heuristic.HeuristicAgent"}
  ]
}' | tee /tmp/foedus-eval/game.json
```
Record `game_id` from the response.

In another terminal:

```bash
python /home/david/foedus/scripts/spike_local_serve.py &
```

- [ ] **Step 6: Walk through the game on a phone viewport**

Use the Playwright MCP tools:

```
browser_resize width=412 height=915
browser_navigate http://localhost:8080/?gid=<game_id>&player=0&api=http://localhost:8765
browser_wait_for time=20
browser_snapshot
browser_take_screenshot filename=/tmp/foedus-eval/01-load.png
browser_console_messages
```

Tap through one full round:
- negotiation phase: tap the chat field, type a message, press send
- intents phase: set at least one stance/intent
- press "Done with negotiation"
- enter an order on the map (tap source node, tap target node)
- press "Commit orders"
- wait for resolution
- screenshot at each step into `/tmp/foedus-eval/NN-step.png`

- [ ] **Step 7: Write the spike report**

Write `/tmp/foedus-eval/notes.md`:

```markdown
# foedus-godot mobile spike report — <date>

## Bundle size
- Uncompressed total: <du -sh output>
- Top 5 files: <du -ah | tail -5 output>
- Estimated brotli transfer: <0.3 * uncompressed>

## Cold start
- browser_navigate → first interactive: <seconds>

## Walkthrough
- Tap nodes: <works / janky / broken — describe>
- Pinch-zoom / pan: <works / not implemented / broken>
- Chat keyboard: <opens / focus-traps / dismisses on send>
- Console errors: <none / list them>

## Decision gate result
- [ ] PASS — proceed pure-Godot
- [ ] PASS with caveats — log Godot-side tasks, proceed
- [ ] FAIL — revert to hybrid (htmx chat + Godot map embed)

## Caveats / follow-ups for the plan
- ...
```

- [ ] **Step 8: Commit the spike artifacts**

```bash
cd /home/david/foedus
git add scripts/spike_local_serve.py
git commit -m "spike: local COOP/COEP server for Phase 0 mobile walkthrough"
cd /home/david/foedus-godot
git add export_presets.cfg
git commit -m "build: add Web HTML5 export preset"
```

**Decision gate:** if the spike report says FAIL, STOP. Revisit the frontend decision with the user before continuing — the rest of this plan assumes pure-Godot. If PASS or PASS-with-caveats, append caveats to a new "Phase 9 follow-ups" section at the end of this plan, then continue to Phase 1.

---

# Phase 1: Project scaffolding + database

### Task 1.1: Declare the `web` extra and create the package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `foedus/web/__init__.py`
- Create: `foedus/web/config.py`

- [ ] **Step 1: Add the `web` optional-dependency to pyproject.toml**

Replace the `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "openskill>=6.0", "fastapi>=0.110", "uvicorn[standard]>=0.30", "httpx>=0.27", "sqlalchemy>=2.0", "alembic>=1.13", "authlib>=1.3", "itsdangerous>=2.2", "pyjwt>=2.8", "pydantic-settings>=2.2", "jinja2>=3.1", "pytest-asyncio>=0.23"]
rating = ["openskill>=6.0"]
remote = ["fastapi>=0.110", "uvicorn[standard]>=0.30", "httpx>=0.27"]
web = ["fastapi>=0.110", "uvicorn[standard]>=0.30", "httpx>=0.27", "sqlalchemy>=2.0", "alembic>=1.13", "authlib>=1.3", "itsdangerous>=2.2", "pyjwt>=2.8", "pydantic-settings>=2.2", "jinja2>=3.1"]
```

- [ ] **Step 2: Install the new deps**

```bash
pip install -e .[dev]
```
Expected: clean install, no resolver errors.

- [ ] **Step 3: Create the package init**

Write `foedus/web/__init__.py`:

```python
"""Async web-play MVP — FastAPI + sqlite over the foedus engine.

Optional dependency. Install with:
    pip install foedus[web]
"""
from __future__ import annotations

try:
    from foedus.web.app import make_web_app
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "foedus.web requires the [web] extra. "
        "Install with: pip install foedus[web]"
    ) from e

__all__ = ["make_web_app"]
```

- [ ] **Step 4: Create Settings**

Write `foedus/web/config.py`:

```python
"""Env-driven configuration for foedus.web."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOEDUS_", env_file=".env",
                                      extra="ignore")

    database_url: str = "sqlite:///./foedus_web.db"
    session_secret: str = "dev-only-change-me"
    jwt_secret: str = "dev-only-change-me-jwt"
    jwt_ttl_seconds: int = 3600
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    base_url: str = "http://localhost:8000"   # external URL, used for OAuth callback
    deadline_tick_seconds: int = 60

def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml foedus/web/__init__.py foedus/web/config.py
git commit -m "feat(web): package skeleton + Settings"
```

---

### Task 1.2: SQLAlchemy engine + session factory

**Files:**
- Create: `foedus/web/db.py`
- Create: `tests/web/__init__.py` (empty)
- Create: `tests/web/conftest.py`
- Create: `tests/web/test_db.py`

- [ ] **Step 1: Write the failing test**

Write `tests/web/__init__.py` (empty file).

Write `tests/web/conftest.py`:

```python
from __future__ import annotations
import pytest
from pathlib import Path
from foedus.web.config import Settings
from foedus.web.db import make_engine, make_session_factory, Base

@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path}/test.db",
                    session_secret="test", jwt_secret="test-jwt")

@pytest.fixture
def db(settings: Settings):
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)
    yield SessionLocal
    Base.metadata.drop_all(engine)
    engine.dispose()
```

Write `tests/web/test_db.py`:

```python
from sqlalchemy import text

def test_engine_can_execute(db):
    with db() as s:
        result = s.execute(text("SELECT 1")).scalar()
        assert result == 1
```

- [ ] **Step 2: Run the test, expect failure**

```bash
pytest tests/web/test_db.py -v
```
Expected: FAIL — `foedus.web.db` doesn't exist.

- [ ] **Step 3: Implement db.py**

Write `foedus/web/db.py`:

```python
"""SQLAlchemy engine + session factory + Declarative Base."""
from __future__ import annotations
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Base(DeclarativeBase):
    pass

def make_engine(database_url: str) -> Engine:
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args, future=True)

def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
```

- [ ] **Step 4: Run the test, expect pass**

```bash
pytest tests/web/test_db.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/db.py tests/web/__init__.py tests/web/conftest.py tests/web/test_db.py
git commit -m "feat(web): sqlalchemy engine + session factory"
```

---

### Task 1.3: ORM models for User, Game, GameSeat, ChatMessage, Session

**Files:**
- Create: `foedus/web/models.py`
- Create: `tests/web/test_models.py`

- [ ] **Step 1: Write the failing test**

Write `tests/web/test_models.py`:

```python
from __future__ import annotations
from datetime import datetime, timedelta
from foedus.web.models import User, Game, GameSeat, ChatMessage, SessionRow

def test_create_user_and_game_with_seats(db):
    with db() as s:
        u = User(github_id=42, github_login="alice")
        s.add(u)
        s.flush()
        g = Game(id="g-1", created_by=u.id, status="pending",
                 map_seed=1, map_preset="CONTINENTAL_SWEEP",
                 max_turns=7, phase_deadline_hours=24,
                 state_json="{}")
        s.add(g)
        s.flush()
        s.add_all([
            GameSeat(game_id="g-1", player_idx=0, kind="human", user_id=u.id),
            GameSeat(game_id="g-1", player_idx=1, kind="bot",
                     bot_class="foedus.agents.heuristic.HeuristicAgent"),
        ])
        s.commit()

    with db() as s:
        g = s.get(Game, "g-1")
        assert g.status == "pending"
        seats = sorted(g.seats, key=lambda x: x.player_idx)
        assert len(seats) == 2
        assert seats[0].kind == "human"
        assert seats[1].bot_class.endswith("HeuristicAgent")

def test_chat_message_roundtrip(db):
    with db() as s:
        u = User(github_id=1, github_login="x"); s.add(u)
        s.add(Game(id="g-2", created_by=1, status="active", map_seed=0,
                   map_preset="P", max_turns=5, state_json="{}"))
        s.flush()
        s.add(ChatMessage(game_id="g-2", turn=0, sender_idx=0,
                          recipients_mask=-1, body="hi"))
        s.commit()
    with db() as s:
        rows = s.query(ChatMessage).all()
        assert len(rows) == 1 and rows[0].body == "hi"

def test_session_row_expiry(db):
    with db() as s:
        u = User(github_id=9, github_login="z"); s.add(u); s.flush()
        s.add(SessionRow(token="abc", user_id=u.id,
                         expires_at=datetime.utcnow() + timedelta(days=7)))
        s.commit()
    with db() as s:
        sr = s.get(SessionRow, "abc")
        assert sr.user_id is not None
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_models.py -v
```
Expected: FAIL — `foedus.web.models` doesn't exist.

- [ ] **Step 3: Implement models.py**

Write `foedus/web/models.py`:

```python
"""ORM models for foedus.web.

Naming note: avoid `Session` collision with sqlalchemy's Session — the
auth-session table is `SessionRow`.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Text, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from foedus.web.db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    github_login: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Game(Base):
    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # pending|active|finished
    map_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    map_preset: Mapped[str] = mapped_column(String(64), nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_deadline_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_phase_deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    discord_webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    seats: Mapped[list["GameSeat"]] = relationship(back_populates="game",
                                                   cascade="all, delete-orphan")
    chats: Mapped[list["ChatMessage"]] = relationship(back_populates="game",
                                                     cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_games_status_deadline", "status", "current_phase_deadline_at"),
    )

class GameSeat(Base):
    __tablename__ = "game_seats"
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    player_idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # human|bot
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    bot_class: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    game: Mapped[Game] = relationship(back_populates="seats")

    __table_args__ = (
        Index("ix_game_seats_user", "user_id"),
    )

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    recipients_mask: Mapped[int] = mapped_column(Integer, nullable=False)  # -1 = broadcast
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    game: Mapped[Game] = relationship(back_populates="chats")

class SessionRow(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_models.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/models.py tests/web/test_models.py
git commit -m "feat(web): ORM models for users/games/seats/chat/sessions"
```

---

### Task 1.4: Alembic baseline migration

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/0001_initial.py`

- [ ] **Step 1: Initialize alembic config**

Write `alembic.ini`:

```ini
[alembic]
script_location = migrations
sqlalchemy.url = sqlite:///./foedus_web.db

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

Write `migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Write `migrations/env.py`:

```python
from __future__ import annotations
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from foedus.web.db import Base
from foedus.web import models  # noqa: F401  -- register models
from foedus.web.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True)  # batch for sqlite ALTER
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 2: Generate the initial migration**

```bash
mkdir -p migrations/versions
alembic revision --autogenerate -m "initial"
ls migrations/versions/
```
Expected: a file like `migrations/versions/<hash>_initial.py`. Rename to `0001_initial.py` and edit the `revision = ...` line to `revision = "0001"`.

- [ ] **Step 3: Verify the migration applies**

```bash
rm -f foedus_web.db
alembic upgrade head
sqlite3 foedus_web.db ".schema"
```
Expected: shows tables `users`, `games`, `game_seats`, `chat_messages`, `sessions`, plus indexes.

- [ ] **Step 4: Commit**

```bash
git add alembic.ini migrations/
git commit -m "feat(web): alembic baseline migration"
```

---

# Phase 2: Session store (GameState ↔ DB)

### Task 2.1: Refactor `make_app` to accept a session store

**Files:**
- Modify: `foedus/game_server/server.py` (small surgical change)
- Modify: `tests/test_game_server.py` (verify backward compat)

The existing `make_app()` captures `sessions: dict[str, GameSession]` in a closure. We need it to optionally accept an external store so foedus.web can substitute a sqlite-backed one. Default behaviour (in-memory dict) must be preserved.

- [ ] **Step 1: Write the compat test**

Add to `tests/test_game_server.py` (if file doesn't exist, create it):

```python
from foedus.game_server import make_app

def test_make_app_accepts_external_store():
    store: dict = {}
    app = make_app(sessions=store)
    # store is shared with the app
    assert hasattr(app, "title")

def test_make_app_default_in_memory_store():
    app = make_app()
    assert hasattr(app, "title")
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_game_server.py::test_make_app_accepts_external_store -v
```
Expected: FAIL with `TypeError: make_app() got an unexpected keyword argument 'sessions'`.

- [ ] **Step 3: Refactor make_app**

In `foedus/game_server/server.py`, change the function signature and remove the inline `sessions: dict = {}` line:

```python
def make_app(sessions: dict | None = None) -> FastAPI:
    app = FastAPI(title="foedus game server", version="0.1.0")
    if sessions is None:
        sessions = {}
    # ... rest of the function unchanged
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_game_server.py -v
pytest tests/ -x  # full suite still green
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add foedus/game_server/server.py tests/test_game_server.py
git commit -m "refactor(game_server): make_app accepts external sessions store"
```

---

### Task 2.2: SqliteSessionStore (load-on-access, save-on-mutate dict-like)

**Files:**
- Create: `foedus/web/session_store.py`
- Create: `tests/web/test_session_store.py`

- [ ] **Step 1: Write the failing test**

Write `tests/web/test_session_store.py`:

```python
from __future__ import annotations
import json
from foedus.core import GameConfig, initial_state
from foedus.mapgen import generate_map
from foedus.game_server.session import GameSession, SeatSpec, build_agent
from foedus.web.models import User, Game, GameSeat
from foedus.web.session_store import SqliteSessionStore

def _make_seed_game(db_session):
    u = User(github_id=1, github_login="alice"); db_session.add(u); db_session.flush()
    cfg = GameConfig(num_players=4, max_turns=5, seed=42,
                     archetype="CONTINENTAL_SWEEP")
    m = generate_map(4, seed=42, archetype="CONTINENTAL_SWEEP")
    state = initial_state(cfg, m)
    from foedus.remote.wire import serialize_state
    g = Game(id="g-test", created_by=u.id, status="active",
             map_seed=42, map_preset="CONTINENTAL_SWEEP",
             max_turns=5, state_json=json.dumps(serialize_state(state)))
    db_session.add(g)
    db_session.add_all([
        GameSeat(game_id="g-test", player_idx=0, kind="human", user_id=u.id),
        GameSeat(game_id="g-test", player_idx=1, kind="bot",
                 bot_class="foedus.agents.heuristic.HeuristicAgent"),
        GameSeat(game_id="g-test", player_idx=2, kind="bot",
                 bot_class="foedus.agents.heuristic.HeuristicAgent"),
        GameSeat(game_id="g-test", player_idx=3, kind="bot",
                 bot_class="foedus.agents.heuristic.HeuristicAgent"),
    ])
    db_session.commit()

def test_store_loads_game_from_db(db):
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    sess = store["g-test"]
    assert isinstance(sess, GameSession)
    assert sess.game_id == "g-test"
    assert len(sess.seats) == 4
    assert sess.seats[0].type == "human"
    assert sess.seats[1].type == "agent"

def test_store_missing_raises_keyerror(db):
    store = SqliteSessionStore(db)
    import pytest
    with pytest.raises(KeyError):
        store["nope"]

def test_store_save_roundtrip(db):
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    sess = store["g-test"]
    # mutate: advance state minimally — call init_round again is no-op,
    # but we can persist with no change and verify state_json still parses.
    store.save(sess)
    with db() as s:
        row = s.get(Game, "g-test")
        assert json.loads(row.state_json)["turn"] == 0
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_session_store.py -v
```
Expected: FAIL — module missing.

- [ ] **Step 3: Implement session_store.py**

Write `foedus/web/session_store.py`:

```python
"""Adapter between SQLAlchemy-persisted Game rows and in-memory GameSession.

Behaves like dict[str, GameSession] for game_server.make_app's needs:
- __getitem__(game_id) loads from DB, hydrates a GameSession
- __setitem__(game_id, sess) persists state_json
- __contains__ / __len__ supported
- save(sess) is the canonical mutation flush
"""
from __future__ import annotations
import json
from typing import Any
from foedus.game_server.session import GameSession, SeatSpec, build_agent
from foedus.remote.wire import serialize_state, deserialize_state
from foedus.web.models import Game, GameSeat

class SqliteSessionStore:
    def __init__(self, session_factory):
        self._sf = session_factory

    def __getitem__(self, game_id: str) -> GameSession:
        with self._sf() as s:
            g = s.get(Game, game_id)
            if g is None:
                raise KeyError(game_id)
            state = deserialize_state(json.loads(g.state_json))
            seats: dict[int, SeatSpec] = {}
            agents: dict[int, Any] = {}
            for row in g.seats:
                if row.kind == "human":
                    seats[row.player_idx] = SeatSpec(type="human",
                                                    name=f"u{row.user_id}")
                else:
                    spec = SeatSpec(type="agent", name=row.bot_class,
                                    kind=row.bot_class, args={})
                    seats[row.player_idx] = spec
                    agents[row.player_idx] = build_agent(spec)
        sess = GameSession(game_id=game_id, state=state, seats=seats,
                           agents=agents)
        return sess

    def __setitem__(self, game_id: str, sess: GameSession) -> None:
        self.save(sess)

    def __contains__(self, game_id: str) -> bool:
        with self._sf() as s:
            return s.get(Game, game_id) is not None

    def __len__(self) -> int:
        with self._sf() as s:
            return s.query(Game).count()

    def get(self, game_id: str, default=None):
        try:
            return self[game_id]
        except KeyError:
            return default

    def save(self, sess: GameSession) -> None:
        with self._sf() as s:
            g = s.get(Game, sess.game_id)
            if g is None:
                raise KeyError(sess.game_id)
            g.state_json = json.dumps(serialize_state(sess.state))
            s.commit()
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_session_store.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/session_store.py tests/web/test_session_store.py
git commit -m "feat(web): SqliteSessionStore hydrates GameSession from DB"
```

---

# Phase 3: Auth (GitHub OAuth + sessions + JWT)

### Task 3.1: JWT helper

**Files:**
- Create: `foedus/web/jwt_helper.py`
- Create: `tests/web/test_jwt_helper.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_jwt_helper.py
from __future__ import annotations
import time, pytest
from foedus.web.jwt_helper import mint_spa_token, verify_spa_token, ExpiredToken, InvalidToken

def test_roundtrip():
    tok = mint_spa_token(user_id=1, game_id="g-1", player_idx=2,
                         secret="s", ttl_seconds=60)
    claims = verify_spa_token(tok, secret="s")
    assert claims["user_id"] == 1
    assert claims["game_id"] == "g-1"
    assert claims["player_idx"] == 2

def test_expired_rejected():
    tok = mint_spa_token(user_id=1, game_id="g-1", player_idx=0,
                         secret="s", ttl_seconds=-1)
    with pytest.raises(ExpiredToken):
        verify_spa_token(tok, secret="s")

def test_wrong_secret_rejected():
    tok = mint_spa_token(user_id=1, game_id="g-1", player_idx=0,
                         secret="a", ttl_seconds=60)
    with pytest.raises(InvalidToken):
        verify_spa_token(tok, secret="b")
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_jwt_helper.py -v
```

- [ ] **Step 3: Implement jwt_helper.py**

```python
"""Short-lived JWTs for the Godot SPA bearer auth.

The SPA receives a token in the URL query string at load time and uses
it as `Authorization: Bearer <token>` on every API call. Tokens encode
(user_id, game_id, player_idx) and expire quickly.
"""
from __future__ import annotations
import time
import jwt

class InvalidToken(Exception): pass
class ExpiredToken(InvalidToken): pass

def mint_spa_token(user_id: int, game_id: str, player_idx: int,
                   secret: str, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = {"user_id": user_id, "game_id": game_id,
               "player_idx": player_idx,
               "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, secret, algorithm="HS256")

def verify_spa_token(token: str, secret: str) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise ExpiredToken(str(e)) from e
    except jwt.InvalidTokenError as e:
        raise InvalidToken(str(e)) from e
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_jwt_helper.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/jwt_helper.py tests/web/test_jwt_helper.py
git commit -m "feat(web): JWT helper for SPA bearer tokens"
```

---

### Task 3.2: GitHub OAuth + cookie session

**Files:**
- Create: `foedus/web/auth.py`
- Create: `tests/web/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_auth.py
from __future__ import annotations
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from foedus.web.auth import install_session_middleware, current_user, create_session
from foedus.web.models import User, SessionRow

def _make_app(settings, db):
    app = FastAPI()
    install_session_middleware(app, settings, db)

    @app.get("/whoami")
    def whoami(request: Request):
        u = current_user(request, db)
        return {"login": u.github_login if u else None}

    return app

def test_no_cookie_no_user(settings, db):
    client = TestClient(_make_app(settings, db))
    r = client.get("/whoami")
    assert r.status_code == 200
    assert r.json() == {"login": None}

def test_session_cookie_resolves_user(settings, db):
    with db() as s:
        u = User(github_id=99, github_login="bob"); s.add(u); s.flush()
        token = create_session(s, u.id, ttl_days=7)
        s.commit()
    client = TestClient(_make_app(settings, db))
    client.cookies.set("foedus_session", token)
    r = client.get("/whoami")
    assert r.status_code == 200
    assert r.json() == {"login": "bob"}

def test_expired_session_rejected(settings, db):
    with db() as s:
        u = User(github_id=100, github_login="carol"); s.add(u); s.flush()
        s.add(SessionRow(token="expired", user_id=u.id,
                         expires_at=datetime.utcnow() - timedelta(hours=1)))
        s.commit()
    client = TestClient(_make_app(settings, db))
    client.cookies.set("foedus_session", "expired")
    r = client.get("/whoami")
    assert r.json() == {"login": None}
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_auth.py -v
```

- [ ] **Step 3: Implement auth.py**

```python
"""GitHub OAuth + cookie-based sessions.

The session cookie value is an opaque random token; the (token → user_id)
mapping lives in the `sessions` table. We don't sign-only-cookie because
explicit DB rows make revocation trivial.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from foedus.web.models import User, SessionRow
from foedus.web.config import Settings

COOKIE_NAME = "foedus_session"
SESSION_TTL_DAYS = 14

_oauth: OAuth | None = None

def _get_oauth(settings: Settings) -> OAuth:
    global _oauth
    if _oauth is None:
        _oauth = OAuth()
        _oauth.register(
            name="github",
            client_id=settings.github_oauth_client_id,
            client_secret=settings.github_oauth_client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user"},
        )
    return _oauth

def install_session_middleware(app: FastAPI, settings: Settings,
                               session_factory) -> None:
    # SessionMiddleware is used only to support authlib's state-cookie
    # for OAuth (not for our user session — that's our own cookie).
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret,
                       same_site="lax")
    oauth = _get_oauth(settings)

    @app.get("/auth/github/login")
    async def login(request: Request):
        redirect_uri = settings.base_url.rstrip("/") + "/auth/github/callback"
        return await oauth.github.authorize_redirect(request, redirect_uri)

    @app.get("/auth/github/callback")
    async def callback(request: Request):
        token = await oauth.github.authorize_access_token(request)
        resp = await oauth.github.get("user", token=token)
        gh = resp.json()
        with session_factory() as s:
            existing = s.query(User).filter_by(github_id=gh["id"]).first()
            if existing is None:
                existing = User(github_id=gh["id"], github_login=gh["login"])
                s.add(existing); s.flush()
            else:
                existing.github_login = gh["login"]
            sess_token = create_session(s, existing.id,
                                        ttl_days=SESSION_TTL_DAYS)
            s.commit()
        response = RedirectResponse(url="/games", status_code=302)
        response.set_cookie(COOKIE_NAME, sess_token, httponly=True,
                            samesite="lax", max_age=SESSION_TTL_DAYS * 86400)
        return response

    @app.post("/auth/logout")
    async def logout(request: Request):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            with session_factory() as s:
                row = s.get(SessionRow, token)
                if row is not None:
                    s.delete(row); s.commit()
        response = RedirectResponse(url="/login", status_code=302)
        response.delete_cookie(COOKIE_NAME)
        return response

def create_session(db, user_id: int, ttl_days: int = SESSION_TTL_DAYS) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessionRow(token=token, user_id=user_id,
                      expires_at=datetime.utcnow() + timedelta(days=ttl_days)))
    return token

def current_user(request: Request, session_factory) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with session_factory() as s:
        row = s.get(SessionRow, token)
        if row is None or row.expires_at < datetime.utcnow():
            return None
        return s.get(User, row.user_id)

def require_user(request: Request, session_factory) -> User:
    u = current_user(request, session_factory)
    if u is None:
        raise HTTPException(status_code=401, detail="login required")
    return u
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_auth.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/auth.py tests/web/test_auth.py
git commit -m "feat(web): GitHub OAuth + cookie sessions"
```

---

# Phase 4: Launcher pages (htmx + Jinja)

### Task 4.1: Base template, login, and games_list pages

**Files:**
- Create: `foedus/web/templates/base.html`
- Create: `foedus/web/templates/login.html`
- Create: `foedus/web/templates/games_list.html`
- Create: `foedus/web/static/css/main.css`
- Create: `foedus/web/routes/__init__.py` (empty)
- Create: `foedus/web/routes/pages.py`
- Create: `tests/web/test_routes_pages.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_routes_pages.py
from __future__ import annotations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from foedus.web.auth import install_session_middleware, create_session
from foedus.web.routes.pages import install_pages
from foedus.web.models import User, Game, GameSeat

def _client(settings, db):
    app = FastAPI()
    install_session_middleware(app, settings, db)
    install_pages(app, db)
    return TestClient(app)

def test_landing_redirects_to_login_when_anonymous(settings, db):
    r = _client(settings, db).get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"

def test_login_page_shows_github_button(settings, db):
    r = _client(settings, db).get("/login")
    assert r.status_code == 200
    assert "github" in r.text.lower()

def test_games_list_shows_user_games(settings, db):
    with db() as s:
        u = User(github_id=1, github_login="alice"); s.add(u); s.flush()
        s.add(Game(id="g-1", created_by=u.id, status="active",
                   map_seed=1, map_preset="P", max_turns=5, state_json="{}"))
        s.add(GameSeat(game_id="g-1", player_idx=0, kind="human", user_id=u.id))
        token = create_session(s, u.id)
        s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.get("/games")
    assert r.status_code == 200
    assert "g-1" in r.text
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_routes_pages.py -v
```

- [ ] **Step 3: Implement templates and routes**

Write `foedus/web/templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}foedus{% endblock %}</title>
<link rel="stylesheet" href="/static/css/main.css">
<script src="/static/htmx.min.js" defer></script>
</head>
<body>
<header><a href="/games">foedus</a>
  {% if user %}<form method="post" action="/auth/logout" style="display:inline">
    <span>{{ user.github_login }}</span>
    <button type="submit">log out</button></form>{% endif %}
</header>
<main>{% block body %}{% endblock %}</main>
</body></html>
```

Write `foedus/web/templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}Sign in — foedus{% endblock %}
{% block body %}
<h1>foedus</h1>
<p>Sign in with GitHub to play.</p>
<a class="btn" href="/auth/github/login">Sign in with GitHub</a>
{% endblock %}
```

Write `foedus/web/templates/games_list.html`:

```html
{% extends "base.html" %}
{% block title %}Your games — foedus{% endblock %}
{% block body %}
<h1>Your games</h1>
<p><a class="btn" href="/games/new">New game</a></p>
{% for bucket, label in [('active', 'Active'), ('pending', 'Pending'), ('finished', 'Finished')] %}
<section>
  <h2>{{ label }}</h2>
  {% if grouped.get(bucket) %}
  <ul>
    {% for g in grouped[bucket] %}
    <li><a href="/games/{{ g.id }}">{{ g.id }}</a>
        — turn {{ g.turn }} / {{ g.max_turns }}
        {% if g.deadline %}— deadline {{ g.deadline }}{% endif %}</li>
    {% endfor %}
  </ul>
  {% else %}<p>None.</p>{% endif %}
</section>
{% endfor %}
{% endblock %}
```

Write `foedus/web/static/css/main.css`:

```css
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;margin:0;padding:0;color:#111;background:#fafafa}
header{background:#1f3a5f;color:#fff;padding:0.6rem 1rem;display:flex;justify-content:space-between;align-items:center}
header a{color:#fff;text-decoration:none;font-weight:600}
main{padding:1rem;max-width:720px;margin:0 auto}
h1,h2{margin-top:0.5rem}
.btn{display:inline-block;padding:0.6rem 1rem;background:#1f6feb;color:#fff;text-decoration:none;border-radius:6px;border:0;cursor:pointer;font-size:1rem}
.btn:hover{background:#1158c7}
.btn-warning{background:#e0a210}
.btn-danger{background:#cf222e}
ul{padding-left:1.2rem}
section{margin-bottom:1.5rem}
form{display:flex;flex-direction:column;gap:0.6rem}
input,select,textarea{font-size:1rem;padding:0.5rem;border:1px solid #ccc;border-radius:4px}
label{font-weight:600;font-size:0.9rem}
.row{display:flex;gap:0.6rem;align-items:center}
```

Write `foedus/web/routes/__init__.py` (empty file).

Write `foedus/web/routes/pages.py`:

```python
"""Launcher pages (htmx + Jinja)."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from foedus.web.auth import current_user
from foedus.web.models import Game, GameSeat

WEB_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

def install_pages(app: FastAPI, session_factory) -> None:
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")),
              name="static")

    @app.get("/")
    def landing(request: Request):
        u = current_user(request, session_factory)
        if u is None:
            return RedirectResponse("/login", status_code=302)
        return RedirectResponse("/games", status_code=302)

    @app.get("/login", response_class=HTMLResponse)
    def login(request: Request):
        return templates.TemplateResponse("login.html",
                                          {"request": request, "user": None})

    @app.get("/games", response_class=HTMLResponse)
    def games_list(request: Request):
        u = current_user(request, session_factory)
        if u is None:
            return RedirectResponse("/login", status_code=302)
        with session_factory() as s:
            rows = (s.query(Game).join(GameSeat,
                    (GameSeat.game_id == Game.id) & (GameSeat.user_id == u.id))
                    .order_by(Game.created_at.desc()).all())
            grouped: dict[str, list[dict]] = defaultdict(list)
            for g in rows:
                try:
                    turn = json.loads(g.state_json).get("turn", 0)
                except Exception:
                    turn = 0
                grouped[g.status].append({"id": g.id, "turn": turn,
                                          "max_turns": g.max_turns,
                                          "deadline": g.current_phase_deadline_at})
        return templates.TemplateResponse("games_list.html", {
            "request": request, "user": u, "grouped": dict(grouped)})
```

- [ ] **Step 4: Vendor htmx**

```bash
mkdir -p foedus/web/static
curl -o foedus/web/static/htmx.min.js https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js
```

- [ ] **Step 5: Run, expect pass**

```bash
pytest tests/web/test_routes_pages.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add foedus/web/templates/ foedus/web/static/ foedus/web/routes/ tests/web/test_routes_pages.py
git commit -m "feat(web): base/login/games-list templates + launcher pages"
```

---

### Task 4.2: Game creation form + POST handler

**Files:**
- Create: `foedus/web/templates/games_new.html`
- Modify: `foedus/web/routes/pages.py`
- Modify: `tests/web/test_routes_pages.py` (add test)

- [ ] **Step 1: Write the failing test**

Append to `tests/web/test_routes_pages.py`:

```python
def test_games_new_form_renders(settings, db):
    with db() as s:
        u = User(github_id=2, github_login="alice"); s.add(u); s.flush()
        token = create_session(s, u.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.get("/games/new")
    assert r.status_code == 200
    assert "max_turns" in r.text

def test_games_post_creates_game(settings, db):
    with db() as s:
        u = User(github_id=3, github_login="alice"); s.add(u); s.flush()
        token = create_session(s, u.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    payload = {
        "map_preset": "CONTINENTAL_SWEEP",
        "max_turns": "5",
        "phase_deadline_hours": "24",
        "discord_webhook_url": "",
        "seat_0_kind": "human", "seat_0_user": "alice",
        "seat_1_kind": "bot", "seat_1_bot": "foedus.agents.heuristic.HeuristicAgent",
        "seat_2_kind": "bot", "seat_2_bot": "foedus.agents.heuristic.HeuristicAgent",
        "seat_3_kind": "bot", "seat_3_bot": "foedus.agents.heuristic.HeuristicAgent",
    }
    r = c.post("/games", data=payload, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/games/")
    with db() as s:
        assert s.query(Game).count() == 1
        assert s.query(GameSeat).count() == 4
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_routes_pages.py::test_games_new_form_renders -v
```

- [ ] **Step 3: Implement template and handlers**

Write `foedus/web/templates/games_new.html`:

```html
{% extends "base.html" %}
{% block title %}New game — foedus{% endblock %}
{% block body %}
<h1>New game</h1>
<form method="post" action="/games">
  <label>Map preset
    <select name="map_preset">
      <option value="CONTINENTAL_SWEEP" selected>Continental Sweep</option>
    </select></label>
  <label>Max turns
    <select name="max_turns">
      <option value="5">5</option><option value="7" selected>7</option>
      <option value="10">10</option><option value="15">15</option>
    </select></label>
  <label>Phase deadline
    <select name="phase_deadline_hours">
      <option value="">No limit</option>
      <option value="12">12 hours</option>
      <option value="24" selected>24 hours</option>
      <option value="48">48 hours</option>
      <option value="72">72 hours</option>
    </select></label>
  <label>Discord webhook URL (optional)
    <input type="url" name="discord_webhook_url" placeholder="https://discord.com/api/webhooks/...">
  </label>
  <h2>Seats</h2>
  {% for i in range(4) %}
  <fieldset>
    <legend>Seat {{ i }}</legend>
    <label>Type
      <select name="seat_{{ i }}_kind">
        <option value="human">Human</option>
        <option value="bot" {% if i > 0 %}selected{% endif %}>Bot</option>
      </select></label>
    <label>GitHub username (if human)
      <input name="seat_{{ i }}_user" {% if i == 0 %}value="{{ user.github_login }}"{% endif %}>
    </label>
    <label>Bot class (if bot)
      <select name="seat_{{ i }}_bot">
        <option value="foedus.agents.heuristic.HeuristicAgent" selected>HeuristicAgent</option>
        <option value="foedus.agents.heuristic.HoldAgent">HoldAgent</option>
      </select></label>
  </fieldset>
  {% endfor %}
  <button class="btn" type="submit">Create</button>
</form>
{% endblock %}
```

Append to `foedus/web/routes/pages.py` (inside `install_pages`):

```python
    @app.get("/games/new", response_class=HTMLResponse)
    def games_new(request: Request):
        u = current_user(request, session_factory)
        if u is None:
            return RedirectResponse("/login", status_code=302)
        return templates.TemplateResponse("games_new.html",
                                          {"request": request, "user": u})

    @app.post("/games")
    async def games_create(request: Request):
        u = current_user(request, session_factory)
        if u is None:
            return RedirectResponse("/login", status_code=302)
        form = await request.form()
        from foedus.web.driver import create_new_game
        gid = create_new_game(session_factory, creator=u, form=dict(form))
        return RedirectResponse(f"/games/{gid}", status_code=302)
```

We'll implement `create_new_game` in Task 6.1. For this test to pass NOW, write a minimal stub:

Write `foedus/web/driver.py` (initial stub; expanded in Task 6.1):

```python
"""Game lifecycle helpers: create, advance phases, substitute hold orders.

Expanded in Phase 6. Stubbed here to satisfy create-game route tests.
"""
from __future__ import annotations
import json, secrets, string
from datetime import datetime, timedelta
from foedus.core import GameConfig, initial_state
from foedus.mapgen import generate_map
from foedus.remote.wire import serialize_state
from foedus.web.models import User, Game, GameSeat

def _new_game_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "g-" + "".join(secrets.choice(alphabet) for _ in range(8))

def create_new_game(session_factory, creator: User, form: dict) -> str:
    map_preset = form.get("map_preset", "CONTINENTAL_SWEEP")
    max_turns = int(form.get("max_turns", "7"))
    dl_raw = form.get("phase_deadline_hours") or None
    deadline_hours = int(dl_raw) if dl_raw else None
    webhook = (form.get("discord_webhook_url") or "").strip() or None
    seed = secrets.randbits(31)
    cfg = GameConfig(num_players=4, max_turns=max_turns, seed=seed,
                     archetype=map_preset)
    m = generate_map(4, seed=seed, archetype=map_preset)
    state = initial_state(cfg, m)
    gid = _new_game_id()

    seats_rows: list[GameSeat] = []
    with session_factory() as s:
        for i in range(4):
            kind = form.get(f"seat_{i}_kind", "bot")
            if kind == "human":
                login = (form.get(f"seat_{i}_user") or "").strip()
                if not login:
                    raise ValueError(f"seat {i} is human but no GitHub login")
                u = s.query(User).filter_by(github_login=login).first()
                if u is None:
                    # auto-create stub; real user fills in github_id on first login
                    u = User(github_id=-abs(hash(login)) % (10**9),
                             github_login=login)
                    s.add(u); s.flush()
                seats_rows.append(GameSeat(game_id=gid, player_idx=i,
                                           kind="human", user_id=u.id))
            else:
                bot = form.get(f"seat_{i}_bot",
                               "foedus.agents.heuristic.HeuristicAgent")
                seats_rows.append(GameSeat(game_id=gid, player_idx=i,
                                           kind="bot", bot_class=bot))
        deadline_at = (datetime.utcnow() + timedelta(hours=deadline_hours)
                       if deadline_hours else None)
        g = Game(id=gid, created_by=creator.id, status="active",
                 map_seed=seed, map_preset=map_preset, max_turns=max_turns,
                 phase_deadline_hours=deadline_hours,
                 current_phase_deadline_at=deadline_at,
                 discord_webhook_url=webhook,
                 state_json=json.dumps(serialize_state(state)))
        s.add(g); s.flush()
        s.add_all(seats_rows); s.commit()
    return gid
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_routes_pages.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/templates/games_new.html foedus/web/routes/pages.py foedus/web/driver.py tests/web/test_routes_pages.py
git commit -m "feat(web): new-game form + create_new_game driver stub"
```

---

# Phase 5: JSON API + JWT bearer + game SPA loader

### Task 5.1: COOP/COEP middleware and SPA loader page

**Files:**
- Create: `foedus/web/coop_coep.py`
- Create: `foedus/web/templates/game_spa.html`
- Modify: `foedus/web/routes/pages.py` (add `/games/{gid}` route)
- Create: `tests/web/test_game_spa.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_game_spa.py
from __future__ import annotations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from foedus.web.auth import install_session_middleware, create_session
from foedus.web.routes.pages import install_pages
from foedus.web.models import User, Game, GameSeat

def _client(settings, db):
    app = FastAPI()
    install_session_middleware(app, settings, db)
    install_pages(app, db)
    return TestClient(app)

def test_game_spa_requires_seat(settings, db):
    with db() as s:
        owner = User(github_id=1, github_login="a"); s.add(owner)
        other = User(github_id=2, github_login="b"); s.add(other); s.flush()
        s.add(Game(id="g-spa", created_by=owner.id, status="active",
                   map_seed=1, map_preset="P", max_turns=5, state_json="{}"))
        s.add(GameSeat(game_id="g-spa", player_idx=0, kind="human", user_id=owner.id))
        token = create_session(s, other.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.get("/games/g-spa")
    assert r.status_code == 403

def test_game_spa_sets_coop_coep_and_includes_token(settings, db):
    with db() as s:
        u = User(github_id=3, github_login="alice"); s.add(u); s.flush()
        s.add(Game(id="g-spa2", created_by=u.id, status="active",
                   map_seed=1, map_preset="P", max_turns=5, state_json="{}"))
        s.add(GameSeat(game_id="g-spa2", player_idx=0, kind="human", user_id=u.id))
        token = create_session(s, u.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.get("/games/g-spa2")
    assert r.status_code == 200
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert r.headers["cross-origin-embedder-policy"] == "require-corp"
    # The boot script must inject the JWT into the Godot iframe URL
    assert "gid=g-spa2" in r.text
    assert "player_idx=0" in r.text
    assert "token=" in r.text
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_game_spa.py -v
```

- [ ] **Step 3: Implement the SPA loader**

Write `foedus/web/coop_coep.py`:

```python
"""Per-route COOP/COEP header attachment.

Applied to:
  - GET /games/{gid}        (the Godot SPA loader)
  - GET /static/godot/*     (the Godot assets)

NOT applied to:
  - /auth/github/callback   (would break the OAuth popup)
"""
from __future__ import annotations
from starlette.types import ASGIApp, Receive, Scope, Send

COOP = (b"cross-origin-opener-policy", b"same-origin")
COEP = (b"cross-origin-embedder-policy", b"require-corp")
CORP = (b"cross-origin-resource-policy", b"cross-origin")

def needs_isolation(path: str) -> bool:
    if path.startswith("/static/godot"):
        return True
    if path.startswith("/games/") and "/" not in path[len("/games/"):]:
        return True  # /games/{gid} but not /games/{gid}/something
    return False

class COOPCOEPMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if not needs_isolation(path):
            return await self.app(scope, receive, send)

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(COOP); headers.append(COEP); headers.append(CORP)
                message["headers"] = headers
            await send(message)
        await self.app(scope, receive, _send)
```

Write `foedus/web/templates/game_spa.html`:

```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>foedus — {{ game.id }}</title>
<style>html,body,iframe{margin:0;padding:0;border:0;width:100vw;height:100vh}
.bar{position:fixed;top:0;left:0;right:0;background:#1f3a5f;color:#fff;padding:4px 8px;font:14px system-ui;z-index:10}
.bar a{color:#fff;margin-right:8px}
iframe{margin-top:28px;height:calc(100vh - 28px)}</style>
</head><body>
<div class="bar"><a href="/games">← lobby</a> {{ game.id }} (you are P{{ player_idx }})</div>
<iframe src="/static/godot/index.html?gid={{ game.id }}&player_idx={{ player_idx }}&token={{ token }}&api={{ api_base }}"
        allow="cross-origin-isolated"></iframe>
</body></html>
```

Append to `foedus/web/routes/pages.py` (inside `install_pages`):

```python
    @app.get("/games/{gid}", response_class=HTMLResponse)
    def game_spa(request: Request, gid: str):
        from foedus.web.config import get_settings
        from foedus.web.jwt_helper import mint_spa_token
        u = current_user(request, session_factory)
        if u is None:
            return RedirectResponse("/login", status_code=302)
        with session_factory() as s:
            g = s.get(Game, gid)
            if g is None:
                return HTMLResponse("not found", status_code=404)
            my_seat = (s.query(GameSeat).filter_by(game_id=gid, user_id=u.id)
                       .first())
            if my_seat is None:
                return HTMLResponse("forbidden", status_code=403)
            settings = get_settings()
            token = mint_spa_token(user_id=u.id, game_id=gid,
                                   player_idx=my_seat.player_idx,
                                   secret=settings.jwt_secret,
                                   ttl_seconds=settings.jwt_ttl_seconds)
            return templates.TemplateResponse("game_spa.html", {
                "request": request, "user": u,
                "game": g, "player_idx": my_seat.player_idx,
                "token": token,
                "api_base": settings.base_url.rstrip("/") + "/api/v1",
            })
```

Add COOP/COEP middleware to the page tests by updating `_client` in `test_routes_pages.py` and `test_game_spa.py` to install it:

Update both `_client` functions in those test files to add:

```python
    from foedus.web.coop_coep import COOPCOEPMiddleware
    app.add_middleware(COOPCOEPMiddleware)
```

After `install_session_middleware(...)` and before `install_pages(...)`.

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_game_spa.py tests/web/test_routes_pages.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/coop_coep.py foedus/web/templates/game_spa.html foedus/web/routes/pages.py tests/web/test_game_spa.py tests/web/test_routes_pages.py
git commit -m "feat(web): SPA loader page + COOP/COEP middleware"
```

---

### Task 5.2: JSON API mount with cookie-or-JWT auth wrapper

**Files:**
- Create: `foedus/web/routes/api.py`
- Create: `tests/web/test_routes_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_routes_api.py
from __future__ import annotations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from foedus.web.auth import install_session_middleware, create_session
from foedus.web.routes.api import install_api
from foedus.web.session_store import SqliteSessionStore
from foedus.web.jwt_helper import mint_spa_token
from foedus.web.models import User, Game, GameSeat
from tests.web.test_session_store import _make_seed_game

def _client(settings, db):
    app = FastAPI()
    install_session_middleware(app, settings, db)
    store = SqliteSessionStore(db)
    install_api(app, db, store, settings)
    return TestClient(app)

def test_api_state_with_cookie(settings, db):
    with db() as s:
        _make_seed_game(s)
        u = s.query(User).first()
        token = create_session(s, u.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.get("/api/v1/games/g-test/view/0")
    assert r.status_code == 200

def test_api_state_with_jwt(settings, db):
    with db() as s:
        _make_seed_game(s)
        u = s.query(User).first()
        s.commit()
        uid = u.id
    tok = mint_spa_token(user_id=uid, game_id="g-test", player_idx=0,
                         secret=settings.jwt_secret, ttl_seconds=60)
    c = _client(settings, db)
    r = c.get("/api/v1/games/g-test/view/0",
              headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200

def test_api_state_without_auth_rejected(settings, db):
    with db() as s:
        _make_seed_game(s); s.commit()
    c = _client(settings, db)
    r = c.get("/api/v1/games/g-test/view/0")
    assert r.status_code == 401

def test_api_seat_mismatch_rejected(settings, db):
    """JWT for player_idx=0 cannot read player_idx=1's view."""
    with db() as s:
        _make_seed_game(s)
        u = s.query(User).first(); s.commit()
        uid = u.id
    tok = mint_spa_token(user_id=uid, game_id="g-test", player_idx=0,
                         secret=settings.jwt_secret, ttl_seconds=60)
    c = _client(settings, db)
    r = c.get("/api/v1/games/g-test/view/1",
              headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_routes_api.py -v
```

- [ ] **Step 3: Implement api.py**

```python
"""JSON API: mount the existing foedus.game_server endpoints under
/api/v1, but front them with our cookie-or-JWT auth wrapper.

For the MVP, this implementation route-handles the subset of game_server
endpoints the SPA actually calls. We do NOT reuse make_app() because its
closure-captured sessions dict + no auth makes wrapping awkward.
"""
from __future__ import annotations
import json
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from foedus.web.auth import current_user
from foedus.web.config import Settings
from foedus.web.jwt_helper import verify_spa_token, InvalidToken
from foedus.web.models import GameSeat
from foedus.web.session_store import SqliteSessionStore

def _resolve_player(request: Request, session_factory, settings: Settings,
                    game_id: str) -> tuple[int, int]:
    """Return (user_id, player_idx) for an authenticated caller; 401/403
    on failure. Tries Authorization: Bearer first, then session cookie."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        tok = auth.split(None, 1)[1]
        try:
            claims = verify_spa_token(tok, secret=settings.jwt_secret)
        except InvalidToken:
            raise HTTPException(401, "bad token")
        if claims["game_id"] != game_id:
            raise HTTPException(403, "token does not match game")
        return int(claims["user_id"]), int(claims["player_idx"])
    u = current_user(request, session_factory)
    if u is None:
        raise HTTPException(401, "login required")
    with session_factory() as s:
        seat = s.query(GameSeat).filter_by(game_id=game_id, user_id=u.id).first()
        if seat is None:
            raise HTTPException(403, "not a seat in this game")
        return u.id, seat.player_idx

def install_api(app: FastAPI, session_factory,
                store: SqliteSessionStore, settings: Settings) -> None:

    @app.get("/api/v1/games/{game_id}/view/{player}")
    def view(game_id: str, player: int, request: Request):
        uid, pidx = _resolve_player(request, session_factory, settings, game_id)
        if pidx != player:
            raise HTTPException(403, "seat mismatch")
        try:
            sess = store[game_id]
        except KeyError:
            raise HTTPException(404, "game not found")
        from foedus.remote.wire import serialize_state
        from foedus.fog import visible_state_for
        visible = visible_state_for(sess.state, pidx)
        return JSONResponse(serialize_state(visible))

    @app.post("/api/v1/games/{game_id}/chat")
    async def chat(game_id: str, request: Request):
        uid, pidx = _resolve_player(request, session_factory, settings, game_id)
        body = await request.json()
        from foedus.web.driver import handle_chat
        return JSONResponse(handle_chat(session_factory, store, game_id, pidx, body))

    @app.post("/api/v1/games/{game_id}/commit")
    async def commit(game_id: str, request: Request):
        uid, pidx = _resolve_player(request, session_factory, settings, game_id)
        body = await request.json()
        from foedus.web.driver import handle_commit
        return JSONResponse(handle_commit(session_factory, store, game_id, pidx, body))

    @app.post("/api/v1/games/{game_id}/orders")
    async def orders(game_id: str, request: Request):
        uid, pidx = _resolve_player(request, session_factory, settings, game_id)
        body = await request.json()
        from foedus.web.driver import handle_orders
        return JSONResponse(handle_orders(session_factory, store, game_id, pidx, body))
```

Stub the three handlers in `foedus/web/driver.py` (will be filled in Task 6.1):

```python
def handle_chat(session_factory, store, game_id, pidx, body):
    sess = store[game_id]
    # Bundle 6 chat endpoint behaviour: append message + advance if eligible.
    raise NotImplementedError  # filled in Task 6.1

def handle_commit(session_factory, store, game_id, pidx, body):
    raise NotImplementedError  # filled in Task 6.1

def handle_orders(session_factory, store, game_id, pidx, body):
    raise NotImplementedError  # filled in Task 6.1
```

- [ ] **Step 4: Run, expect 3 of 4 pass (auth tests pass; view test passes because we don't call into the stub for view)**

```bash
pytest tests/web/test_routes_api.py -v
```
Expected: `test_api_state_with_cookie`, `test_api_state_with_jwt`, `test_api_state_without_auth_rejected`, `test_api_seat_mismatch_rejected` all pass (view does not call the stubs).

- [ ] **Step 5: Commit**

```bash
git add foedus/web/routes/api.py foedus/web/driver.py tests/web/test_routes_api.py
git commit -m "feat(web): JSON API + cookie-or-JWT auth wrapper"
```

---

# Phase 6: Driver (phase advance) + concurrency

### Task 6.1: Per-game async lock + chat/commit/orders handlers

**Files:**
- Create: `foedus/web/locks.py`
- Modify: `foedus/web/driver.py` (fill the three handlers + add advance_phase)
- Create: `tests/web/test_driver.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_driver.py
from __future__ import annotations
import json
import pytest
from foedus.web.session_store import SqliteSessionStore
from foedus.web.driver import handle_chat, handle_commit, handle_orders
from foedus.web.models import ChatMessage
from tests.web.test_session_store import _make_seed_game

@pytest.mark.asyncio
async def test_chat_appends_message(db):
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    result = handle_chat(db, store, "g-test", player_idx=0,
                         body={"recipients": [], "body": "hello"})
    assert result["ok"] is True
    with db() as s:
        rows = s.query(ChatMessage).all()
        assert len(rows) == 1 and rows[0].body == "hello"

def test_commit_records_intents_for_player(db):
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    result = handle_commit(db, store, "g-test", player_idx=0,
                           body={"intents": [], "aid_spends": [], "done": True})
    assert "phase" in result

def test_orders_submission_persists(db):
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    # Submit a hold for every unit owned by player 0.
    sess = store["g-test"]
    units = [u for u in sess.state.units.values() if u.owner == 0]
    if not units:
        pytest.skip("player 0 has no units in this seed")
    body = {"orders": [{"unit_id": u.id, "kind": "hold"} for u in units]}
    result = handle_orders(db, store, "g-test", player_idx=0, body=body)
    assert result["ok"] is True
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_driver.py -v
```
Expected: FAIL — handlers raise NotImplementedError.

- [ ] **Step 3: Implement locks.py and fill the handlers**

Write `foedus/web/locks.py`:

```python
"""Per-game asyncio.Lock registry.

For sync handler code, also exposes a threading.Lock equivalent so the
deadline worker (asyncio task in the same loop) and FastAPI handlers
serialize through the same primitive.
"""
from __future__ import annotations
import asyncio
from collections import defaultdict

class GameLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def lock(self, game_id: str) -> asyncio.Lock:
        return self._locks[game_id]

# Module singleton — one process, one registry.
_locks = GameLocks()
def lock_for(game_id: str) -> asyncio.Lock:
    return _locks.lock(game_id)
```

Replace the three handler stubs in `foedus/web/driver.py` with implementations:

```python
from foedus.web.models import ChatMessage
from foedus.remote.wire import (
    serialize_state, deserialize_intent, deserialize_aid_spend,
    deserialize_order,
)

def handle_chat(session_factory, store, game_id: str, pidx: int,
                body: dict) -> dict:
    """Append a chat message. Body: {recipients: [int], body: str}."""
    sess = store[game_id]
    recipients = body.get("recipients") or []
    msg_body = (body.get("body") or "").strip()
    if not msg_body:
        return {"ok": False, "error": "empty body"}
    mask = -1 if not recipients else sum(1 << r for r in recipients)
    sess.record_chat_message(player=pidx, recipients=recipients, body=msg_body)
    with session_factory() as s:
        s.add(ChatMessage(game_id=game_id, turn=sess.state.turn,
                          sender_idx=pidx, recipients_mask=mask,
                          body=msg_body))
        s.commit()
    store.save(sess)
    return {"ok": True}

def handle_commit(session_factory, store, game_id: str, pidx: int,
                  body: dict) -> dict:
    """Set intents + aid spends and optionally signal done with negotiation."""
    sess = store[game_id]
    intents_raw = body.get("intents") or []
    spends_raw = body.get("aid_spends") or []
    done = bool(body.get("done", False))
    intents = [deserialize_intent(x) for x in intents_raw]
    spends = [deserialize_aid_spend(x) for x in spends_raw]
    sess.apply_press_update(pidx, intents, spends)
    if done:
        sess.signal_chat_done(pidx)
    advanced = _maybe_advance(sess)
    store.save(sess)
    return {"ok": True, "phase": sess.state.phase.name, "advanced": advanced}

def handle_orders(session_factory, store, game_id: str, pidx: int,
                  body: dict) -> dict:
    """Submit orders for the player. Body: {orders: [...]}."""
    sess = store[game_id]
    orders_raw = body.get("orders") or []
    orders_by_unit = {}
    for o in orders_raw:
        order = deserialize_order(o)
        orders_by_unit[order.unit_id] = order
    sess.submit_orders(pidx, orders_by_unit)
    advanced = _maybe_advance(sess)
    store.save(sess)
    return {"ok": True, "phase": sess.state.phase.name, "advanced": advanced}

def _maybe_advance(sess) -> bool:
    """If both chat-phase-complete and all orders submitted, finalize the
    round. Bot orders are pre-computed at init_round time. Returns True
    if the round advanced."""
    from foedus.core import Phase
    advanced_any = False
    while True:
        if sess.state.phase == Phase.NEGOTIATION:
            if not sess.is_chat_phase_complete():
                return advanced_any
            # Move to orders phase implicitly via the engine's submit_orders
            # path; bots' orders are already in pending_orders.
            return advanced_any
        elif sess.state.phase == Phase.ORDERS:
            if not sess.all_orders_submitted():
                return advanced_any
            sess.advance()  # finalize_round
            advanced_any = True
            if sess.state.is_terminal():
                return advanced_any
            sess.init_round()
        else:
            return advanced_any
```

Note: depending on the GameSession API surface (Bundle 6), the exact method names may differ slightly. Verify against `foedus/game_server/session.py` and adjust. If `is_chat_phase_complete` / `all_orders_submitted` / `record_chat_message` are not present with those exact names, look for the equivalent (e.g. `state.is_chat_phase_complete` lives on the GameState in Bundle 6).

- [ ] **Step 4: Install pytest-asyncio mode**

Add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
```

- [ ] **Step 5: Run, expect pass**

```bash
pytest tests/web/test_driver.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add foedus/web/locks.py foedus/web/driver.py pyproject.toml tests/web/test_driver.py
git commit -m "feat(web): per-game locks + chat/commit/orders handlers"
```

---

### Task 6.2: Wire locks into the API routes

**Files:**
- Modify: `foedus/web/routes/api.py`

- [ ] **Step 1: Modify the three POST endpoints to take the lock**

In `foedus/web/routes/api.py`, change the chat/commit/orders handlers:

```python
    @app.post("/api/v1/games/{game_id}/chat")
    async def chat(game_id: str, request: Request):
        uid, pidx = _resolve_player(request, session_factory, settings, game_id)
        body = await request.json()
        from foedus.web.driver import handle_chat
        from foedus.web.locks import lock_for
        async with lock_for(game_id):
            return JSONResponse(handle_chat(session_factory, store, game_id, pidx, body))

    @app.post("/api/v1/games/{game_id}/commit")
    async def commit(game_id: str, request: Request):
        uid, pidx = _resolve_player(request, session_factory, settings, game_id)
        body = await request.json()
        from foedus.web.driver import handle_commit
        from foedus.web.locks import lock_for
        async with lock_for(game_id):
            return JSONResponse(handle_commit(session_factory, store, game_id, pidx, body))

    @app.post("/api/v1/games/{game_id}/orders")
    async def orders(game_id: str, request: Request):
        uid, pidx = _resolve_player(request, session_factory, settings, game_id)
        body = await request.json()
        from foedus.web.driver import handle_orders
        from foedus.web.locks import lock_for
        async with lock_for(game_id):
            return JSONResponse(handle_orders(session_factory, store, game_id, pidx, body))
```

- [ ] **Step 2: Run the full suite**

```bash
pytest tests/web/ -v
```
Expected: still all passing.

- [ ] **Step 3: Commit**

```bash
git add foedus/web/routes/api.py
git commit -m "feat(web): take per-game lock around all mutating API calls"
```

---

# Phase 7: Deadline worker

### Task 7.1: Background asyncio task that auto-advances expired phases

**Files:**
- Create: `foedus/web/deadline_worker.py`
- Create: `tests/web/test_deadline_worker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_deadline_worker.py
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
import pytest
from foedus.web.session_store import SqliteSessionStore
from foedus.web.deadline_worker import sweep_once
from foedus.web.models import Game
from tests.web.test_session_store import _make_seed_game

@pytest.mark.asyncio
async def test_sweep_advances_expired_game(db):
    with db() as s:
        _make_seed_game(s)
        g = s.get(Game, "g-test")
        g.current_phase_deadline_at = datetime.utcnow() - timedelta(minutes=1)
        s.commit()
    store = SqliteSessionStore(db)
    count = await sweep_once(db, store)
    assert count >= 1

@pytest.mark.asyncio
async def test_sweep_ignores_unexpired_game(db):
    with db() as s:
        _make_seed_game(s)
        g = s.get(Game, "g-test")
        g.current_phase_deadline_at = datetime.utcnow() + timedelta(hours=1)
        s.commit()
    store = SqliteSessionStore(db)
    count = await sweep_once(db, store)
    assert count == 0

@pytest.mark.asyncio
async def test_sweep_ignores_games_without_deadline(db):
    with db() as s:
        _make_seed_game(s)
        g = s.get(Game, "g-test")
        g.current_phase_deadline_at = None
        s.commit()
    store = SqliteSessionStore(db)
    count = await sweep_once(db, store)
    assert count == 0
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_deadline_worker.py -v
```

- [ ] **Step 3: Implement deadline_worker.py**

```python
"""Background asyncio task: every N seconds, advance games whose phase
deadline has passed. For each expired game, substitute HoldAgent orders
for any human seat that hasn't submitted, then run _maybe_advance.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Iterable
from foedus.web.locks import lock_for
from foedus.web.models import Game, GameSeat
from foedus.web.session_store import SqliteSessionStore

log = logging.getLogger(__name__)

async def sweep_once(session_factory, store: SqliteSessionStore) -> int:
    """Advance every game whose deadline has passed. Returns count advanced."""
    now = datetime.utcnow()
    expired_ids: list[str] = []
    with session_factory() as s:
        rows = (s.query(Game.id).filter(Game.status == "active",
                Game.current_phase_deadline_at.is_not(None),
                Game.current_phase_deadline_at < now).all())
        expired_ids = [r[0] for r in rows]
    advanced = 0
    for gid in expired_ids:
        async with lock_for(gid):
            advanced += int(_force_advance(session_factory, store, gid))
    return advanced

def _force_advance(session_factory, store: SqliteSessionStore, gid: str) -> bool:
    """Force the game past its current phase. For NEGOTIATION: mark every
    human seat done. For ORDERS: submit holds for every un-submitted unit
    owned by a human seat."""
    from foedus.core import Phase
    from foedus.legal import enumerate_legal_orders
    sess = store[gid]
    if sess.state.phase == Phase.NEGOTIATION:
        for pidx in sess.state.players:
            if sess.is_human(pidx) and not sess.state.chat_done.get(pidx, False):
                sess.signal_chat_done(pidx)
    if sess.state.phase == Phase.ORDERS:
        for pidx in sess.state.players:
            if not sess.is_human(pidx):
                continue
            if sess.has_submitted(pidx):
                continue
            # Hold every owned unit.
            holds = {}
            for unit in sess.state.units.values():
                if unit.owner != pidx:
                    continue
                # Construct an explicit Hold order using the existing API.
                from foedus.core import Order
                holds[unit.id] = Order(unit_id=unit.id, kind="hold")
            sess.submit_orders(pidx, holds)
    # Run normal advance loop.
    from foedus.web.driver import _maybe_advance
    advanced = _maybe_advance(sess)
    # Reset the deadline relative to now.
    with session_factory() as s:
        g = s.get(Game, gid)
        if g.phase_deadline_hours:
            g.current_phase_deadline_at = (datetime.utcnow()
                                           + timedelta(hours=g.phase_deadline_hours))
        if sess.state.is_terminal():
            g.status = "finished"
            g.finished_at = datetime.utcnow()
        s.commit()
    store.save(sess)
    return advanced

async def run_worker(session_factory, store: SqliteSessionStore,
                     tick_seconds: int = 60) -> None:
    log.info("deadline worker starting; tick=%ds", tick_seconds)
    while True:
        try:
            n = await sweep_once(session_factory, store)
            if n:
                log.info("deadline worker advanced %d game(s)", n)
        except Exception:
            log.exception("deadline worker tick failed")
        await asyncio.sleep(tick_seconds)
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_deadline_worker.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/deadline_worker.py tests/web/test_deadline_worker.py
git commit -m "feat(web): deadline worker auto-advances expired phases"
```

---

# Phase 8: Discord notify

### Task 8.1: Discord webhook poster (stub-friendly)

**Files:**
- Create: `foedus/web/notify.py`
- Create: `tests/web/test_notify.py`
- Modify: `foedus/web/driver.py` (call notifier on phase advance)

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_notify.py
from __future__ import annotations
import pytest
from foedus.web.notify import DiscordNotifier, NullNotifier

def test_null_notifier_silent():
    n = NullNotifier()
    n.notify("https://example", "hi")  # no exception

def test_discord_posts(monkeypatch):
    calls = []
    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        class R:
            status_code = 204
            def raise_for_status(self): pass
        return R()
    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    n = DiscordNotifier()
    n.notify("https://example/wh", "your turn in g-1")
    assert calls == [("https://example/wh", {"content": "your turn in g-1"})]

def test_discord_swallows_errors(monkeypatch):
    def fake_post(*a, **kw):
        raise Exception("boom")
    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    DiscordNotifier().notify("u", "msg")  # no exception
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_notify.py -v
```

- [ ] **Step 3: Implement notify.py**

```python
"""Discord webhook poster.

Best-effort, fire-and-forget. Errors are logged, not raised — a flaky
Discord must never block game progress.
"""
from __future__ import annotations
import logging
from typing import Protocol
import httpx

log = logging.getLogger(__name__)

class Notifier(Protocol):
    def notify(self, webhook_url: str, message: str) -> None: ...

class NullNotifier:
    def notify(self, webhook_url: str, message: str) -> None:
        pass

class DiscordNotifier:
    def notify(self, webhook_url: str, message: str) -> None:
        if not webhook_url:
            return
        try:
            r = httpx.post(webhook_url, json={"content": message}, timeout=5.0)
            r.raise_for_status()
        except Exception:
            log.exception("discord webhook failed (%s)", webhook_url[:40])
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_notify.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Wire it into the driver's `_maybe_advance`**

Modify `foedus/web/driver.py` to accept and use a notifier. Replace `_maybe_advance` with a version that takes a `notify_callback`:

```python
def _maybe_advance(sess, *, on_advance=None) -> bool:
    from foedus.core import Phase
    advanced_any = False
    while True:
        if sess.state.phase == Phase.NEGOTIATION:
            if not sess.is_chat_phase_complete():
                return advanced_any
            return advanced_any
        elif sess.state.phase == Phase.ORDERS:
            if not sess.all_orders_submitted():
                return advanced_any
            sess.advance()
            advanced_any = True
            if on_advance is not None:
                on_advance(sess)
            if sess.state.is_terminal():
                return advanced_any
            sess.init_round()
        else:
            return advanced_any
```

And the three handlers gain a `notifier` keyword:

```python
def handle_chat(session_factory, store, game_id, pidx, body, *, notifier=None):
    # ... unchanged body, but call _maybe_advance with on_advance...
    # (notifier wiring lives at the route level — see Task 8.2)
```

For simplicity, the notifier call happens in the route handler, not the driver. So driver stays clean.

- [ ] **Step 6: Commit**

```bash
git add foedus/web/notify.py tests/web/test_notify.py foedus/web/driver.py
git commit -m "feat(web): Discord webhook notifier + driver hook"
```

---

# Phase 9: App factory + lifespan

### Task 9.1: `make_web_app` factory wires everything together

**Files:**
- Create: `foedus/web/app.py`
- Create: `tests/web/test_app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_app.py
from __future__ import annotations
from fastapi.testclient import TestClient
from foedus.web.app import make_web_app

def test_app_boots_and_healthz(settings, db, monkeypatch):
    # Override get_settings to return our test settings
    monkeypatch.setattr("foedus.web.config.get_settings", lambda: settings)
    app = make_web_app(session_factory_override=db)
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["ok"] is True
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/web/test_app.py -v
```

- [ ] **Step 3: Implement app.py**

```python
"""FastAPI app factory. Wires session middleware, COOP/COEP, pages, API,
deadline worker, and the SqliteSessionStore."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from foedus.web.config import get_settings
from foedus.web.db import make_engine, make_session_factory, Base
from foedus.web.auth import install_session_middleware
from foedus.web.coop_coep import COOPCOEPMiddleware
from foedus.web.routes.pages import install_pages
from foedus.web.routes.api import install_api
from foedus.web.session_store import SqliteSessionStore
from foedus.web.deadline_worker import run_worker

def make_web_app(session_factory_override=None) -> FastAPI:
    settings = get_settings()
    if session_factory_override is not None:
        SessionLocal = session_factory_override
    else:
        engine = make_engine(settings.database_url)
        Base.metadata.create_all(engine)
        SessionLocal = make_session_factory(engine)
    store = SqliteSessionStore(SessionLocal)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(run_worker(
            SessionLocal, store, tick_seconds=settings.deadline_tick_seconds))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, BaseException):
                pass

    app = FastAPI(title="foedus web", version="0.1.0", lifespan=lifespan)
    app.add_middleware(COOPCOEPMiddleware)
    install_session_middleware(app, settings, SessionLocal)
    install_pages(app, SessionLocal)
    install_api(app, SessionLocal, store, settings)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/web/test_app.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add foedus/web/app.py tests/web/test_app.py
git commit -m "feat(web): make_web_app factory + lifespan-managed deadline worker"
```

---

# Phase 10: foedus-godot SPA changes (JWT-from-URL)

### Task 10.1: GameClient.gd reads gid/player_idx/token/api from URL

**Files (in foedus-godot):**
- Modify: `/home/david/foedus-godot/scripts/GameClient.gd`
- Modify: `/home/david/foedus-godot/scripts/Main.gd` (or whichever bootstraps GameClient)

This task happens in the foedus-godot repo, not foedus. Open a parallel branch there.

- [ ] **Step 1: Read URL query string from JS into GDScript**

In `GameClient.gd`, add a static helper that uses `JavaScriptBridge` when running on the web:

```gdscript
static func read_url_params() -> Dictionary:
    var result := {
        "gid": "",
        "player_idx": -1,
        "token": "",
        "api": "",
    }
    if OS.has_feature("web"):
        var window = JavaScriptBridge.get_interface("window")
        if window == null:
            return result
        var search = String(window.location.search)
        if search.begins_with("?"):
            search = search.substr(1)
        for pair in search.split("&"):
            var kv = pair.split("=", true, 1)
            if kv.size() != 2:
                continue
            var k = kv[0]
            var v = JavaScriptBridge.eval("decodeURIComponent('%s')" % kv[1])
            match k:
                "gid": result.gid = v
                "player_idx": result.player_idx = int(v)
                "token": result.token = v
                "api": result.api = v
    return result
```

- [ ] **Step 2: Modify HTTP request setup to send the bearer token**

Find every `HTTPRequest.request(url, ...)` call in `GameClient.gd`. Replace the headers argument with:

```gdscript
var headers := PackedStringArray(["Content-Type: application/json"])
if _bearer_token != "":
    headers.append("Authorization: Bearer " + _bearer_token)
```

Store `_bearer_token` as a `var _bearer_token: String = ""` member, set in `_ready()` via:

```gdscript
func _ready() -> void:
    var p := GameClient.read_url_params()
    if p.token != "":
        _bearer_token = p.token
    if p.api != "":
        _api_base = p.api      # was probably hardcoded to localhost:8765
    if p.gid != "":
        _game_id = p.gid
    if p.player_idx >= 0:
        _player_idx = p.player_idx
```

- [ ] **Step 3: Add a back-to-lobby button to the in-game UI**

In the topmost scene (`scenes/council/CouncilEntry.tscn` or its controller `.gd`):

```gdscript
func _on_lobby_pressed() -> void:
    if OS.has_feature("web"):
        var window = JavaScriptBridge.get_interface("window")
        window.location.assign("/games")
    else:
        get_tree().quit()
```

Wire a Button labeled "Back to lobby" to this signal.

- [ ] **Step 4: Build and verify**

```bash
cd /home/david/foedus-godot
godot --headless --export-release "Web" /tmp/foedus-godot-web/index.html
ls -la /tmp/foedus-godot-web/
```

Test by serving with the COOP/COEP server and opening with `?gid=test&player_idx=0&token=fake&api=http://localhost:8765/api/v1` — verify the network tab shows `Authorization: Bearer fake` on every request.

- [ ] **Step 5: Commit (in foedus-godot)**

```bash
cd /home/david/foedus-godot
git add scripts/GameClient.gd scripts/Main.gd scenes/council/
git commit -m "feat: read gid/player_idx/token/api from URL query string"
git push
```

---

# Phase 11: End-to-end smoke test

### Task 11.1: Two simulated humans walk one full turn

**Files:**
- Create: `tests/web/test_full_turn_e2e.py`

- [ ] **Step 1: Write the test**

```python
# tests/web/test_full_turn_e2e.py
"""End-to-end: create a game with 2 humans + 2 bots, walk one full turn,
verify the game state advances."""
from __future__ import annotations
import json
import pytest
from fastapi.testclient import TestClient
from foedus.web.app import make_web_app
from foedus.web.auth import create_session
from foedus.web.models import User, Game

def test_two_humans_walk_one_turn(settings, db, monkeypatch):
    monkeypatch.setattr("foedus.web.config.get_settings", lambda: settings)
    app = make_web_app(session_factory_override=db)
    # Create two users.
    with db() as s:
        u_a = User(github_id=10, github_login="a"); s.add(u_a)
        u_b = User(github_id=11, github_login="b"); s.add(u_b); s.flush()
        tok_a = create_session(s, u_a.id)
        tok_b = create_session(s, u_b.id)
        s.commit()
    with TestClient(app) as c:
        c.cookies.set("foedus_session", tok_a)
        r = c.post("/games", data={
            "map_preset": "CONTINENTAL_SWEEP", "max_turns": "5",
            "phase_deadline_hours": "24", "discord_webhook_url": "",
            "seat_0_kind": "human", "seat_0_user": "a",
            "seat_1_kind": "human", "seat_1_user": "b",
            "seat_2_kind": "bot",
            "seat_2_bot": "foedus.agents.heuristic.HeuristicAgent",
            "seat_3_kind": "bot",
            "seat_3_bot": "foedus.agents.heuristic.HeuristicAgent",
        }, follow_redirects=False)
        assert r.status_code == 302
        gid = r.headers["location"].rsplit("/", 1)[-1]

        # Both humans signal done on negotiation.
        for tok in (tok_a, tok_b):
            c.cookies.set("foedus_session", tok)
            pidx = 0 if tok == tok_a else 1
            r = c.post(f"/api/v1/games/{gid}/commit",
                       json={"intents": [], "aid_spends": [], "done": True})
            assert r.status_code == 200, r.text

        # Both humans submit hold orders for all their units.
        for tok, pidx in [(tok_a, 0), (tok_b, 1)]:
            c.cookies.set("foedus_session", tok)
            r = c.get(f"/api/v1/games/{gid}/view/{pidx}")
            state = r.json()
            holds = [{"unit_id": uid, "kind": "hold"}
                     for uid, u in state["units"].items()
                     if u["owner"] == pidx]
            r = c.post(f"/api/v1/games/{gid}/orders", json={"orders": holds})
            assert r.status_code == 200, r.text

        # Verify turn advanced.
        with db() as s:
            g = s.get(Game, gid)
            state = json.loads(g.state_json)
            assert state["turn"] >= 1
```

- [ ] **Step 2: Run**

```bash
pytest tests/web/test_full_turn_e2e.py -v
```
Expected: 1 passed. If it fails, the failure pinpoints which engine-API name we got wrong in driver.py — fix and re-run.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/web/test_full_turn_e2e.py
git commit -m "test(web): e2e — two humans walk one full turn"
```

---

# Phase 12: Deployment

### Task 12.1: Dockerfile

**Files:**
- Create: `Dockerfile.web`
- Create: `.dockerignore`

- [ ] **Step 1: Write Dockerfile.web**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY foedus/ ./foedus/
COPY migrations/ ./migrations/
COPY alembic.ini ./

RUN pip install -e .[web]

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn foedus.web.app:make_web_app --factory --host 0.0.0.0 --port 8000"]
```

Write `.dockerignore`:

```
__pycache__
*.pyc
.git
.pytest_cache
tests/
foedus_web.db
/tmp
docs/
.github/
```

- [ ] **Step 2: Build and smoke-test locally**

```bash
docker build -f Dockerfile.web -t foedus-web .
docker run --rm -p 8000:8000 \
  -e FOEDUS_SESSION_SECRET=test -e FOEDUS_JWT_SECRET=test \
  -e FOEDUS_GITHUB_OAUTH_CLIENT_ID=x -e FOEDUS_GITHUB_OAUTH_CLIENT_SECRET=y \
  foedus-web &
sleep 5
curl -s http://localhost:8000/healthz
```
Expected: `{"ok":true}`.

```bash
docker stop $(docker ps -q --filter ancestor=foedus-web)
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile.web .dockerignore
git commit -m "build(web): Dockerfile.web + .dockerignore"
```

---

### Task 12.2: fly.toml

**Files:**
- Create: `fly.toml`

- [ ] **Step 1: Write fly.toml**

```toml
app = "foedus-web"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile.web"

[env]
  FOEDUS_DATABASE_URL = "sqlite:////data/foedus_web.db"
  FOEDUS_BASE_URL = "https://foedus-web.fly.dev"

[[mounts]]
  source = "foedus_data"
  destination = "/data"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0
  processes = ["app"]

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

- [ ] **Step 2: Document the deploy steps in README**

Append to `README.md` a new section:

```markdown
## Async web-play deployment (Fly.io)

One-time:

```sh
flyctl launch --no-deploy --copy-config
flyctl volume create foedus_data --size 1
flyctl secrets set \
  FOEDUS_SESSION_SECRET="$(openssl rand -hex 32)" \
  FOEDUS_JWT_SECRET="$(openssl rand -hex 32)" \
  FOEDUS_GITHUB_OAUTH_CLIENT_ID=<github oauth client id> \
  FOEDUS_GITHUB_OAUTH_CLIENT_SECRET=<github oauth client secret>
```

Per deploy:

```sh
flyctl deploy
```

Set the GitHub OAuth callback URL to `https://foedus-web.fly.dev/auth/github/callback`.
```

- [ ] **Step 3: Commit**

```bash
git add fly.toml README.md
git commit -m "deploy(web): fly.toml + README deploy instructions"
```

---

### Task 12.3: GitHub Actions deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: deploy web
on:
  push:
    branches: [main]
    paths:
      - 'foedus/**'
      - 'migrations/**'
      - 'pyproject.toml'
      - 'Dockerfile.web'
      - 'fly.toml'
      - '.github/workflows/deploy.yml'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e .[dev]
      - run: pytest -q

  build-godot:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
        with:
          repository: dbyrne/foedus-godot
          path: foedus-godot
      - name: Install Godot 4.3
        run: |
          curl -L -o godot.zip https://github.com/godotengine/godot/releases/download/4.3-stable/Godot_v4.3-stable_linux.x86_64.zip
          unzip godot.zip
          mv Godot_v4.3-stable_linux.x86_64 /usr/local/bin/godot
          chmod +x /usr/local/bin/godot
      - name: Install export templates
        run: |
          curl -L -o tpz.zip https://github.com/godotengine/godot/releases/download/4.3-stable/Godot_v4.3-stable_export_templates.tpz
          mkdir -p ~/.local/share/godot/export_templates/4.3.stable
          unzip -o tpz.zip -d ~/.local/share/godot/export_templates/4.3.stable
      - name: Build web export
        run: |
          mkdir -p foedus/web/static/godot
          godot --headless --path foedus-godot --export-release "Web" foedus/web/static/godot/index.html
      - uses: actions/upload-artifact@v4
        with:
          name: godot-web
          path: foedus/web/static/godot/

  deploy:
    runs-on: ubuntu-latest
    needs: build-godot
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: { name: godot-web, path: foedus/web/static/godot/ }
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci(web): build Godot HTML5 + deploy to Fly on main"
```

---

# Final checklist

- [ ] All tests pass: `pytest -q`
- [ ] Docker image builds: `docker build -f Dockerfile.web -t foedus-web .`
- [ ] OAuth app created on GitHub with callback URL set
- [ ] `flyctl deploy` succeeds and `https://foedus-web.fly.dev/healthz` returns `{"ok": true}`
- [ ] One real game played to completion with David + dbyrne on phones

# Phase 9 follow-ups (from spike — 2026-05-13)

The Phase 0 spike passed (bundle 35 MB / ~10 MB brotli, COOP/COEP
working, canvas + taps + SharedArrayBuffer all good, 0 console
errors). Decision: proceed pure-Godot. Four caveats observed:

- **FU-1: Server URL input clipped on 412 px viewport.** Godot-side
  responsive-layout fix. Probably an anchor-width setting on the
  `LineEdit` in `scenes/council/CouncilEntry.tscn`. Trivial; ship
  alongside Task 10.1.

- **FU-2: In-canvas lobby UI needs an "if URL params, skip" branch.**
  When `gid` / `player_idx` / `token` / `api` are present in the URL,
  the Godot client should hide its connection lobby and auto-connect.
  Already covered by Task 10.1 — add an explicit check in
  `_ready()` to skip the lobby Control node when `gid` is set.

- **FU-3: Touch on the hex map is still unverified.** Rerun the
  spike harness AFTER Task 10.1 completes, with a real game running.
  Add as a new Task 10.2 below.

- **FU-4: Slow WASM cold start (~5–10 s).** Add a "Loading game…"
  splash in `templates/game_spa.html`. Already covered by Task 5.1's
  HTML — add a CSS-positioned overlay that the Godot canvas's
  `focus_canvas_on_start` fires `display: none` on. Add as Task 5.3.

### Task 5.3: Loading splash overlay on the SPA wrapper page

**Files:**
- Modify: `foedus/web/templates/game_spa.html`

- [ ] **Step 1: Add the overlay**

In `game_spa.html`, replace the body section with:

```html
<body>
<div class="bar"><a href="/games">← lobby</a> {{ game.id }} (you are P{{ player_idx }})</div>
<div id="loading">Loading game… (first load ~10s)</div>
<iframe id="game" src="/static/godot/index.html?gid={{ game.id }}&player_idx={{ player_idx }}&token={{ token }}&api={{ api_base }}"
        allow="cross-origin-isolated"
        onload="setTimeout(()=>document.getElementById('loading').style.display='none', 1500)"></iframe>
<style>
#loading{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);color:#fff;font:18px system-ui;background:#1f3a5f;padding:1rem 2rem;border-radius:6px;z-index:5}
#game{display:block}
</style>
</body>
```

- [ ] **Step 2: Commit**

```bash
git add foedus/web/templates/game_spa.html
git commit -m "feat(web): loading splash on SPA wrapper for slow Godot cold start"
```

### Task 10.2: Second mobile spike pass with a live game

**Files:**
- Modify: `/tmp/foedus-eval/notes.md` (append findings)

- [ ] **Step 1: Re-export foedus-godot with Task 10.1's changes**

```bash
cd /home/david/foedus-godot
godot --headless --export-release "Web" /tmp/foedus-godot-web/index.html
```

- [ ] **Step 2: Run a real game**

Start the foedus play-server with a 4-seat game (per Task 0.1 Step 5).
Mint a JWT (use a Python REPL with `foedus.web.jwt_helper.mint_spa_token`).

- [ ] **Step 3: Open the SPA with full URL params**

```
browser_resize 412 915
browser_navigate http://localhost:8080/?gid=<gid>&player_idx=0&token=<jwt>&api=http://localhost:8765
```

- [ ] **Step 4: Walk through one full turn on the phone viewport**

Document for each: tap hex node, drag/pinch on map, tap chat field,
type message, send. Screenshot at each step into
`/tmp/foedus-eval/10-*.png`.

- [ ] **Step 5: Append findings to /tmp/foedus-eval/notes.md**

If anything is broken: open a new follow-up task on the foedus-godot
side. If everything works: mark FU-3 closed and proceed to Phase 11.
