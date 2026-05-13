from __future__ import annotations
from datetime import datetime, timedelta, timezone
from foedus.web.models import User, Game, GameSeat, ChatMessage, SessionRow

def test_create_user_and_game_with_seats(db):
    with db() as s:
        u = User(github_id=42, github_login="alice")
        s.add(u)
        s.flush()
        g = Game(id="g-1", created_by=u.id, status="pending",
                 map_seed=1, map_preset="CONTINENTAL_SWEEP",
                 max_turns=7, phase_deadline_hours=24,
                 state_json="{}")
        s.add(g)
        s.flush()
        s.add_all([
            GameSeat(game_id="g-1", player_idx=0, kind="human", user_id=u.id),
            GameSeat(game_id="g-1", player_idx=1, kind="bot",
                     bot_class="foedus.agents.heuristic.HeuristicAgent"),
        ])
        s.commit()

    with db() as s:
        g = s.get(Game, "g-1")
        assert g.status == "pending"
        seats = sorted(g.seats, key=lambda x: x.player_idx)
        assert len(seats) == 2
        assert seats[0].kind == "human"
        assert seats[1].bot_class.endswith("HeuristicAgent")

def test_chat_message_roundtrip(db):
    with db() as s:
        u = User(github_id=1, github_login="x"); s.add(u); s.flush()
        s.add(Game(id="g-2", created_by=u.id, status="active", map_seed=0,
                   map_preset="P", max_turns=5, state_json="{}"))
        s.flush()
        s.add(ChatMessage(game_id="g-2", turn=0, sender_idx=0,
                          recipients_mask=-1, body="hi"))
        s.commit()
    with db() as s:
        rows = s.query(ChatMessage).all()
        assert len(rows) == 1 and rows[0].body == "hi"

def test_session_row_expiry(db):
    with db() as s:
        u = User(github_id=9, github_login="z"); s.add(u); s.flush()
        s.add(SessionRow(token="abc", user_id=u.id,
                         expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
        s.commit()
    with db() as s:
        sr = s.get(SessionRow, "abc")
        assert sr.user_id is not None

def test_fk_enforcement_blocks_orphan_seat(db):
    """Step 0's PRAGMA foreign_keys=ON should make orphan inserts fail."""
    import pytest
    from sqlalchemy.exc import IntegrityError
    with db() as s:
        s.add(GameSeat(game_id="nonexistent", player_idx=0,
                       kind="bot",
                       bot_class="foedus.agents.heuristic.HeuristicAgent"))
        with pytest.raises(IntegrityError):
            s.commit()
