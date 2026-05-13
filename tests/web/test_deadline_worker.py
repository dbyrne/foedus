from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from foedus.web.session_store import SqliteSessionStore
from foedus.web.deadline_worker import sweep_once
from foedus.web.models import Game
from tests.web.test_session_store import _make_seed_game


async def test_sweep_advances_expired_game(db):
    """An expired game in NEGOTIATION should have all humans skipped
    through chat and committed with hold-orders, and the deadline reset."""
    with db() as s:
        _make_seed_game(s)
        g = s.get(Game, "g-test")
        g.current_phase_deadline_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        g.phase_deadline_hours = 24   # reset target
        s.commit()
    store = SqliteSessionStore(db)
    count = await sweep_once(db, store)
    assert count == 1
    # Real state change: the game should have advanced (turn increased).
    # Since agents auto-submit and player 0 is forced through, the round
    # completes and we move to turn 1. Player 0 is human so won't be in
    # chat_done/round_done of the new turn (those are agent-only until the
    # human acts in the new round).
    sess = store["g-test"]
    assert sess.state.turn == 1
    # Deadline got reset to the future (~24h from now).
    with db() as s:
        from foedus.web.util import as_utc
        g = s.get(Game, "g-test")
        assert g.current_phase_deadline_at is not None
        assert as_utc(g.current_phase_deadline_at) > datetime.now(timezone.utc)


async def test_sweep_ignores_unexpired_game(db):
    with db() as s:
        _make_seed_game(s)
        g = s.get(Game, "g-test")
        g.current_phase_deadline_at = datetime.now(timezone.utc) + timedelta(hours=1)
        s.commit()
    store = SqliteSessionStore(db)
    count = await sweep_once(db, store)
    assert count == 0


async def test_sweep_ignores_games_without_deadline(db):
    with db() as s:
        _make_seed_game(s)
        g = s.get(Game, "g-test")
        g.current_phase_deadline_at = None
        s.commit()
    store = SqliteSessionStore(db)
    count = await sweep_once(db, store)
    assert count == 0
