"""SQLAlchemy ORM table definitions (Row suffix to avoid confusion with domain models)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SchemaVersionRow(Base):
    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    main_branch: Mapped[str] = mapped_column(String(255), default="main")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    user_message_count: Mapped[int] = mapped_column(Integer, default=0)
    assistant_message_count: Mapped[int] = mapped_column(Integer, default=0)
    tools_used: Mapped[str] = mapped_column(JSON, default="[]")
    files_accessed: Mapped[str] = mapped_column(JSON, default="[]")
    models_used: Mapped[str] = mapped_column(JSON, default="[]")
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    cwd: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    git_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CommitRow(Base):
    __tablename__ = "commits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str] = mapped_column(String(255), default="")
    files_changed: Mapped[str] = mapped_column(JSON, default="[]")
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    commit_type: Mapped[str] = mapped_column(String(50), default="other")
    is_ai_assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    priority: Mapped[str] = mapped_column(String(50), default="medium")
    created_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rollover_count: Mapped[int] = mapped_column(Integer, default=0)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD


class TaskHistoryRow(Base):
    __tablename__ = "task_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # action: created, updated, rolled_over, completed
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    from_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    to_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailySummaryRow(Base):
    __tablename__ = "daily_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_commits: Mapped[int] = mapped_column(Integer, default=0)
    total_files_changed: Mapped[int] = mapped_column(Integer, default=0)
    total_additions: Mapped[int] = mapped_column(Integer, default=0)
    total_deletions: Mapped[int] = mapped_column(Integer, default=0)
    total_active_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    summary_text: Mapped[str] = mapped_column(Text, default="")
    report_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CollectionStateRow(Base):
    """Tracks last collection state for incremental processing."""

    __tablename__ = "collection_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    last_modified: Mapped[float] = mapped_column(Float, nullable=False)
    last_size: Mapped[int] = mapped_column(Integer, nullable=False)
    last_collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
