"""JSON API: mount the existing foedus.game_server endpoints under
/api/v1, but front them with our cookie-or-JWT auth wrapper.

For the MVP, this implementation route-handles the subset of game_server
endpoints the SPA actually calls. We do NOT reuse make_app() because its
closure-captured sessions dict + no auth makes wrapping awkward.
"""
from __future__ import annotations
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from foedus.web.auth import current_user
from foedus.web.config import Settings
from foedus.web.jwt_helper import verify_spa_token, InvalidToken
from foedus.web.models import GameSeat
from foedus.web.session_store import SqliteSessionStore


def _resolve_player(request: Request, session_factory, settings: Settings,
                    game_id: str) -> tuple[int, int]:
    """Return (user_id, player_idx) for an authenticated caller; raise
    HTTPException 401/403 on failure. Tries Authorization: Bearer first,
    then session cookie. Note: never leaks PyJWT error strings."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        parts = auth.split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            raise HTTPException(401, "unauthorized")
        tok = parts[1].strip()
        try:
            claims = verify_spa_token(tok, secret=settings.jwt_secret)
        except InvalidToken:
            # Don't propagate PyJWT's internal message — generic 401.
            raise HTTPException(401, "unauthorized")
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
        return JSONResponse(sess.view_for(pidx))

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
