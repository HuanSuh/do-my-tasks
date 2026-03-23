"""Database engine and session management."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from do_my_tasks.storage.tables import Base, SchemaVersionRow

logger = logging.getLogger("dmt")

CURRENT_SCHEMA_VERSION = 2


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


def _get_schema_version(session) -> int:
    try:
        row = session.query(SchemaVersionRow).first()
        return row.version if row else 0
    except Exception:
        return 0


def _migrate_v1_to_v2(engine) -> None:
    """Migrate sessions table: add segment_index, remove unique on session_id."""
    logger.info("Migrating schema from v1 to v2: adding session segment tracking")
    with engine.connect() as conn:
        # Check if segment_index column already exists
        result = conn.execute(text("PRAGMA table_info(sessions)"))
        cols = {row[1] for row in result}
        if "segment_index" in cols:
            logger.debug("segment_index column already exists, skipping table rebuild")
            return

        # Recreate sessions table without unique constraint on session_id
        conn.execute(text("""
            CREATE TABLE sessions_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(255) NOT NULL,
                segment_index INTEGER NOT NULL DEFAULT 0,
                project_name VARCHAR(255) NOT NULL,
                project_path VARCHAR(1024) NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                message_count INTEGER DEFAULT 0,
                user_message_count INTEGER DEFAULT 0,
                assistant_message_count INTEGER DEFAULT 0,
                tools_used JSON DEFAULT '[]',
                files_accessed JSON DEFAULT '[]',
                models_used JSON DEFAULT '[]',
                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                duration_minutes FLOAT DEFAULT 0.0,
                cwd VARCHAR(1024),
                git_branch VARCHAR(255),
                date VARCHAR(10) NOT NULL,
                collected_at DATETIME,
                CONSTRAINT uq_session_segment UNIQUE (session_id, segment_index)
            )
        """))
        conn.execute(text("""
            INSERT INTO sessions_v2 (
                id, session_id, segment_index, project_name, project_path,
                start_time, end_time, message_count, user_message_count,
                assistant_message_count, tools_used, files_accessed, models_used,
                total_input_tokens, total_output_tokens, duration_minutes,
                cwd, git_branch, date, collected_at
            )
            SELECT
                id, session_id, 0, project_name, project_path,
                start_time, end_time, message_count, user_message_count,
                assistant_message_count, tools_used, files_accessed, models_used,
                total_input_tokens, total_output_tokens, duration_minutes,
                cwd, git_branch, date, collected_at
            FROM sessions
        """))
        conn.execute(text("DROP TABLE sessions"))
        conn.execute(text("ALTER TABLE sessions_v2 RENAME TO sessions"))
        conn.commit()
    logger.info("Schema migration v1→v2 complete")


def init_db(db_path: Path | str | None = None) -> sessionmaker[Session]:
    """Initialize database: create tables, run migrations, return session factory."""
    engine = get_engine(db_path)

    factory = sessionmaker(bind=engine)

    with factory() as session:
        current_version = _get_schema_version(session)

    # Run migrations
    if current_version < 2:
        if current_version == 1:
            _migrate_v1_to_v2(engine)
        # Fresh DB: create all tables
        Base.metadata.create_all(engine)

        with factory() as session:
            existing = session.query(SchemaVersionRow).first()
            if not existing:
                session.add(SchemaVersionRow(version=CURRENT_SCHEMA_VERSION))
            else:
                existing.version = CURRENT_SCHEMA_VERSION
            session.commit()
    else:
        # Ensure any new tables are created
        Base.metadata.create_all(engine)

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
