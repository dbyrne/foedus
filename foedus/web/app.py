"""FastAPI app factory. Wires session middleware, COOP/COEP, pages, API,
deadline worker, and the SqliteSessionStore."""
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from foedus.web.config import get_settings
from foedus.web.db import make_engine, make_session_factory, Base
from foedus.web.auth import install_session_middleware
from foedus.web.coop_coep import COOPCOEPMiddleware
from foedus.web.routes.pages import install_pages
from foedus.web.routes.api import install_api
from foedus.web.session_store import SqliteSessionStore
from foedus.web.deadline_worker import run_worker

log = logging.getLogger(__name__)


def make_web_app(session_factory_override=None) -> FastAPI:
    settings = get_settings()

    is_local = (settings.base_url.startswith("http://localhost")
                or settings.base_url.startswith("http://127.0.0.1"))
    if not is_local:
        if not settings.session_secret or settings.session_secret == "dev-only-change-me":
            raise RuntimeError("FOEDUS_SESSION_SECRET must be set in production")
        if not settings.jwt_secret or settings.jwt_secret == "dev-only-change-me-jwt":
            raise RuntimeError("FOEDUS_JWT_SECRET must be set in production")

    if session_factory_override is not None:
        SessionLocal = session_factory_override
    else:
        engine = make_engine(settings.database_url)
        Base.metadata.create_all(engine)
        SessionLocal = make_session_factory(engine)
    store = SqliteSessionStore(SessionLocal)

    from foedus.web.notify import DiscordNotifier
    notifier = DiscordNotifier()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(run_worker(
            SessionLocal, store, tick_seconds=settings.deadline_tick_seconds,
            notifier=notifier))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("deadline worker crashed during shutdown")

    app = FastAPI(title="foedus web", version="0.1.0", lifespan=lifespan)
    app.add_middleware(COOPCOEPMiddleware)
    install_session_middleware(app, settings, SessionLocal)
    install_pages(app, SessionLocal)
    install_api(app, SessionLocal, store, settings, notifier=notifier)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
