"""Game lifecycle helpers: create, advance phases, substitute hold orders.

Expanded in Phase 6. For now only `create_new_game` is implemented.

Cache/lock contracts will be added when the chat/commit/orders handlers
land in Task 6.1.
"""
from __future__ import annotations
import json
import secrets
import string
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from foedus.core import GameConfig, Archetype, Press, Stance
from foedus.resolve import initial_state
from foedus.mapgen import generate_map
from foedus.remote.wire import (
    serialize_state,
    deserialize_intent,
    deserialize_aid_spend,
    deserialize_orders,
)
from foedus.web.models import User, Game, GameSeat, ChatMessage


ALLOWED_BOT_CLASSES = frozenset({
    "foedus.agents.heuristic.HeuristicAgent",
    "foedus.agents.heuristic.HoldAgent",
})


def _new_game_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "g-" + "".join(secrets.choice(alphabet) for _ in range(8))


def create_new_game(session_factory, creator: User, form: dict) -> str:
    """Create a Game + GameSeat rows from a form submission. Returns the
    new game_id. Raises HTTPException(400) if the form is invalid."""
    map_preset_raw = form.get("map_preset", "continental_sweep")
    try:
        archetype = Archetype(map_preset_raw)
    except ValueError:
        raise HTTPException(400, f"unknown map_preset: {map_preset_raw!r}")
    try:
        max_turns = int(form.get("max_turns", "7"))
        dl_raw = form.get("phase_deadline_hours") or ""
        deadline_hours = int(dl_raw) if dl_raw else None
    except ValueError as e:
        raise HTTPException(400, f"invalid integer field: {e}")
    webhook = (form.get("discord_webhook_url") or "").strip() or None
    seed = secrets.randbits(31)

    cfg = GameConfig(num_players=4, max_turns=max_turns, seed=seed,
                     archetype=archetype)
    m = generate_map(4, seed=seed, archetype=archetype)
    state = initial_state(cfg, m)
    gid = _new_game_id()

    with session_factory() as s:
        seats_rows: list[GameSeat] = []
        for i in range(4):
            kind = form.get(f"seat_{i}_kind", "bot")
            if kind == "human":
                login = (form.get(f"seat_{i}_user") or "").strip()
                if not login:
                    raise HTTPException(400, f"seat {i} is human but no GitHub login")
                # Lookup by login first — reconcile with placeholder if it exists.
                u = s.query(User).filter_by(github_login=login).first()
                if u is None:
                    # Create placeholder with NULL github_id; real value filled
                    # on first OAuth login (see foedus.web.auth.callback).
                    u = User(github_id=None, github_login=login)
                    s.add(u); s.flush()
                seats_rows.append(GameSeat(game_id=gid, player_idx=i,
                                           kind="human", user_id=u.id))
            else:
                bot = form.get(f"seat_{i}_bot",
                               "foedus.agents.heuristic.HeuristicAgent")
                if bot not in ALLOWED_BOT_CLASSES:
                    raise HTTPException(400, f"unknown bot_class: {bot!r}")
                seats_rows.append(GameSeat(game_id=gid, player_idx=i,
                                           kind="bot", bot_class=bot))
        deadline_at = (datetime.now(timezone.utc)
                       + timedelta(hours=deadline_hours)) if deadline_hours else None
        g = Game(id=gid, created_by=creator.id, status="active",
                 map_seed=seed, map_preset=map_preset_raw, max_turns=max_turns,
                 phase_deadline_hours=deadline_hours,
                 current_phase_deadline_at=deadline_at,
                 discord_webhook_url=webhook,
                 state_json=json.dumps(serialize_state(state)))
        s.add(g); s.flush()
        s.add_all(seats_rows); s.commit()
    return gid


def handle_chat(session_factory, store, game_id: str, pidx: int,
                body: dict) -> dict:
    """Submit a chat message (and implicit chat-phase done) for player.
    Body schema: {"draft": {"recipients": [int]|None, "body": str} | None}.
    Returns the engine response augmented with the persisted ChatMessage id."""
    draft = body.get("draft")
    sess = store[game_id]
    result = sess.submit_press_chat(pidx, draft)
    # Persist the chat row separately for cheap history rendering.
    if draft and not result.get("message_dropped"):
        recipients = draft.get("recipients")
        mask = -1 if not recipients else sum(1 << int(r) for r in recipients)
        with session_factory() as s:
            s.add(ChatMessage(game_id=game_id, turn=sess.state.turn,
                              sender_idx=pidx, recipients_mask=mask,
                              body=str(draft.get("body", ""))))
            s.commit()
    store.save(sess)
    return result


def handle_commit(session_factory, store, game_id: str, pidx: int,
                  body: dict) -> dict:
    """Final commit: press + orders + implicit signal_done. Auto-advances
    the round if all seats are in. Body schema:
      {"press": {"stance": {idx: "ally|enemy|neutral"}, "intents": [...]},
       "orders": {unit_id: {...}},
       "aid_spends": [...]}
    """
    sess = store[game_id]
    press_raw = body.get("press") or {}

    stance: dict[int, Stance] = {}
    for k, v in (press_raw.get("stance") or {}).items():
        stance[int(k)] = Stance(v)

    intents = [deserialize_intent(it) for it in (press_raw.get("intents") or [])]
    press = Press(stance=stance, intents=intents)

    orders = deserialize_orders(body.get("orders") or {})
    aid_spends_raw = body.get("aid_spends") or []
    aid_spends = [deserialize_aid_spend(x) for x in aid_spends_raw]

    result = sess.submit_press_commit(pidx, press, orders,
                                       aid_spends or None)
    store.save(sess)
    return result


def handle_orders(session_factory, store, game_id: str, pidx: int,
                  body: dict) -> dict:
    """Submit orders for player WITHOUT signaling done — for clients that
    want to set orders before pressing commit. Body schema:
      {"orders": {unit_id: {...}}}
    Most clients use /commit instead. Provided for parity with the upstream
    game_server endpoint."""
    sess = store[game_id]
    orders = deserialize_orders(body.get("orders") or {})
    sess.submit_human_orders(pidx, orders)
    store.save(sess)
    return {"ok": True}
