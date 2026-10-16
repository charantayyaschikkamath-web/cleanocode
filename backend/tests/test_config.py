from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings


def test_yaml_defaults_and_environment_overrides(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
app:
  name: Configured CampusTwin
  api_prefix: /v2
database:
  url: sqlite:///./data/config.db
virtual_time:
  multiplier: 12
impact:
  tariff_per_kwh: 7.5
  co2_factor_kg_per_kwh: null
cors:
  allowed_origins: [http://localhost:3000]
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("CAMPUS_TWIN_APP_NAME", raising=False)
    monkeypatch.delenv("CAMPUS_TWIN_API_PREFIX", raising=False)
    monkeypatch.delenv("CAMPUS_TWIN_DATABASE_URL", raising=False)
    monkeypatch.delenv("CAMPUS_TWIN_VIRTUAL_TIME_MULTIPLIER", raising=False)
    monkeypatch.delenv("CAMPUS_TWIN_TARIFF_PER_KWH", raising=False)
    monkeypatch.delenv("CAMPUS_TWIN_CO2_FACTOR_KG_PER_KWH", raising=False)
    monkeypatch.delenv("CAMPUS_TWIN_ALLOWED_ORIGINS", raising=False)

    settings = Settings.from_env(config)
    assert settings.app_name == "Configured CampusTwin"
    assert settings.api_prefix == "/v2"
    assert settings.database_url == "sqlite:///./data/config.db"
    assert settings.virtual_time_multiplier == 12
    assert settings.tariff_per_kwh == Decimal("7.5")
    assert settings.co2_factor_kg_per_kwh is None
    assert settings.allowed_origins == ("http://localhost:3000",)

    monkeypatch.setenv("CAMPUS_TWIN_VIRTUAL_TIME_MULTIPLIER", "5")
    overridden = Settings.from_env(config)
    assert overridden.virtual_time_multiplier == 5
