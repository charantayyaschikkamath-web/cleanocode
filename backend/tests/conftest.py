from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
import os

# A module-level app is imported below; keep its default DB process-local so test collection
# can never create or mutate the developer's configured application database.
os.environ.setdefault("CAMPUS_TWIN_DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import initialize_database, make_engine, make_session_factory
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        api_prefix="/api/v1",
        virtual_time_multiplier=30,
        allowed_origins=("http://localhost:5173",),
        tariff_per_kwh=None,
        co2_factor_kg_per_kwh=None,
    )


@pytest.fixture
def engine():
    engine = make_engine("sqlite://")
    initialize_database(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def app(settings, engine):
    return create_app(settings=settings, engine=engine)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session_factory(engine):
    return make_session_factory(engine)


@pytest.fixture
def db_session(session_factory) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
