"""End-to-end: create a game with 2 humans + 2 bots, walk one full turn,
verify the game state advances.

Exercises the full chain: htmx form POST -> driver.create_new_game ->
SqliteSessionStore.save -> /api/v1/games/{gid}/chat -> submit_press_chat ->
/api/v1/games/{gid}/commit -> submit_press_commit -> auto-finalize ->
state.turn increments.
"""
from __future__ import annotations
import json
from fastapi.testclient import TestClient
from foedus.web.app import make_web_app
from foedus.web.auth import create_session
from foedus.web.models import User, Game


def test_two_humans_walk_one_turn(settings, db, monkeypatch):
    monkeypatch.setattr("foedus.web.config.get_settings", lambda: settings)
    app = make_web_app(session_factory_override=db)

    with db() as s:
        u_a = User(github_id=10, github_login="a"); s.add(u_a)
        u_b = User(github_id=11, github_login="b"); s.add(u_b); s.flush()
        tok_a = create_session(s, u_a.id)
        tok_b = create_session(s, u_b.id)
        s.commit()

    with TestClient(app) as c:
        c.cookies.set("foedus_session", tok_a)
        r = c.post("/games", data={
            "map_preset": "continental_sweep", "max_turns": "5",
            "phase_deadline_hours": "24", "discord_webhook_url": "",
            "seat_0_kind": "human", "seat_0_user": "a",
            "seat_1_kind": "human", "seat_1_user": "b",
            "seat_2_kind": "bot",
            "seat_2_bot": "foedus.agents.heuristic.HeuristicAgent",
            "seat_3_kind": "bot",
            "seat_3_bot": "foedus.agents.heuristic.HeuristicAgent",
        }, follow_redirects=False)
        assert r.status_code == 302, r.text
        gid = r.headers["location"].rsplit("/", 1)[-1]

        for tok, pidx in [(tok_a, 0), (tok_b, 1)]:
            c.cookies.set("foedus_session", tok)
            r = c.post(f"/api/v1/games/{gid}/chat", json={"draft": None})
            assert r.status_code == 200, f"chat failed for p{pidx}: {r.text}"

        for tok, pidx in [(tok_a, 0), (tok_b, 1)]:
            c.cookies.set("foedus_session", tok)
            r = c.get(f"/api/v1/games/{gid}/view/{pidx}")
            assert r.status_code == 200, r.text
            view = r.json()
            state = view.get("state", view)
            units = state.get("units", {})
            my_holds = {}
            for uid, unit in units.items():
                if unit.get("owner") == pidx:
                    my_holds[uid] = {"type": "Hold"}
            r = c.post(f"/api/v1/games/{gid}/commit", json={
                "press": {"stance": {}, "intents": []},
                "orders": my_holds,
                "aid_spends": [],
            })
            assert r.status_code == 200, f"commit failed for p{pidx}: {r.text}"
            result = r.json()
            if pidx == 1:
                assert result.get("round_advanced") is True, (
                    f"expected round to advance after p1 commit: {result}")

        with db() as s:
            g = s.get(Game, gid)
            state_json = json.loads(g.state_json)
            assert state_json["turn"] >= 1, (
                f"turn did not advance: turn={state_json['turn']}")
