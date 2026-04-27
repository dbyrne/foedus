"""HTTP server for local interactive play.

Hosts a multi-player game session that mixes human players (driving via
the HTTP API from a UI like Godot) and agents (in-process, or remote
Dockerized agents speaking the foedus.remote protocol).

Optional dependency. Install with:
    pip install foedus[remote]

(The server reuses fastapi/uvicorn that the remote extra already pulls in.)
"""

from __future__ import annotations

try:
    from foedus.game_server.server import make_app, serve
    from foedus.game_server.session import GameSession, SeatSpec, build_agent
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "foedus.game_server requires fastapi/uvicorn. "
        "Install with: pip install foedus[remote]"
    ) from e

__all__ = ["GameSession", "SeatSpec", "build_agent", "make_app", "serve"]
