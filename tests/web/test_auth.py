from __future__ import annotations
from datetime import datetime, timedelta, timezone
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
                         expires_at=datetime.now(timezone.utc) - timedelta(hours=1)))
        s.commit()
    client = TestClient(_make_app(settings, db))
    client.cookies.set("foedus_session", "expired")
    r = client.get("/whoami")
    assert r.json() == {"login": None}
