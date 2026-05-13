from __future__ import annotations
import json
from foedus.core import GameConfig, Archetype
from foedus.resolve import initial_state
from foedus.mapgen import generate_map
from foedus.game_server.session import GameSession, SeatSpec, build_agent
from foedus.web.models import User, Game, GameSeat
from foedus.web.session_store import SqliteSessionStore

def _make_seed_game(db_session):
    u = User(github_id=1, github_login="alice"); db_session.add(u); db_session.flush()
    cfg = GameConfig(num_players=4, max_turns=5, seed=42,
                     archetype=Archetype.CONTINENTAL_SWEEP)
    m = generate_map(4, seed=42, archetype=Archetype.CONTINENTAL_SWEEP)
    state = initial_state(cfg, m)
    from foedus.remote.wire import serialize_state
    g = Game(id="g-test", created_by=u.id, status="active",
             map_seed=42, map_preset="continental_sweep",
             max_turns=5, state_json=json.dumps(serialize_state(state)))
    db_session.add(g)
    db_session.add_all([
        GameSeat(game_id="g-test", player_idx=0, kind="human", user_id=u.id),
        GameSeat(game_id="g-test", player_idx=1, kind="bot",
                 bot_class="foedus.agents.heuristic.HeuristicAgent"),
        GameSeat(game_id="g-test", player_idx=2, kind="bot",
                 bot_class="foedus.agents.heuristic.HeuristicAgent"),
        GameSeat(game_id="g-test", player_idx=3, kind="bot",
                 bot_class="foedus.agents.heuristic.HeuristicAgent"),
    ])
    db_session.commit()

def test_store_loads_game_from_db(db):
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    sess = store["g-test"]
    assert isinstance(sess, GameSession)
    assert sess.game_id == "g-test"
    assert len(sess.seats) == 4
    assert sess.seats[0].type == "human"
    assert sess.seats[1].type == "agent"

def test_store_missing_raises_keyerror(db):
    store = SqliteSessionStore(db)
    import pytest
    with pytest.raises(KeyError):
        store["nope"]

def test_store_save_roundtrip(db):
    """Save then reload must produce a structurally equal GameState."""
    with db() as s:
        _make_seed_game(s)
    store = SqliteSessionStore(db)
    sess_before = store["g-test"]
    store.save(sess_before)
    sess_after = store["g-test"]
    # Same turn, phase, same units, same ownership.
    assert sess_after.state.turn == sess_before.state.turn
    assert sess_after.state.phase == sess_before.state.phase
    assert set(sess_after.state.units.keys()) == set(sess_before.state.units.keys())
    for uid, u in sess_before.state.units.items():
        assert sess_after.state.units[uid].owner == u.owner
        assert sess_after.state.units[uid].location == u.location
