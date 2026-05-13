"""Per-route COOP/COEP header attachment.

Applied to:
  - GET /games/{gid}        (the Godot SPA loader page)
  - GET /static/godot/*     (the Godot HTML5 assets)

NOT applied to:
  - /auth/github/callback   (would break the OAuth popup)
  - all other routes
"""
from __future__ import annotations
from starlette.types import ASGIApp, Receive, Scope, Send

COOP = (b"cross-origin-opener-policy", b"same-origin")
COEP = (b"cross-origin-embedder-policy", b"require-corp")
CORP = (b"cross-origin-resource-policy", b"cross-origin")


def needs_isolation(path: str) -> bool:
    """True iff the path should receive COOP/COEP isolation headers."""
    if path.startswith("/static/godot"):
        return True
    if path.startswith("/games/"):
        suffix = path[len("/games/"):]
        if suffix and "/" not in suffix and suffix != "new":
            return True
    return False


class COOPCOEPMiddleware:
    """ASGI middleware that attaches COOP/COEP/CORP headers to specific
    paths (see `needs_isolation`). Non-isolated paths pass through
    unchanged — important for the OAuth popup, which COOP would break."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if not needs_isolation(path):
            return await self.app(scope, receive, send)

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(COOP)
                headers.append(COEP)
                headers.append(CORP)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, _send)
