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
