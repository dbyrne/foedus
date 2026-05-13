"""Adapter between SQLAlchemy-persisted Game rows and in-memory GameSession.

Behaves like dict[str, GameSession] for game_server.make_app's needs:
- __getitem__(game_id) loads from DB, hydrates a GameSession
- __setitem__(game_id, sess) persists state_json
- __contains__ / __len__ supported
- save(sess) is the canonical mutation flush

Cache semantics: __getitem__ rebuilds the GameSession (and any agents)
from the DB on every call — there is no in-process cache. This is
correct for HeuristicAgent (stateless) but would lose state for any
future stateful agent (RNG seed, MCP/LLM handle, etc.). Re-evaluate
if a stateful agent class lands.
"""
from __future__ import annotations
import json
from typing import Any
from foedus.game_server.session import GameSession, SeatSpec, build_agent
from foedus.remote.wire import serialize_state, deserialize_state
from foedus.web.models import Game, GameSeat

class SqliteSessionStore:
    def __init__(self, session_factory):
        self._sf = session_factory

    def __getitem__(self, game_id: str) -> GameSession:
        with self._sf() as s:
            g = s.get(Game, game_id)
            if g is None:
                raise KeyError(game_id)
            state = deserialize_state(json.loads(g.state_json))
            seats: dict[int, SeatSpec] = {}
            agents: dict[int, Any] = {}
            for row in g.seats:
                if row.kind == "human":
                    seats[row.player_idx] = SeatSpec(type="human",
                                                    name=f"u{row.user_id}")
                else:
                    spec = SeatSpec(type="agent", name=row.bot_class,
                                    kind=row.bot_class, args={})
                    seats[row.player_idx] = spec
                    agents[row.player_idx] = build_agent(spec)
        sess = GameSession(game_id=game_id, state=state, seats=seats,
                           agents=agents)
        return sess

    def __setitem__(self, game_id: str, sess: GameSession) -> None:
        self.save(sess)

    def __contains__(self, game_id: str) -> bool:
        with self._sf() as s:
            return s.get(Game, game_id) is not None

    def __len__(self) -> int:
        with self._sf() as s:
            return s.query(Game).count()

    def get(self, game_id: str, default=None):
        try:
            return self[game_id]
        except KeyError:
            return default

    def save(self, sess: GameSession) -> None:
        """Persist the session's state_json. CALLER MUST HOLD THE PER-GAME
        asyncio.Lock (foedus.web.locks.lock_for(game_id)) — this method
        does no concurrency control. Last-write-wins without the lock."""
        with self._sf() as s:
            g = s.get(Game, sess.game_id)
            if g is None:
                raise KeyError(sess.game_id)
            g.state_json = json.dumps(serialize_state(sess.state))
            s.commit()
