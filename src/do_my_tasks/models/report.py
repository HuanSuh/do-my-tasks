"""Domain model for daily reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from do_my_tasks.models.commit import GitCommitData
from do_my_tasks.models.session import ClaudeSession
from do_my_tasks.models.task import Task


class ProjectSummary(BaseModel):
    """Summary for a single project."""

    project_name: str
    project_path: str
    sessions: list[ClaudeSession] = Field(default_factory=list)
    commits: list[GitCommitData] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    total_session_minutes: float = 0.0
    total_additions: int = 0
    total_deletions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class DailySummary(BaseModel):
    """Complete daily summary across all projects."""

    date: str  # YYYY-MM-DD
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    projects: list[ProjectSummary] = Field(default_factory=list)
    rolled_over_tasks: list[Task] = Field(default_factory=list)
    high_priority_items: list[str] = Field(default_factory=list)
    total_sessions: int = 0
    total_commits: int = 0
    total_files_changed: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    total_active_minutes: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    summary_text: str = ""
