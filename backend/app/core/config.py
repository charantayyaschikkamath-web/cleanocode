from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def _nested(mapping: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = mapping
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _setting(env_name: str, config: dict[str, Any], path: str, default: Any) -> Any:
    raw = os.getenv(env_name)
    if raw is not None:
        return raw
    return _nested(config, path, default)


def _decimal_value(raw: Any, name: str) -> Decimal | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal number") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a finite, non-negative number")
    return value


def _positive_float(raw: Any, name: str, *, minimum: float = 0.0) -> float:
    try:
        value = float(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= minimum:
        raise ValueError(f"{name} must be greater than {minimum}")
    return value


def _load_config(config_path: str | Path | None) -> dict[str, Any]:
    explicit_path = config_path or os.getenv("CAMPUS_TWIN_CONFIG_FILE")
    path = Path(explicit_path).expanduser() if explicit_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        if explicit_path:
            raise ValueError(f"Configured CampusTwin config file does not exist: {path}")
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to read CampusTwin config file: {path}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("config.yaml root must be a mapping/object")
    return loaded


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "CampusTwin AI API"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str = "sqlite:///./data/campustwin.db"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    virtual_time_multiplier: float = 30.0
    allowed_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    tariff_per_kwh: Decimal | None = None
    co2_factor_kg_per_kwh: Decimal | None = None
    impact_calculation_version: str = "energy-impact-v1"

    @classmethod
    def from_env(cls, config_path: str | Path | None = None) -> "Settings":
        config = _load_config(config_path)
        prefix = str(_setting("CAMPUS_TWIN_API_PREFIX", config, "app.api_prefix", "/api/v1")).strip()
        if not prefix.startswith("/"):
            raise ValueError("CAMPUS_TWIN_API_PREFIX must start with '/'")
        prefix = prefix.rstrip("/") or "/api/v1"

        multiplier_raw = _setting(
            "CAMPUS_TWIN_VIRTUAL_TIME_MULTIPLIER", config, "virtual_time.multiplier", 30
        )
        multiplier = _positive_float(multiplier_raw, "CAMPUS_TWIN_VIRTUAL_TIME_MULTIPLIER")

        origins_raw: Any = _setting(
            "CAMPUS_TWIN_ALLOWED_ORIGINS",
            config,
            "cors.allowed_origins",
            ["http://localhost:5173", "http://127.0.0.1:5173"],
        )
        if isinstance(origins_raw, str):
            origins = tuple(origin.strip().rstrip("/") for origin in origins_raw.split(",") if origin.strip())
        elif isinstance(origins_raw, (list, tuple)):
            origins = tuple(str(origin).strip().rstrip("/") for origin in origins_raw if str(origin).strip())
        else:
            raise ValueError("cors.allowed_origins must be a list or comma-separated string")
        if not origins:
            raise ValueError("CAMPUS_TWIN_ALLOWED_ORIGINS must contain at least one origin")

        database_url = str(_setting(
            "CAMPUS_TWIN_DATABASE_URL", config, "database.url", "sqlite:///./data/campustwin.db"
        )).strip()
        if not database_url:
            raise ValueError("CAMPUS_TWIN_DATABASE_URL cannot be empty")

        log_level = str(_setting("CAMPUS_TWIN_LOG_LEVEL", config, "logging.level", "INFO")).upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("CAMPUS_TWIN_LOG_LEVEL must be a standard logging level")

        return cls(
            app_name=str(_setting("CAMPUS_TWIN_APP_NAME", config, "app.name", "CampusTwin AI API")),
            app_version=str(_setting("CAMPUS_TWIN_APP_VERSION", config, "app.version", "0.1.0")),
            environment=str(_setting("CAMPUS_TWIN_ENVIRONMENT", config, "app.environment", "development")),
            database_url=database_url,
            api_prefix=prefix,
            log_level=log_level,
            virtual_time_multiplier=multiplier,
            allowed_origins=origins,
            tariff_per_kwh=_decimal_value(
                _setting("CAMPUS_TWIN_TARIFF_PER_KWH", config, "impact.tariff_per_kwh", None),
                "CAMPUS_TWIN_TARIFF_PER_KWH",
            ),
            co2_factor_kg_per_kwh=_decimal_value(
                _setting("CAMPUS_TWIN_CO2_FACTOR_KG_PER_KWH", config, "impact.co2_factor_kg_per_kwh", None),
                "CAMPUS_TWIN_CO2_FACTOR_KG_PER_KWH",
            ),
            impact_calculation_version=str(_setting(
                "CAMPUS_TWIN_IMPACT_CALCULATION_VERSION",
                config,
                "impact.calculation_version",
                "energy-impact-v1",
            )),
        )

    def ensure_database_directory(self) -> None:
        """Create a local SQLite parent directory when the configured URL is file-backed."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix) and not self.database_url.startswith("sqlite:////"):
            relative = self.database_url[len(prefix):].split("?", 1)[0]
            if relative and relative not in {":memory:", ":memory"}:
                path = Path(relative)
                if path.parent != Path("."):
                    path.parent.mkdir(parents=True, exist_ok=True)
