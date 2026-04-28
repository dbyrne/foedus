"""HTTP wire protocol for foedus agents.

Each agent is exposed as a tiny HTTP service:

    POST /act     { state: <serialized GameState>, player: int }
                  -> { orders: { "<unit_id>": <serialized Order>, ... } }
    GET  /info    -> { name, version, capabilities }
    GET  /healthz -> { ok: true }

The same protocol works whether the agent runs in a sibling process, on
another machine over SSH, or inside a Docker container the game runner
pulls from a registry. `RemoteAgent` is a drop-in `Agent` that delegates
its `choose_orders` call to a remote endpoint, so `play_game(...)` works
unchanged with mixed in-process and remote agents.

Optional dependency. Install with:
    pip install foedus[remote]
"""

from __future__ import annotations

try:
    from foedus.remote.client import RemoteAgent
    from foedus.remote.server import AgentServer, make_app, serve
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "foedus.remote requires fastapi/uvicorn/httpx. "
        "Install with: pip install foedus[remote]"
    ) from e

__all__ = ["AgentServer", "RemoteAgent", "make_app", "serve"]
