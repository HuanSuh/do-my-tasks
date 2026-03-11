"""Database engine and session management."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from do_my_tasks.storage.tables import Base, SchemaVersionRow

CURRENT_SCHEMA_VERSION = 1


def get_db_path() -> Path:
    """Get the database file path."""
    db_path = os.environ.get("DMT_DB_PATH")
    if db_path:
        return Path(db_path)
    config_dir = Path.home() / ".config" / "do_my_tasks"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "data.db"


def get_engine(db_path: Path | str | None = None):
    """Create a SQLAlchemy engine."""
    if db_path is None:
        db_path = get_db_path()
    if str(db_path) == ":memory:":
        url = "sqlite:///:memory:"
    else:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
    return create_engine(url, echo=False)


def init_db(db_path: Path | str | None = None) -> sessionmaker[Session]:
    """Initialize database: create tables and return session factory."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)

    factory = sessionmaker(bind=engine)

    # Set schema version if not exists
    with factory() as session:
        existing = session.query(SchemaVersionRow).first()
        if not existing:
            session.add(SchemaVersionRow(version=CURRENT_SCHEMA_VERSION))
            session.commit()

    return factory


# Global session factory - initialized lazily
_session_factory: sessionmaker[Session] | None = None


def get_session_factory(db_path: Path | str | None = None) -> sessionmaker[Session]:
    """Get or create the global session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = init_db(db_path)
    return _session_factory


def reset_session_factory() -> None:
    """Reset the global session factory (for testing)."""
    global _session_factory
    _session_factory = None
