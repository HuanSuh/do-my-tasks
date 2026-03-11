"""Domain model for Claude Code sessions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, computed_field


class ClaudeSession(BaseModel):
    """Represents a parsed Claude Code session."""

    session_id: str
    project_path: str
    project_name: str
    start_time: datetime
    end_time: datetime | None = None
    message_count: int = 0
    user_message_count: int = 0
    assistant_message_count: int = 0
    tools_used: list[str] = Field(default_factory=list)
    files_accessed: list[str] = Field(default_factory=list)
    models_used: list[str] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cwd: str | None = None
    git_branch: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_minutes(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() / 60
        return 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens
