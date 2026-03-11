"""Rule-based daily summarizer: queries DB and builds DailySummary."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from do_my_tasks.models.commit import GitCommitData
from do_my_tasks.models.report import DailySummary, ProjectSummary
from do_my_tasks.models.session import ClaudeSession
from do_my_tasks.models.task import Task, TaskPriority, TaskStatus
from do_my_tasks.storage.repository import (
    CommitRepository,
    SessionRepository,
    TaskRepository,
    UnitOfWork,
)


class Summarizer:
    """Generates a DailySummary from collected data in the database."""

    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def generate(self, date_str: str) -> DailySummary:
        """Generate a daily summary for the given date."""
        with UnitOfWork(self.session_factory) as uow:
            session_repo = SessionRepository(uow.session)
            commit_repo = CommitRepository(uow.session)
            task_repo = TaskRepository(uow.session)

            session_rows = session_repo.get_by_date(date_str)
            commit_rows = commit_repo.get_by_date(date_str)
            task_rows = task_repo.list_all(date=date_str)

            # Group by project
            project_data: dict[str, ProjectSummary] = {}

            for row in session_rows:
                if row.project_name not in project_data:
                    project_data[row.project_name] = ProjectSummary(
                        project_name=row.project_name,
                        project_path=row.project_path,
                    )
                ps = project_data[row.project_name]
                session = ClaudeSession(
                    session_id=row.session_id,
                    project_path=row.project_path,
                    project_name=row.project_name,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    message_count=row.message_count,
                    user_message_count=row.user_message_count,
                    assistant_message_count=row.assistant_message_count,
                    tools_used=row.tools_used if isinstance(row.tools_used, list) else [],
                    files_accessed=(
                        row.files_accessed if isinstance(row.files_accessed, list) else []
                    ),
                    models_used=row.models_used if isinstance(row.models_used, list) else [],
                    total_input_tokens=row.total_input_tokens,
                    total_output_tokens=row.total_output_tokens,
                )
                ps.sessions.append(session)
                ps.total_session_minutes += row.duration_minutes
                ps.total_input_tokens += row.total_input_tokens
                ps.total_output_tokens += row.total_output_tokens

            for row in commit_rows:
                if row.project_name not in project_data:
                    project_data[row.project_name] = ProjectSummary(
                        project_name=row.project_name,
                        project_path=row.project_path,
                    )
                ps = project_data[row.project_name]
                commit = GitCommitData(
                    sha=row.sha,
                    project_path=row.project_path,
                    project_name=row.project_name,
                    author=row.author,
                    timestamp=row.timestamp,
                    message=row.message,
                    branch=row.branch,
                    files_changed=row.files_changed if isinstance(row.files_changed, list) else [],
                    additions=row.additions,
                    deletions=row.deletions,
                    commit_type=row.commit_type,
                    is_ai_assisted=row.is_ai_assisted,
                )
                ps.commits.append(commit)
                ps.total_additions += row.additions
                ps.total_deletions += row.deletions

            for row in task_rows:
                pname = row.project_name
                if pname not in project_data:
                    project_data[pname] = ProjectSummary(
                        project_name=pname, project_path=""
                    )
                task = Task(
                    id=row.id,
                    task_id=f"T-{row.id:04d}",
                    project_name=row.project_name,
                    title=row.title,
                    description=row.description,
                    status=TaskStatus(row.status),
                    priority=TaskPriority(row.priority),
                    created_date=row.created_date,
                    completed_date=row.completed_date,
                    rollover_count=row.rollover_count,
                    requires_review=row.requires_review,
                    date=row.date,
                )
                project_data[pname].tasks.append(task)

            projects = list(project_data.values())

            # Compute totals
            all_files: set[str] = set()
            total_additions = 0
            total_deletions = 0
            total_minutes = 0.0
            total_input_tokens = 0
            total_output_tokens = 0

            for ps in projects:
                total_additions += ps.total_additions
                total_deletions += ps.total_deletions
                total_minutes += ps.total_session_minutes
                total_input_tokens += ps.total_input_tokens
                total_output_tokens += ps.total_output_tokens
                for c in ps.commits:
                    all_files.update(c.files_changed)

            # Rolled over tasks
            rolled_over = [
                t for ps in projects for t in ps.tasks
                if t.status == TaskStatus.ROLLED_OVER
            ]

            # Build summary text
            summary_text = self._build_summary_text(projects, date_str)

            return DailySummary(
                date=date_str,
                projects=projects,
                rolled_over_tasks=rolled_over,
                total_sessions=len(session_rows),
                total_commits=len(commit_rows),
                total_files_changed=len(all_files),
                total_additions=total_additions,
                total_deletions=total_deletions,
                total_active_minutes=total_minutes,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                summary_text=summary_text,
            )

    def _build_summary_text(self, projects: list[ProjectSummary], date_str: str) -> str:
        """Build a rule-based summary text."""
        if not projects:
            return f"No activity recorded for {date_str}."

        project_names = [p.project_name for p in projects]
        total_commits = sum(len(p.commits) for p in projects)
        total_sessions = sum(len(p.sessions) for p in projects)

        # Collect commit types
        commit_types: dict[str, int] = {}
        for p in projects:
            for c in p.commits:
                commit_types[c.commit_type] = commit_types.get(c.commit_type, 0) + 1

        type_summary = ", ".join(
            f"{count} {t}" for t, count in sorted(commit_types.items(), key=lambda x: -x[1])
        )

        parts = []
        parts.append(
            f"Worked on {len(projects)} project(s): {', '.join(project_names)}."
        )
        if total_commits:
            parts.append(f"{total_commits} commit(s) ({type_summary}).")
        if total_sessions:
            parts.append(f"{total_sessions} Claude session(s).")

        return " ".join(parts)
