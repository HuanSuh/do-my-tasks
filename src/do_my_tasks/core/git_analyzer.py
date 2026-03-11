"""Git commit analyzer using GitPython.

Extracts commits for a given date range, parses conventional commit types,
and calculates file change statistics.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from do_my_tasks.models.commit import GitCommitData

logger = logging.getLogger("dmt")

# Conventional commit type pattern
CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[^)]+)\))?\s*!?\s*:\s*(?P<description>.+)",
    re.IGNORECASE,
)

CO_AUTHORED_RE = re.compile(r"Co-Authored-By:.*Claude", re.IGNORECASE)


def analyze_project(
    project_path: str,
    project_name: str,
    date_str: str,
    main_branch: str = "main",
) -> list[GitCommitData]:
    """Analyze Git commits for a project on a given date.

    Args:
        project_path: Path to the Git repository
        project_name: Human-readable project name
        date_str: Date in YYYY-MM-DD format
        main_branch: Main branch name for reference
    """
    try:
        import git
    except ImportError:
        logger.warning("GitPython not installed, skipping git analysis")
        return []

    repo_path = Path(project_path)
    if not repo_path.exists():
        logger.warning(f"Project path does not exist: {project_path}")
        return []

    if not (repo_path / ".git").exists():
        logger.debug(f"Not a git repository: {project_path}")
        return []

    try:
        repo = git.Repo(project_path)
    except git.InvalidGitRepositoryError:
        logger.warning(f"Invalid git repository: {project_path}")
        return []

    # Parse date range (local timezone)
    target_date = datetime.strptime(date_str, "%Y-%m-%d")
    since = target_date.replace(hour=0, minute=0, second=0)
    until = since + timedelta(days=1)

    # Get current branch
    try:
        current_branch = repo.active_branch.name
    except (TypeError, ValueError):
        current_branch = "HEAD"

    commits: list[GitCommitData] = []

    try:
        for commit in repo.iter_commits(
            all=True,
            since=since.isoformat(),
            until=until.isoformat(),
        ):
            commit_data = _parse_commit(commit, project_path, project_name, current_branch)
            if commit_data:
                commits.append(commit_data)
    except Exception as e:
        logger.warning(f"Error reading git log for {project_name}: {e}")

    return commits


def _parse_commit(
    commit,
    project_path: str,
    project_name: str,
    branch: str,
) -> GitCommitData | None:
    """Parse a single git commit into GitCommitData."""
    try:
        message = commit.message.strip()
        commit_type = _parse_commit_type(message)
        is_ai = bool(CO_AUTHORED_RE.search(message))

        # Get file changes
        files_changed: list[str] = []
        additions = 0
        deletions = 0

        try:
            stats = commit.stats
            files_changed = list(stats.files.keys())
            for file_stats in stats.files.values():
                additions += file_stats.get("insertions", 0)
                deletions += file_stats.get("deletions", 0)
        except Exception:
            # stats can fail on some commits (e.g., initial commit)
            pass

        # Convert timestamp to UTC
        authored_dt = commit.authored_datetime
        if authored_dt.tzinfo is None:
            authored_dt = authored_dt.replace(tzinfo=UTC)

        return GitCommitData(
            sha=commit.hexsha,
            project_path=project_path,
            project_name=project_name,
            author=str(commit.author),
            timestamp=authored_dt,
            message=message,
            branch=branch,
            files_changed=files_changed,
            additions=additions,
            deletions=deletions,
            commit_type=commit_type,
            is_ai_assisted=is_ai,
        )
    except Exception as e:
        logger.debug(f"Failed to parse commit {commit.hexsha[:8]}: {e}")
        return None


def _parse_commit_type(message: str) -> str:
    """Parse conventional commit type from message."""
    first_line = message.split("\n")[0]
    match = CONVENTIONAL_COMMIT_RE.match(first_line)
    if match:
        return match.group("type").lower()
    return "other"
