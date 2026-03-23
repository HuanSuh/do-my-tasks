"""Daily activity collector - orchestrates session parsing and git analysis."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from do_my_tasks.core.git_analyzer import analyze_project
from do_my_tasks.core.session_parser import (
    _to_local_date_str,
    find_session_files,
    parse_session_file_after,
    parse_sessions_for_date,
)
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

            # Parse sessions starting on date_str
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

            # Detect resume segments for existing sessions
            counts["sessions"] += self._collect_resume_segments(
                name, path, date_str, session_repo
            )

            # Analyze git commits
            commits = analyze_project(path, name, date_str)
            for commit in commits:
                if not commit_repo.exists(commit.sha):
                    commit_repo.save(commit, date_str)
                    counts["commits"] += 1

            uow.commit()

        return counts

    def _collect_resume_segments(
        self,
        project_name: str,
        project_path: str | None,
        date_str: str,
        session_repo: "SessionRepository",
    ) -> int:
        """Detect new activity appended to already-collected session files.

        When a user runs `claude --resume <uuid>`, new messages are appended to the
        existing JSONL. This method finds those new messages and saves them as a
        separate segment row (segment_index > 0) so they appear in the correct date.
        """
        files = find_session_files(self.config.claude_projects_dir, project_path=project_path)
        count = 0

        for file_path in files:
            stem = file_path.stem
            if stem.startswith("agent-"):
                continue

            # Find the latest already-collected segment for this file
            latest = session_repo.get_latest_segment(stem)
            # Also check by sessionId (the file stem may differ from the stored session_id)
            # We try stem first since it's cheaper; full lookup happens inside get_latest_segment
            if latest is None:
                continue  # Not collected yet — handled by parse_sessions_for_date
            if latest.end_time is None:
                continue

            # Parse only messages after the latest collected end_time
            new_seg = parse_session_file_after(file_path, latest.end_time)
            if new_seg is None:
                continue

            # Only count this segment if its activity starts on date_str
            seg_date = _to_local_date_str(new_seg.start_time)
            if seg_date != date_str:
                continue

            next_index = latest.segment_index + 1
            if session_repo.exists(new_seg.session_id, segment_index=next_index):
                continue

            new_seg.project_name = project_name
            if project_path:
                new_seg.project_path = project_path
            session_repo.save(new_seg, date_str, segment_index=next_index)
            logger.info(
                f"Collected resume segment {next_index} for session "
                f"{new_seg.session_id[:8]}… ({project_name})"
            )
            count += 1

        return count

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

            # Also detect resume segments for unregistered sessions
            count += self._collect_resume_segments(None, None, date_str, session_repo)

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
