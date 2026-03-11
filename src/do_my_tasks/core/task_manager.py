"""Task lifecycle management: create, list, update, complete, delete, rollover."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from do_my_tasks.models.task import Task, TaskPriority, TaskStatus
from do_my_tasks.storage.repository import TaskRepository, UnitOfWork
from do_my_tasks.storage.tables import TaskHistoryRow, TaskRow


class TaskManager:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def create(
        self,
        title: str,
        project_name: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        description: str | None = None,
        date: str = "",
        source_commit_sha: str | None = None,
        parent_task_id: int | None = None,
        rollover_count: int = 0,
        requires_review: bool = False,
    ) -> TaskRow:
        task = Task(
            project_name=project_name,
            title=title,
            description=description,
            priority=priority,
            date=date,
            source_commit_sha=source_commit_sha,
            parent_task_id=parent_task_id,
            rollover_count=rollover_count,
            requires_review=requires_review,
        )
        with UnitOfWork(self.session_factory) as uow:
            repo = TaskRepository(uow.session)
            row = repo.create(task)
            uow.commit()
            # Refresh to get the ID
            uow.session.refresh(row)
            return row

    def list(
        self,
        project_name: str | None = None,
        status: str | None = None,
        date: str | None = None,
    ) -> list[TaskRow]:
        with UnitOfWork(self.session_factory) as uow:
            repo = TaskRepository(uow.session)
            rows = repo.list_all(project_name=project_name, status=status, date=date)
            # Detach from session
            uow.session.expunge_all()
            return rows

    def get_stale(self) -> list[TaskRow]:
        with UnitOfWork(self.session_factory) as uow:
            repo = TaskRepository(uow.session)
            rows = repo.get_stale_tasks()
            uow.session.expunge_all()
            return rows

    def update_status(self, task_id: int, new_status: TaskStatus) -> TaskRow | None:
        with UnitOfWork(self.session_factory) as uow:
            repo = TaskRepository(uow.session)
            row = repo.update_status(task_id, new_status)
            if row:
                uow.commit()
                uow.session.refresh(row)
                uow.session.expunge(row)
            return row

    def update_priority(self, task_id: int, new_priority: TaskPriority) -> TaskRow | None:
        with UnitOfWork(self.session_factory) as uow:
            repo = TaskRepository(uow.session)
            row = repo.get_by_id(task_id)
            if row:
                row.priority = new_priority.value
                uow.commit()
                uow.session.refresh(row)
                uow.session.expunge(row)
            return row

    def delete(self, task_id: int) -> bool:
        with UnitOfWork(self.session_factory) as uow:
            repo = TaskRepository(uow.session)
            result = repo.delete(task_id)
            if result:
                uow.commit()
            return result

    def get_incomplete_for_date(self, date: str) -> list[TaskRow]:
        with UnitOfWork(self.session_factory) as uow:
            repo = TaskRepository(uow.session)
            rows = repo.get_incomplete_for_date(date)
            uow.session.expunge_all()
            return rows

    def rollover(self, from_date: str, to_date: str) -> int:
        """Rollover incomplete tasks from from_date to to_date.

        - Mark original tasks as ROLLED_OVER
        - Create new PENDING tasks for to_date
        - Track rollover_count and set requires_review if > 3
        """
        count = 0
        with UnitOfWork(self.session_factory) as uow:
            repo = TaskRepository(uow.session)
            incomplete = repo.get_incomplete_for_date(from_date)

            for task_row in incomplete:
                old_status = task_row.status
                new_rollover_count = task_row.rollover_count + 1

                # Mark original as rolled over
                task_row.status = TaskStatus.ROLLED_OVER.value
                task_row.rollover_count = new_rollover_count

                # Record history for the rollover
                history = TaskHistoryRow(
                    task_id=task_row.id,
                    action="rolled_over",
                    old_status=old_status,
                    new_status=TaskStatus.ROLLED_OVER.value,
                    from_date=from_date,
                    to_date=to_date,
                )
                uow.session.add(history)

                # Create new task for the new date
                new_task = Task(
                    project_name=task_row.project_name,
                    title=task_row.title,
                    description=task_row.description,
                    priority=TaskPriority(task_row.priority),
                    date=to_date,
                    source_commit_sha=task_row.source_commit_sha,
                    parent_task_id=task_row.id,
                    rollover_count=new_rollover_count,
                    requires_review=new_rollover_count > 3,
                )
                repo.create(new_task)
                count += 1

            uow.commit()

        return count
