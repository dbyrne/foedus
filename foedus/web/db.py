"""SQLAlchemy engine + session factory + Declarative Base."""
from __future__ import annotations
from sqlalchemy import create_engine, Engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Base(DeclarativeBase):
    pass

def _enable_sqlite_fks(dbapi_connection, connection_record):
    # No-op for non-sqlite backends; the cursor() succeeds and the
    # PRAGMA is silently ignored on PG/MySQL.
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass

def make_engine(database_url: str) -> Engine:
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    event.listen(engine, "connect", _enable_sqlite_fks)
    return engine

def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
