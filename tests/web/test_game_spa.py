from __future__ import annotations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from foedus.web.auth import install_session_middleware, create_session
from foedus.web.coop_coep import COOPCOEPMiddleware
from foedus.web.routes.pages import install_pages
from foedus.web.models import User, Game, GameSeat

def _client(settings, db):
    app = FastAPI()
    app.add_middleware(COOPCOEPMiddleware)
    install_session_middleware(app, settings, db)
    install_pages(app, db)
    return TestClient(app)

def test_game_spa_requires_seat(settings, db):
    with db() as s:
        owner = User(github_id=1, github_login="a"); s.add(owner)
        other = User(github_id=2, github_login="b"); s.add(other); s.flush()
        s.add(Game(id="g-spa", created_by=owner.id, status="active",
                   map_seed=1, map_preset="continental_sweep",
                   max_turns=5, state_json="{}"))
        s.add(GameSeat(game_id="g-spa", player_idx=0, kind="human", user_id=owner.id))
        token = create_session(s, other.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.get("/games/g-spa")
    assert r.status_code == 403

def test_game_spa_sets_coop_coep_and_includes_token(settings, db):
    with db() as s:
        u = User(github_id=3, github_login="alice"); s.add(u); s.flush()
        s.add(Game(id="g-spa2", created_by=u.id, status="active",
                   map_seed=1, map_preset="continental_sweep",
                   max_turns=5, state_json="{}"))
        s.add(GameSeat(game_id="g-spa2", player_idx=0, kind="human", user_id=u.id))
        token = create_session(s, u.id); s.commit()
    c = _client(settings, db); c.cookies.set("foedus_session", token)
    r = c.get("/games/g-spa2")
    assert r.status_code == 200
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert r.headers["cross-origin-embedder-policy"] == "require-corp"
    assert "gid=g-spa2" in r.text
    assert "player_idx=0" in r.text
    assert "token=" in r.text
