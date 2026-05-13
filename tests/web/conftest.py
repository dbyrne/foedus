from __future__ import annotations
import pytest
from pathlib import Path
from foedus.web.config import Settings
from foedus.web.db import make_engine, make_session_factory, Base

@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path}/test.db",
                    session_secret="test", jwt_secret="test-jwt")

@pytest.fixture
def db(settings: Settings):
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)
    yield SessionLocal
    Base.metadata.drop_all(engine)
    engine.dispose()
