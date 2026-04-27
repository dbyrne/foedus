"""FastAPI app exposing GameSessions over HTTP for UI clients.

Designed for *local* trusted use — the Python import path of an agent class
is accepted from clients. Bind to 127.0.0.1 by default; only expose to a
network you trust.

Endpoints:

    POST   /games                      create a session, returns game_id + view
    GET    /games                      list active sessions (admin)
    GET    /games/{id}                 admin view (full state)
    GET    /games/{id}/view/{player}   per-player view (legal orders etc.)
    POST   /games/{id}/orders          submit human orders
    POST   /games/{id}/advance         resolve one turn (or auto-advance)
    DELETE /games/{id}                 dispose
    GET    /healthz
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from foedus.core import GameConfig
from foedus.game_server.session import (
    GameSession,
    SeatSpec,
    build_agent,
)
from foedus.mapgen import generate_map
from foedus.remote.wire import deserialize_orders
from foedus.resolve import initial_state


class SeatPayload(BaseModel):
    type: str
    name: str | None = None
    kind: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    url: str | None = None


class CreateGameRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    seats: list[SeatPayload]


class CreateGameResponse(BaseModel):
    game_id: str
    view: dict[str, Any]


class SubmitOrdersRequest(BaseModel):
    player: int
    orders: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AdvanceRequest(BaseModel):
    auto: bool = False           # keep advancing while no humans block
    max_turns: int = 1000        # safety bound for auto


def make_app() -> FastAPI:
    app = FastAPI(title="foedus game server", version="0.1.0")
    sessions: dict[str, GameSession] = {}

    def _session(game_id: str) -> GameSession:
        sess = sessions.get(game_id)
        if sess is None:
            raise HTTPException(status_code=404, detail=f"unknown game_id {game_id!r}")
        return sess

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"ok": True, "sessions": len(sessions)}

    @app.post("/games", response_model=CreateGameResponse)
    def create_game(req: CreateGameRequest) -> CreateGameResponse:
        try:
            cfg = GameConfig(**req.config)
        except TypeError as e:
            raise HTTPException(status_code=400,
                                detail=f"invalid config: {e}")
        if len(req.seats) != cfg.num_players:
            raise HTTPException(
                status_code=400,
                detail=f"need {cfg.num_players} seats, got {len(req.seats)}",
            )
        m = generate_map(cfg.num_players, seed=cfg.seed)
        state = initial_state(cfg, m)

        seats: dict[int, SeatSpec] = {}
        agents: dict[int, Any] = {}
        for i, sp in enumerate(req.seats):
            try:
                seat = SeatSpec(
                    type=sp.type, name=sp.name, kind=sp.kind,
                    args=sp.args or {}, url=sp.url,
                )
            except ValueError as e:
                raise HTTPException(status_code=400,
                                    detail=f"seat {i}: {e}")
            seats[i] = seat
            if seat.type != "human":
                try:
                    agents[i] = build_agent(seat)
                except ValueError as e:
                    raise HTTPException(status_code=400,
                                        detail=f"seat {i}: {e}")

        game_id = str(uuid.uuid4())
        sess = GameSession(
            game_id=game_id,
            state=state,
            seats=seats,
            agents=agents,
        )
        sessions[game_id] = sess

        # Show seat 0's view by default — clients usually want the first
        # player's perspective immediately after create.
        return CreateGameResponse(game_id=game_id, view=sess.view_for(0))

    @app.get("/games")
    def list_games() -> dict[str, Any]:
        return {
            "games": [
                {
                    "game_id": gid,
                    "turn": s.state.turn,
                    "is_terminal": s.state.is_terminal(),
                    "awaiting_humans": s.awaiting_humans(),
                }
                for gid, s in sessions.items()
            ]
        }

    @app.get("/games/{game_id}")
    def admin_view(game_id: str) -> dict[str, Any]:
        sess = _session(game_id)
        # "Admin" view: full state, no fog filter; useful for debugging /
        # spectator UIs.
        from foedus.remote.wire import serialize_state
        return {
            "game_id": game_id,
            "turn": sess.state.turn,
            "state": serialize_state(sess.state),
            "awaiting_humans": sess.awaiting_humans(),
            "is_terminal": sess.state.is_terminal(),
        }

    @app.get("/games/{game_id}/view/{player}")
    def player_view(game_id: str, player: int) -> dict[str, Any]:
        sess = _session(game_id)
        if player not in sess.seats:
            raise HTTPException(status_code=400,
                                detail=f"unknown player {player}")
        return sess.view_for(player)

    @app.post("/games/{game_id}/orders")
    def submit_orders(game_id: str,
                      req: SubmitOrdersRequest) -> dict[str, Any]:
        sess = _session(game_id)
        if req.player not in sess.seats:
            raise HTTPException(status_code=400,
                                detail=f"unknown player {req.player}")
        if not sess.is_human(req.player):
            raise HTTPException(status_code=400,
                                detail=f"player {req.player} is not a human seat")
        try:
            orders = deserialize_orders(req.orders)
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=400,
                                detail=f"invalid orders: {e}")
        try:
            sess.submit_human_orders(req.player, orders)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, "ready_to_resolve": sess.can_resolve()}

    @app.post("/games/{game_id}/advance")
    def advance(game_id: str, req: AdvanceRequest) -> dict[str, Any]:
        sess = _session(game_id)
        if not sess.can_resolve():
            return {
                "advanced": 0,
                "awaiting_humans": sess.awaiting_humans(),
                "turn": sess.state.turn,
                "is_terminal": sess.state.is_terminal(),
            }
        if req.auto:
            n = sess.auto_advance(max_turns=req.max_turns)
        else:
            sess.advance()
            n = 1
        return {
            "advanced": n,
            "awaiting_humans": sess.awaiting_humans(),
            "turn": sess.state.turn,
            "is_terminal": sess.state.is_terminal(),
        }

    @app.delete("/games/{game_id}")
    def delete_game(game_id: str) -> dict[str, Any]:
        if game_id not in sessions:
            raise HTTPException(status_code=404,
                                detail=f"unknown game_id {game_id!r}")
        del sessions[game_id]
        return {"ok": True}

    return app


def serve(host: str = "127.0.0.1", port: int = 8090) -> None:
    """Run the game server with uvicorn (foreground, blocking)."""
    import uvicorn

    app = make_app()
    uvicorn.run(app, host=host, port=port, log_level="info")
