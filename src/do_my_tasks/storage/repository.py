"""Repository classes for data access with UnitOfWork pattern."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from do_my_tasks.models.commit import GitCommitData
from do_my_tasks.models.session import ClaudeSession
from do_my_tasks.models.task import Task, TaskStatus
from do_my_tasks.storage.tables import (
    CollectionStateRow,
    CommitRow,
    DailySummaryRow,
    ProjectRow,
    SessionRow,
    TaskHistoryRow,
    TaskRow,
)


class UnitOfWork:
    """Context manager for database transactions."""

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> UnitOfWork:
        self.session = self._session_factory()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            if exc_type:
                self.session.rollback()
            self.session.close()

    def commit(self):
        if self.session:
            self.session.commit()

    def rollback(self):
        if self.session:
            self.session.rollback()


class ProjectRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(self, name: str, path: str, main_branch: str = "main", slug: str | None = None) -> ProjectRow:
        existing = self.session.query(ProjectRow).filter_by(name=name).first()
        if existing:
            existing.path = path
            existing.main_branch = main_branch
            existing.is_active = True
            if slug is not None:
                existing.slug = slug or None
            return existing
        row = ProjectRow(name=name, path=path, main_branch=main_branch, slug=slug or None)
        self.session.add(row)
        return row

    def list_active(self) -> list[ProjectRow]:
        return self.session.query(ProjectRow).filter_by(is_active=True).all()

    def get_by_name(self, name: str) -> ProjectRow | None:
        return self.session.query(ProjectRow).filter_by(name=name).first()

    def remove(self, name: str) -> bool:
        row = self.session.query(ProjectRow).filter_by(name=name).first()
        if row:
            row.is_active = False
            return True
        return False


class SessionRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(
        self,
        data: ClaudeSession,
        date: str,
        segment_index: int = 0,
    ) -> SessionRow:
        existing = self.session.query(SessionRow).filter_by(
            session_id=data.session_id, segment_index=segment_index
        ).first()
        if existing:
            return existing
        row = SessionRow(
            session_id=data.session_id,
            segment_index=segment_index,
            project_name=data.project_name,
            project_path=data.project_path,
            start_time=data.start_time,
            end_time=data.end_time,
            message_count=data.message_count,
            user_message_count=data.user_message_count,
            assistant_message_count=data.assistant_message_count,
            tools_used=data.tools_used,
            files_accessed=data.files_accessed,
            models_used=data.models_used,
            total_input_tokens=data.total_input_tokens,
            total_output_tokens=data.total_output_tokens,
            duration_minutes=data.duration_minutes,
            cwd=data.cwd,
            git_branch=data.git_branch,
            date=date,
        )
        self.session.add(row)
        return row

    def get_by_date(self, date: str) -> list[SessionRow]:
        return self.session.query(SessionRow).filter_by(date=date).all()

    def get_by_project_and_date(self, project_name: str, date: str) -> list[SessionRow]:
        return (
            self.session.query(SessionRow)
            .filter_by(project_name=project_name, date=date)
            .all()
        )

    def exists(self, session_id: str, segment_index: int = 0) -> bool:
        return (
            self.session.query(SessionRow)
            .filter_by(session_id=session_id, segment_index=segment_index)
            .first()
        ) is not None

    def get_latest_segment(self, session_id: str) -> SessionRow | None:
        """Return the most recently collected segment for a given session_id."""
        return (
            self.session.query(SessionRow)
            .filter_by(session_id=session_id)
            .order_by(SessionRow.segment_index.desc())
            .first()
        )


class CommitRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, data: GitCommitData, date: str) -> CommitRow:
        existing = self.session.query(CommitRow).filter_by(sha=data.sha).first()
        if existing:
            return existing
        row = CommitRow(
            sha=data.sha,
            project_name=data.project_name,
            project_path=data.project_path,
            author=data.author,
            timestamp=data.timestamp,
            message=data.message,
            branch=data.branch,
            files_changed=data.files_changed,
            additions=data.additions,
            deletions=data.deletions,
            commit_type=data.commit_type,
            is_ai_assisted=data.is_ai_assisted,
            date=date,
        )
        self.session.add(row)
        return row

    def get_by_date(self, date: str) -> list[CommitRow]:
        return self.session.query(CommitRow).filter_by(date=date).all()

    def get_by_project_and_date(self, project_name: str, date: str) -> list[CommitRow]:
        return (
            self.session.query(CommitRow)
            .filter_by(project_name=project_name, date=date)
            .all()
        )

    def exists(self, sha: str) -> bool:
        return self.session.query(CommitRow).filter_by(sha=sha).first() is not None


class TaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, task: Task) -> TaskRow:
        row = TaskRow(
            project_name=task.project_name,
            title=task.title,
            description=task.description,
            status=task.status.value,
            priority=task.priority.value,
            created_date=task.created_date,
            source_commit_sha=task.source_commit_sha,
            rollover_count=task.rollover_count,
            requires_review=task.requires_review,
            parent_task_id=task.parent_task_id,
            date=task.date,
        )
        self.session.add(row)
        self.session.flush()  # Get the ID

        # Record history
        history = TaskHistoryRow(
            task_id=row.id,
            action="created",
            new_status=task.status.value,
            to_date=task.date,
        )
        self.session.add(history)
        return row

    def get_by_id(self, task_id: int) -> TaskRow | None:
        return self.session.query(TaskRow).filter_by(id=task_id).first()

    def list_all(
        self,
        project_name: str | None = None,
        status: str | None = None,
        date: str | None = None,
    ) -> list[TaskRow]:
        query = self.session.query(TaskRow)
        if project_name:
            query = query.filter_by(project_name=project_name)
        if status:
            query = query.filter_by(status=status)
        if date:
            query = query.filter_by(date=date)
        return query.order_by(TaskRow.priority, TaskRow.created_date).all()

    def update_status(
        self, task_id: int, new_status: TaskStatus, date: str | None = None
    ) -> TaskRow | None:
        row = self.get_by_id(task_id)
        if not row:
            return None
        old_status = row.status
        row.status = new_status.value
        if new_status == TaskStatus.COMPLETED:
            row.completed_date = datetime.utcnow()

        history = TaskHistoryRow(
            task_id=task_id,
            action="updated",
            old_status=old_status,
            new_status=new_status.value,
            from_date=row.date,
            to_date=date or row.date,
        )
        self.session.add(history)
        return row

    def delete(self, task_id: int) -> bool:
        row = self.get_by_id(task_id)
        if row:
            self.session.delete(row)
            return True
        return False

    def get_incomplete_for_date(self, date: str) -> list[TaskRow]:
        return (
            self.session.query(TaskRow)
            .filter(
                TaskRow.date == date,
                TaskRow.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
            )
            .all()
        )

    def get_stale_tasks(self, min_rollover: int = 3) -> list[TaskRow]:
        return (
            self.session.query(TaskRow)
            .filter(TaskRow.rollover_count >= min_rollover, TaskRow.requires_review)
            .all()
        )


class SummaryRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, date: str, summary_data: dict) -> DailySummaryRow:
        existing = self.session.query(DailySummaryRow).filter_by(date=date).first()
        if existing:
            for key, value in summary_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            return existing
        row = DailySummaryRow(date=date, **summary_data)
        self.session.add(row)
        return row

    def get_by_date(self, date: str) -> DailySummaryRow | None:
        return self.session.query(DailySummaryRow).filter_by(date=date).first()


class CollectionStateRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_state(self, file_path: str) -> CollectionStateRow | None:
        return self.session.query(CollectionStateRow).filter_by(file_path=file_path).first()

    def update_state(
        self, file_path: str, last_modified: float, last_size: int
    ) -> CollectionStateRow:
        existing = self.get_state(file_path)
        if existing:
            existing.last_modified = last_modified
            existing.last_size = last_size
            existing.last_collected_at = datetime.utcnow()
            return existing
        row = CollectionStateRow(
            file_path=file_path,
            last_modified=last_modified,
            last_size=last_size,
        )
        self.session.add(row)
        return row

    def needs_collection(self, file_path: str, current_modified: float, current_size: int) -> bool:
        state = self.get_state(file_path)
        if not state:
            return True
        return state.last_modified < current_modified or state.last_size != current_size
