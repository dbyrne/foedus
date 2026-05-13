"""Per-game asyncio.Lock registry.

A module-level singleton mapping `game_id -> asyncio.Lock`. Used by API
handlers to serialize the read-modify-write cycle (load GameSession from
store, mutate via engine call, persist) so concurrent submitters can't
clobber each other. The deadline_worker (Phase 7) takes the same lock.
"""
from __future__ import annotations
import asyncio
from collections import defaultdict


class GameLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def lock(self, game_id: str) -> asyncio.Lock:
        return self._locks[game_id]


_locks = GameLocks()


def lock_for(game_id: str) -> asyncio.Lock:
    return _locks.lock(game_id)
