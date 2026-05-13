"""Background asyncio task: every N seconds, advance games whose phase
deadline has passed.

For each expired game (active, deadline in the past):
  1. Take the per-game asyncio.Lock.
  2. If chat phase is NOT complete, skip chat for every active human
     still in chat (calls submit_press_chat(player, None)).
  3. If now waiting on round_done (orders), submit a Hold-everything
     commit for every active human who hasn't committed.
  4. submit_press_commit auto-finalizes when the round completes, so
     no separate advance call is needed.
  5. Reset current_phase_deadline_at to now + phase_deadline_hours
     (or None if no deadline configured).
  6. If the game terminated (state.is_terminal()), mark status='finished'
     and set finished_at.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from foedus.core import Hold, Press, Phase
from foedus.web.locks import lock_for
from foedus.web.models import Game
from foedus.web.session_store import SqliteSessionStore

log = logging.getLogger(__name__)


async def sweep_once(session_factory, store: SqliteSessionStore) -> int:
    """Advance every game whose deadline has passed. Returns count advanced."""
    now = datetime.now(timezone.utc)
    with session_factory() as s:
        rows = (s.query(Game.id, Game.current_phase_deadline_at)
                .filter(Game.status == "active",
                        Game.current_phase_deadline_at.is_not(None))
                .all())
    expired_ids: list[str] = []
    from foedus.web.util import as_utc
    for gid, deadline in rows:
        if as_utc(deadline) < now:
            expired_ids.append(gid)

    advanced = 0
    for gid in expired_ids:
        async with lock_for(gid):
            try:
                if _force_advance(session_factory, store, gid):
                    advanced += 1
            except Exception:
                log.exception("force-advance failed for %s", gid)
    return advanced


def _force_advance(session_factory, store: SqliteSessionStore, gid: str) -> bool:
    """Force the game past its current phase boundary. Returns True if any
    state change was attempted."""
    sess = store[gid]
    num_players = sess.state.config.num_players

    # Phase 1: skip chat for humans who haven't signaled chat_done.
    if sess.state.phase == Phase.NEGOTIATION:
        for pidx in range(num_players):
            if not sess.is_human(pidx):
                continue
            if not sess.is_active(pidx):
                continue
            if pidx in sess.state.chat_done:
                continue
            sess.submit_press_chat(pidx, draft=None)

    # Phase 2: commit hold-orders for humans still missing from round_done.
    # submit_press_commit requires chat phase complete — after the loop above
    # all active humans have signaled chat_done.
    for pidx in range(num_players):
        if not sess.is_human(pidx):
            continue
        if not sess.is_active(pidx):
            continue
        if pidx in sess.state.round_done:
            continue
        holds = {u.id: Hold() for u in sess.state.units.values()
                 if u.owner == pidx}
        sess.submit_press_commit(pidx, Press(stance={}, intents=[]),
                                 holds, None)
        # submit_press_commit auto-finalizes the round + calls init_round
        # if everyone is in, so the state may now be a NEW turn.

    store.save(sess)

    # Reset the deadline window relative to now.
    with session_factory() as s:
        g = s.get(Game, gid)
        if g.phase_deadline_hours:
            g.current_phase_deadline_at = (datetime.now(timezone.utc)
                                           + timedelta(hours=g.phase_deadline_hours))
        if sess.state.is_terminal():
            g.status = "finished"
            g.finished_at = datetime.now(timezone.utc)
        s.commit()
    return True


async def run_worker(session_factory, store: SqliteSessionStore,
                     tick_seconds: int = 60) -> None:
    """Long-running task started by the app lifespan."""
    log.info("deadline worker starting; tick=%ds", tick_seconds)
    while True:
        try:
            n = await sweep_once(session_factory, store)
            if n:
                log.info("deadline worker advanced %d game(s)", n)
        except Exception:
            log.exception("deadline worker tick failed")
        await asyncio.sleep(tick_seconds)
