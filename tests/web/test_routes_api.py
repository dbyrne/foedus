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
