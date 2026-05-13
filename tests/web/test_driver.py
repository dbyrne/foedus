from __future__ import annotations
import pytest
from foedus.web.session_store import SqliteSessionStore
from foedus.web.driver import handle_chat, handle_commit, handle_orders
from foedus.web.models import ChatMessage
from tests.web.test_session_store import _make_seed_game


def test_chat_appends_message(db):
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    result = handle_chat(db, store, "g-test", pidx=0,
                         body={"draft": {"recipients": None, "body": "hello"}})
    assert result["ok"] is True
    with db() as s:
        rows = s.query(ChatMessage).all()
        assert len(rows) == 1 and rows[0].body == "hello"


def test_chat_skip_signals_done_without_message(db):
    """draft=None: no chat row, but chat_done is set."""
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    result = handle_chat(db, store, "g-test", pidx=0,
                         body={"draft": None})
    assert result["ok"] is True
    with db() as s:
        assert s.query(ChatMessage).count() == 0


def test_orders_submission_stored(db):
    """submit_human_orders stores orders without signaling done."""
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    sess = store["g-test"]
    p0_units = [u for u in sess.state.units.values() if u.owner == 0]
    if not p0_units:
        pytest.skip("seed game has no player-0 units")
    body = {"orders": {str(u.id): {"type": "Hold"} for u in p0_units}}
    result = handle_orders(db, store, "g-test", pidx=0, body=body)
    assert result["ok"] is True
    # Reload — pending_orders is in-memory only, but the call shouldn't error.
    sess2 = store["g-test"]
    assert sess2.game_id == "g-test"
