"""GitHub OAuth + cookie-based sessions.

The session cookie value is an opaque random token; the (token -> user_id)
mapping lives in the `sessions` table. We don't sign-only-cookie because
explicit DB rows make revocation trivial.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
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
    # for OAuth (not for our user session - that's our own cookie).
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
                      expires_at=datetime.now(timezone.utc) + timedelta(days=ttl_days)))
    return token

def current_user(request: Request, session_factory) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with session_factory() as s:
        row = s.get(SessionRow, token)
        if row is None:
            return None
        # SQLite's DateTime(timezone=True) strips tzinfo on read; treat naive
        # datetimes as UTC for comparison with our timezone-aware "now".
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return None
        return s.get(User, row.user_id)

def require_user(request: Request, session_factory) -> User:
    u = current_user(request, session_factory)
    if u is None:
        raise HTTPException(status_code=401, detail="login required")
    return u
