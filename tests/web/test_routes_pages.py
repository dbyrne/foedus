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
                   map_seed=1, map_preset="continental_sweep", max_turns=5, state_json="{}"))
        s.add(GameSeat(game_id="g-1", player_idx=0, kind="human", user_id=u.id))
        token = create_session(s, u.id)
        s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.get("/games")
    assert r.status_code == 200
    assert "g-1" in r.text

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
        "map_preset": "continental_sweep",
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

def test_games_post_invalid_archetype_rejected(settings, db):
    with db() as s:
        u = User(github_id=20, github_login="alice"); s.add(u); s.flush()
        token = create_session(s, u.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.post("/games", data={
        "map_preset": "not_a_real_preset",
        "max_turns": "5", "phase_deadline_hours": "24", "discord_webhook_url": "",
        "seat_0_kind": "human", "seat_0_user": "alice",
        "seat_1_kind": "bot", "seat_1_bot": "foedus.agents.heuristic.HoldAgent",
        "seat_2_kind": "bot", "seat_2_bot": "foedus.agents.heuristic.HoldAgent",
        "seat_3_kind": "bot", "seat_3_bot": "foedus.agents.heuristic.HoldAgent",
    })
    assert r.status_code == 400

def test_games_post_disallowed_bot_class_rejected(settings, db):
    with db() as s:
        u = User(github_id=21, github_login="alice"); s.add(u); s.flush()
        token = create_session(s, u.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.post("/games", data={
        "map_preset": "continental_sweep", "max_turns": "5",
        "phase_deadline_hours": "24", "discord_webhook_url": "",
        "seat_0_kind": "human", "seat_0_user": "alice",
        "seat_1_kind": "bot", "seat_1_bot": "os.system",
        "seat_2_kind": "bot", "seat_2_bot": "foedus.agents.heuristic.HoldAgent",
        "seat_3_kind": "bot", "seat_3_bot": "foedus.agents.heuristic.HoldAgent",
    })
    assert r.status_code == 400

def test_placeholder_user_reconciled_on_login(settings, db):
    """Creating a game with a placeholder login, then the real user logging
    in via the callback path should reconcile to the same User row."""
    from foedus.web.driver import create_new_game
    with db() as s:
        creator = User(github_id=30, github_login="creator"); s.add(creator); s.commit()
        creator_id = creator.id
    with db() as s:
        creator = s.get(User, creator_id)
        gid = create_new_game(db, creator=creator, form={
            "map_preset": "continental_sweep", "max_turns": "5",
            "phase_deadline_hours": "24", "discord_webhook_url": "",
            "seat_0_kind": "human", "seat_0_user": "creator",
            "seat_1_kind": "human", "seat_1_user": "invited_friend",
            "seat_2_kind": "bot", "seat_2_bot": "foedus.agents.heuristic.HoldAgent",
            "seat_3_kind": "bot", "seat_3_bot": "foedus.agents.heuristic.HoldAgent",
        })
    with db() as s:
        ph = s.query(User).filter_by(github_login="invited_friend").one()
        assert ph.github_id is None  # placeholder
        ph_id = ph.id
    # Simulate the OAuth callback reconciliation path.
    with db() as s:
        existing = s.query(User).filter_by(github_id=999).first()
        if existing is None:
            existing = s.query(User).filter_by(github_login="invited_friend").first()
            if existing is not None:
                existing.github_id = 999
        assert existing is not None
        assert existing.id == ph_id  # SAME row reconciled
        s.commit()
    with db() as s:
        assert s.query(User).filter_by(github_login="invited_friend").count() == 1
