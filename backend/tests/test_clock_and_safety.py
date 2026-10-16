from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.clock import VirtualClock
from app.core.config import Settings
from app.core.logging import redact
from app.db.session import initialize_database, make_engine


def test_virtual_clock_separates_wall_time_from_accelerated_scenario_time():
    wall = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    monotonic_value = [100.0]
    clock = VirtualClock(
        multiplier=30,
        wall_now=lambda: wall,
        monotonic=lambda: monotonic_value[0],
        virtual_origin=wall,
    )
    monotonic_value[0] += 2
    assert clock.wall_now() == wall
    assert clock.virtual_now() == wall + timedelta(seconds=60)
    assert clock.elapsed_virtual_seconds(wall, wall + timedelta(seconds=600)) == 600


def test_log_redactor_hides_secret_like_fields_and_bearer_tokens():
    output = redact({
        "api_key": "very-secret",
        "message": "Authorization: Bearer abc.def.ghi password=hunter2",
        "nested": {"refresh_token": "refresh-secret"},
    })
    assert output["api_key"] == "[REDACTED]"
    assert "abc.def.ghi" not in output["message"]
    assert "hunter2" not in output["message"]
    assert output["nested"]["refresh_token"] == "[REDACTED]"


def test_database_refuses_unversioned_legacy_tables():
    engine = make_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE legacy_records (id INTEGER PRIMARY KEY)"))
        with pytest.raises(RuntimeError, match="no schema_versions table"):
            initialize_database(engine)
    finally:
        engine.dispose()
