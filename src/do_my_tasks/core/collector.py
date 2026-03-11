"""Daily activity collector - orchestrates session parsing and git analysis."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from do_my_tasks.core.git_analyzer import analyze_project
from do_my_tasks.core.session_parser import parse_sessions_for_date
from do_my_tasks.core.task_manager import TaskManager
from do_my_tasks.storage.repository import (
    CommitRepository,
    ProjectRepository,
    SessionRepository,
    UnitOfWork,
)
from do_my_tasks.utils.config import DMTConfig

logger = logging.getLogger("dmt")


class DailyCollector:
    """Orchestrates data collection from all configured projects."""

    def __init__(self, config: DMTConfig, session_factory: sessionmaker[Session]):
        self.config = config
        self.session_factory = session_factory

    def collect(
        self,
        date_str: str,
        project_filter: str | None = None,
    ) -> dict:
        """Collect sessions and commits for all projects on a given date.

        Returns summary dict with counts and errors.
        """
        result = {
            "sessions": 0,
            "commits": 0,
            "projects": 0,
            "errors": [],
        }

        projects = self.config.projects
        if project_filter:
            projects = [p for p in projects if p.name == project_filter]
            if not projects:
                result["errors"].append(f"Project '{project_filter}' not found in config.")
                return result

        # Auto-trigger rollover if needed
        self._maybe_rollover(date_str)

        for project in projects:
            try:
                counts = self._collect_project(project.name, project.path, date_str)
                result["sessions"] += counts["sessions"]
                result["commits"] += counts["commits"]
                result["projects"] += 1
            except Exception as e:
                error_msg = f"{project.name}: {e}"
                logger.warning(f"Error collecting {error_msg}")
                result["errors"].append(error_msg)

        # Also collect sessions not tied to a specific registered project
        try:
            orphan_sessions = self._collect_unregistered_sessions(date_str)
            result["sessions"] += orphan_sessions
        except Exception as e:
            logger.debug(f"Error collecting unregistered sessions: {e}")

        return result

    def _collect_project(self, name: str, path: str, date_str: str) -> dict:
        """Collect data for a single project."""
        counts = {"sessions": 0, "commits": 0}

        with UnitOfWork(self.session_factory) as uow:
            session_repo = SessionRepository(uow.session)
            commit_repo = CommitRepository(uow.session)
            project_repo = ProjectRepository(uow.session)

            # Ensure project exists in DB
            project_repo.upsert(name, path)

            # Parse sessions
            sessions = parse_sessions_for_date(
                self.config.claude_projects_dir,
                date_str,
                project_path=path,
            )
            for session in sessions:
                if not session_repo.exists(session.session_id):
                    session.project_name = name
                    session_repo.save(session, date_str)
                    counts["sessions"] += 1

            # Analyze git commits
            commits = analyze_project(path, name, date_str)
            for commit in commits:
                if not commit_repo.exists(commit.sha):
                    commit_repo.save(commit, date_str)
                    counts["commits"] += 1

            uow.commit()

        return counts

    def _collect_unregistered_sessions(self, date_str: str) -> int:
        """Collect orphan sessions and attribute worktree sessions to parent projects."""
        from do_my_tasks.core.session_parser import _matches_project

        sessions = parse_sessions_for_date(self.config.claude_projects_dir, date_str)

        count = 0
        with UnitOfWork(self.session_factory) as uow:
            session_repo = SessionRepository(uow.session)
            for session in sessions:
                if session_repo.exists(session.session_id):
                    continue

                # Try to match to a registered project (including worktrees)
                dir_name = Path(session.project_path).name
                matched = False
                for proj in self.config.projects:
                    if _matches_project(dir_name, proj.path):
                        matched = True
                        break

                if matched:
                    # Already collected via _collect_project
                    continue

                # Try to attribute worktree sessions to parent project
                # by checking if any registered project path is a prefix
                parent_name = self._find_parent_project(dir_name)
                if parent_name:
                    session.project_name = parent_name

                if not session_repo.exists(session.session_id):
                    session_repo.save(session, date_str)
                    count += 1
            uow.commit()

        return count

    def _find_parent_project(self, encoded_dir_name: str) -> str | None:
        """Find the parent project for a worktree or nested session dir."""
        for proj in self.config.projects:
            encoded_path = proj.path.replace("/", "-")
            # Check if the dir name starts with the project's encoded path
            if encoded_dir_name.startswith(encoded_path):
                return proj.name
        return None

    def _maybe_rollover(self, date_str: str) -> None:
        """Auto-trigger task rollover when collecting for a new day."""
        from datetime import datetime, timedelta

        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        yesterday = (target - timedelta(days=1)).isoformat()

        manager = TaskManager(self.session_factory)
        incomplete = manager.get_incomplete_for_date(yesterday)
        if incomplete:
            rolled = manager.rollover(yesterday, date_str)
            if rolled > 0:
                logger.info(f"Auto-rolled over {rolled} tasks from {yesterday} to {date_str}")
