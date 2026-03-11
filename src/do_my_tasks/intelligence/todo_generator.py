"""TODO generator for dmt plan: combines rollover tasks, high priority items, and follow-ups."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from do_my_tasks.intelligence.priority_analyzer import PriorityAnalyzer
from do_my_tasks.models.commit import GitCommitData
from do_my_tasks.models.task import Task, TaskPriority, TaskStatus
from do_my_tasks.storage.repository import CommitRepository, TaskRepository, UnitOfWork
from do_my_tasks.utils.config import DMTConfig


@dataclass
class PlanItems:
    """Collection of plan items for the day."""

    rolled_over: list[Task] = field(default_factory=list)
    high_priority: list[str] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)

    def has_items(self) -> bool:
        return bool(self.rolled_over or self.high_priority or self.follow_ups)


class TodoGenerator:
    """Generates TODO list combining multiple sources."""

    def __init__(self, session_factory: sessionmaker[Session], config: DMTConfig):
        self.session_factory = session_factory
        self.config = config
        self.priority_analyzer = PriorityAnalyzer(config.scoring)

    def generate(self, date_str: str) -> PlanItems:
        """Generate plan items for the given date."""
        items = PlanItems()

        with UnitOfWork(self.session_factory) as uow:
            task_repo = TaskRepository(uow.session)
            commit_repo = CommitRepository(uow.session)

            # 1. Rolled over tasks (pending/in_progress for this date with rollover_count > 0)
            all_tasks = task_repo.list_all(date=date_str)
            for row in all_tasks:
                if row.status in (TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value):
                    task = Task(
                        id=row.id,
                        task_id=f"T-{row.id:04d}",
                        project_name=row.project_name,
                        title=row.title,
                        description=row.description,
                        status=TaskStatus(row.status),
                        priority=TaskPriority(row.priority),
                        created_date=row.created_date,
                        rollover_count=row.rollover_count,
                        requires_review=row.requires_review,
                        date=row.date,
                    )
                    if row.rollover_count > 0:
                        items.rolled_over.append(task)

            # 2. High priority items from recent commits
            commit_rows = commit_repo.get_by_date(date_str)
            commits = [
                GitCommitData(
                    sha=r.sha,
                    project_path=r.project_path,
                    project_name=r.project_name,
                    author=r.author,
                    timestamp=r.timestamp,
                    message=r.message,
                    branch=r.branch,
                    files_changed=r.files_changed if isinstance(r.files_changed, list) else [],
                    additions=r.additions,
                    deletions=r.deletions,
                    commit_type=r.commit_type,
                    is_ai_assisted=r.is_ai_assisted,
                )
                for r in commit_rows
            ]

            if commits:
                results = self.priority_analyzer.score_commits(commits)
                for commit, result in zip(commits, results):
                    if result.priority == TaskPriority.HIGH:
                        short_msg = commit.message.split("\n")[0][:80]
                        items.high_priority.append(
                            f"[{commit.project_name}] {short_msg} - {result.explanation}"
                        )

            # 3. Auto-detect follow-ups from commit patterns
            items.follow_ups = self._detect_follow_ups(commits)

        return items

    def _detect_follow_ups(self, commits: list[GitCommitData]) -> list[str]:
        """Detect suggested follow-up actions from commit patterns."""
        follow_ups: list[str] = []

        for commit in commits:
            # Check for new files without tests
            has_tests = any("test" in f.lower() for f in commit.files_changed)

            if commit.commit_type == "feat" and not has_tests:
                follow_ups.append(
                    f"[{commit.project_name}] Add tests for: "
                    f"{commit.message.split(chr(10))[0][:60]}"
                )

            # Large changes that might need docs
            if commit.total_changes > 300 and commit.commit_type != "docs":
                follow_ups.append(
                    f"[{commit.project_name}] Consider documenting large change: "
                    f"{commit.message.split(chr(10))[0][:60]}"
                )

        return follow_ups

    def save_as_tasks(self, items: PlanItems, date_str: str) -> int:
        """Save plan items as tasks in the database."""
        from do_my_tasks.core.task_manager import TaskManager

        manager = TaskManager(self.session_factory)
        saved = 0

        for item_text in items.high_priority:
            # Extract project name from [project_name] prefix
            project = "general"
            title = item_text
            if item_text.startswith("["):
                end = item_text.index("]")
                project = item_text[1:end]
                title = item_text[end + 2:]

            manager.create(
                title=title,
                project_name=project,
                priority=TaskPriority.HIGH,
                date=date_str,
            )
            saved += 1

        for item_text in items.follow_ups:
            project = "general"
            title = item_text
            if item_text.startswith("["):
                end = item_text.index("]")
                project = item_text[1:end]
                title = item_text[end + 2:]

            manager.create(
                title=title,
                project_name=project,
                priority=TaskPriority.MEDIUM,
                date=date_str,
            )
            saved += 1

        return saved
