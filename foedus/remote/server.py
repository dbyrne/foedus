"""HTTP server that wraps any `Agent` and exposes the foedus wire protocol.

`make_app(agent)` returns a FastAPI app with three endpoints:
    POST /act     — the strategic decision endpoint
    GET  /info    — agent metadata
    GET  /healthz — liveness probe

`serve(agent, ...)` runs uvicorn (foreground, blocking) — the canonical
entry point used by `foedus agent serve` and by `Dockerfile.agent`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from foedus.agents.base import Agent
from foedus.remote.wire import (
    deserialize_state,
    serialize_orders,
)


class ActRequest(BaseModel):
    state: dict[str, Any]
    player: int


class ActResponse(BaseModel):
    orders: dict[str, dict[str, Any]] = Field(default_factory=dict)


class InfoResponse(BaseModel):
    name: str
    version: str
    capabilities: list[str] = Field(default_factory=list)


class AgentServer:
    """Convenience holder pairing an agent with its metadata."""

    def __init__(self, agent: Agent, *,
                 name: str = "agent",
                 version: str = "0.1.0",
                 capabilities: list[str] | None = None) -> None:
        self.agent = agent
        self.name = name
        self.version = version
        self.capabilities = capabilities or []


def make_app(agent: Agent, *,
             name: str = "agent",
             version: str = "0.1.0",
             capabilities: list[str] | None = None) -> FastAPI:
    """Build a FastAPI app exposing the agent over HTTP.

    Pure factory — testable via fastapi.testclient.TestClient(make_app(...)).
    """
    app = FastAPI(title=f"foedus agent: {name}", version=version)
    server = AgentServer(agent, name=name, version=version,
                         capabilities=capabilities)

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/info", response_model=InfoResponse)
    def info() -> InfoResponse:
        return InfoResponse(
            name=server.name,
            version=server.version,
            capabilities=server.capabilities,
        )

    @app.post("/act", response_model=ActResponse)
    def act(req: ActRequest) -> ActResponse:
        state = deserialize_state(req.state)
        orders = server.agent.choose_orders(state, req.player)
        return ActResponse(orders=serialize_orders(orders))

    return app


def serve(agent: Agent, *,
          host: str = "127.0.0.1",
          port: int = 8080,
          name: str = "agent",
          version: str = "0.1.0",
          capabilities: list[str] | None = None) -> None:
    """Run the agent server with uvicorn (foreground, blocking)."""
    import uvicorn

    app = make_app(agent, name=name, version=version,
                   capabilities=capabilities)
    uvicorn.run(app, host=host, port=port, log_level="info")
