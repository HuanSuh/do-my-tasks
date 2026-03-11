"""Domain model for tasks."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, computed_field


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ROLLED_OVER = "rolled_over"


class TaskPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Task(BaseModel):
    """Represents a task."""

    id: int | None = None
    task_id: str = ""  # T-0001 format
    project_name: str
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    created_date: datetime = Field(default_factory=datetime.utcnow)
    completed_date: datetime | None = None
    source_commit_sha: str | None = None
    rollover_count: int = 0
    requires_review: bool = False
    parent_task_id: int | None = None
    date: str = ""  # YYYY-MM-DD for the day this task belongs to

    @computed_field  # type: ignore[prop-decorator]
    @property
    def days_since_created(self) -> int:
        return (datetime.utcnow() - self.created_date).days

    def format_task_id(self, seq: int) -> str:
        return f"T-{seq:04d}"
