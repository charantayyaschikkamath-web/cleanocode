from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.models import SchemaVersion  # noqa: F401 - ensure schema_versions is registered

CURRENT_SCHEMA_VERSION = 1


def make_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        kwargs["connect_args"] = connect_args
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool

    engine = create_engine(database_url, **kwargs)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_connection(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def initialize_database(engine: Engine) -> None:
    """Initialize a fresh database safely and reject unversioned legacy schemas.

    `create_all` is idempotent for a fresh/current schema but does not alter existing
    columns. Refusing an unversioned existing database is safer than silently assuming
    its shape is current. Future schema changes must add explicit versioned migrations.
    """
    inspector = __import__("sqlalchemy").inspect(engine)
    existing_tables = set(inspector.get_table_names())
    has_version_table = "schema_versions" in existing_tables

    if existing_tables and not has_version_table:
        raise RuntimeError(
            "Database has tables but no schema_versions table. Back up the file and run an explicit migration; refusing unsafe implicit initialization."
        )

    if has_version_table:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT MAX(version) FROM schema_versions")).scalar()
        if version is None and existing_tables - {"schema_versions"}:
            raise RuntimeError(
                "Database has application tables but its schema_versions table is empty. Back up the file and perform an explicit migration; refusing unsafe initialization."
            )
        if version is not None and int(version) > CURRENT_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} is newer than this application supports ({CURRENT_SCHEMA_VERSION})."
            )
        if version is not None and int(version) < CURRENT_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} requires a migration to {CURRENT_SCHEMA_VERSION}; no automatic migration is registered."
            )

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        current = connection.execute(text("SELECT MAX(version) FROM schema_versions")).scalar()
        if current is None:
            connection.execute(
                SchemaVersion.__table__.insert().values(
                    version=CURRENT_SCHEMA_VERSION,
                    applied_at=datetime.now(timezone.utc),
                    description="Initial Account 2 core schema",
                )
            )
        if engine.dialect.name == "sqlite":
            # Audit transitions are insert-only at the database boundary, not just by convention.
            connection.execute(text("""
                CREATE TRIGGER IF NOT EXISTS trg_action_transitions_no_update
                BEFORE UPDATE ON action_transitions
                BEGIN SELECT RAISE(ABORT, 'action_transitions are append-only'); END;
            """))
            connection.execute(text("""
                CREATE TRIGGER IF NOT EXISTS trg_action_transitions_no_delete
                BEFORE DELETE ON action_transitions
                BEGIN SELECT RAISE(ABORT, 'action_transitions are append-only'); END;
            """))


def get_session_factory(settings: Settings) -> tuple[Engine, sessionmaker[Session]]:
    settings.ensure_database_directory()
    engine = make_engine(settings.database_url)
    initialize_database(engine)
    return engine, make_session_factory(engine)


def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
