"""HTTP client that implements the foedus `Agent` protocol over the wire."""

from __future__ import annotations

from typing import Any

import httpx

from foedus.core import ChatDraft, GameState, Order, PlayerId, Press, UnitId
from foedus.remote.wire import (
    deserialize_orders,
    serialize_state,
)


class RemoteAgent:
    """An `Agent` whose `choose_orders` calls a remote AgentServer over HTTP.

    Drop-in replacement for an in-process agent: same `choose_orders(state, player)`
    signature, same return type. Lets `play_game(...)` mix in-process and
    remote agents transparently.

    The `client` parameter is for tests — pass a fastapi TestClient (which is
    an httpx.Client subclass) and the agent talks to the in-process app
    without going through a real network.
    """

    def __init__(self, url: str = "http://localhost:8080", *,
                 timeout: float = 30.0,
                 client: httpx.Client | None = None) -> None:
        self.url = url.rstrip("/")
        if client is not None:
            self._http = client
            self._owns_client = False
        else:
            self._http = httpx.Client(base_url=self.url, timeout=timeout)
            self._owns_client = True

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        r = self._http.post("/act", json={
            "state": serialize_state(state),
            "player": player,
        })
        r.raise_for_status()
        body = r.json()
        return deserialize_orders(body["orders"])

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        """Default empty press. Press v0 over the wire is not yet implemented;
        when it is, this should call a /press endpoint analogous to /act."""
        return Press(stance={}, intents=[])

    def chat_drafts(self, state: GameState,
                    player: PlayerId) -> list[ChatDraft]:
        """Default no chat. RemoteAgents speak via /act only for now."""
        return []

    def info(self) -> dict[str, Any]:
        r = self._http.get("/info")
        r.raise_for_status()
        return r.json()

    def healthz(self) -> bool:
        try:
            r = self._http.get("/healthz", timeout=2.0)
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False
        return r.status_code == 200 and r.json().get("ok") is True

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> "RemoteAgent":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
