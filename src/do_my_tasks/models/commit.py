"""Domain model for Git commits."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, computed_field


class GitCommitData(BaseModel):
    """Represents a parsed Git commit."""

    sha: str
    project_path: str
    project_name: str
    author: str
    timestamp: datetime
    message: str
    branch: str
    files_changed: list[str] = []
    additions: int = 0
    deletions: int = 0
    commit_type: str = "other"
    is_ai_assisted: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions

    @computed_field  # type: ignore[prop-decorator]
    @property
    def impact_score(self) -> float:
        """Change impact score (0-100)."""
        return min(100.0, self.total_changes / 10)
