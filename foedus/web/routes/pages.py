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
        return templates.TemplateResponse(request, "login.html",
                                          {"user": None})

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
        return templates.TemplateResponse(request, "games_list.html",
                                          {"user": u, "grouped": dict(grouped)})

    @app.get("/games/new", response_class=HTMLResponse)
    def games_new(request: Request):
        u = current_user(request, session_factory)
        if u is None:
            return RedirectResponse("/login", status_code=302)
        return templates.TemplateResponse(request, "games_new.html",
                                          {"user": u})

    @app.post("/games")
    async def games_create(request: Request):
        u = current_user(request, session_factory)
        if u is None:
            return RedirectResponse("/login", status_code=302)
        form = await request.form()
        from foedus.web.driver import create_new_game
        gid = create_new_game(session_factory, creator=u, form=dict(form))
        return RedirectResponse(f"/games/{gid}", status_code=302)
