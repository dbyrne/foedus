from __future__ import annotations
from fastapi.testclient import TestClient
from foedus.web.app import make_web_app


def test_app_boots_and_healthz(settings, db, monkeypatch):
    monkeypatch.setattr("foedus.web.config.get_settings", lambda: settings)
    app = make_web_app(session_factory_override=db)
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["ok"] is True
