"""Discord webhook poster.

Best-effort, fire-and-forget. Errors are logged, not raised — a flaky
Discord must never block game progress.
"""
from __future__ import annotations
import logging
from typing import Protocol
import httpx

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify(self, webhook_url: str, message: str) -> None: ...


class NullNotifier:
    """No-op notifier — useful for tests and for games without a Discord URL."""

    def notify(self, webhook_url: str, message: str) -> None:
        pass


class DiscordNotifier:
    """Posts {"content": message} to the webhook URL. Swallows all errors."""

    def notify(self, webhook_url: str | None, message: str) -> None:
        if not webhook_url:
            return
        try:
            r = httpx.post(webhook_url, json={"content": message}, timeout=5.0)
            r.raise_for_status()
        except Exception:
            log.exception("discord webhook failed (%s)", webhook_url[:40])
