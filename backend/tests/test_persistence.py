from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import make_engine
from app.main import create_app


def test_file_database_survives_app_restart(tmp_path):
    db_path = tmp_path / "persist.db"
    url = f"sqlite:///{db_path.as_posix()}"
    settings = Settings(database_url=url, allowed_origins=("http://localhost:5173",), virtual_time_multiplier=30)

    engine_one = make_engine(url)
    app_one = create_app(settings=settings, engine=engine_one)
    with TestClient(app_one) as client:
        create = client.post("/api/v1/buildings", json={"name": "Persisted Block", "code": "PERSIST-1"})
        assert create.status_code == 201, create.text
        building_id = create.json()["id"]
    engine_one.dispose()

    engine_two = make_engine(url)
    app_two = create_app(settings=settings, engine=engine_two)
    with TestClient(app_two) as client:
        listed = client.get("/api/v1/buildings")
        assert listed.status_code == 200
        assert any(row["id"] == building_id for row in listed.json())
        assert client.get(f"/api/v1/buildings/{building_id}").json()["name"] == "Persisted Block"
    engine_two.dispose()
