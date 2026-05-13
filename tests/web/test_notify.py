from __future__ import annotations
import pytest
from foedus.web.notify import DiscordNotifier, NullNotifier


def test_null_notifier_silent():
    n = NullNotifier()
    n.notify("https://example", "hi")  # no exception


def test_discord_posts(monkeypatch):
    calls = []
    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        class R:
            status_code = 204
            def raise_for_status(self): pass
        return R()
    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    n = DiscordNotifier()
    n.notify("https://example/wh", "your turn in g-1")
    assert calls == [("https://example/wh", {"content": "your turn in g-1"})]


def test_discord_swallows_errors(monkeypatch):
    def fake_post(*a, **kw):
        raise Exception("boom")
    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    DiscordNotifier().notify("u", "msg")  # no exception


def test_discord_skips_empty_url(monkeypatch):
    """An empty webhook_url should be a no-op without any HTTP attempt."""
    posted = []
    def fake_post(*a, **kw):
        posted.append(True)
        return None
    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    DiscordNotifier().notify("", "msg")
    DiscordNotifier().notify(None, "msg")
    assert posted == []
