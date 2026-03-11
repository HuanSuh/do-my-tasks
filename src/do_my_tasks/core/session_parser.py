"""JSONL session parser for Claude Code sessions.

Parses ~/.claude/projects/*/*.jsonl files line by line (streaming).
Supports message types: user, assistant, file-history-snapshot.
Extracts: message counts, tools used, files accessed, timestamps, token usage.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from do_my_tasks.models.session import ClaudeSession

logger = logging.getLogger("dmt")

# Tool names we track from assistant content blocks
TOOL_USE_TYPE = "tool_use"


def parse_session_file(file_path: Path) -> ClaudeSession | None:
    """Parse a single JSONL session file into a ClaudeSession.

    Streams line by line to avoid loading entire file into memory.
    Skips malformed JSON lines with a warning.
    """
    session_id = file_path.stem  # UUID filename without extension
    # Skip agent files
    if session_id.startswith("agent-"):
        return None

    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    tools_used: set[str] = set()
    files_accessed: set[str] = set()
    models_used: set[str] = set()
    total_input_tokens = 0
    total_output_tokens = 0
    user_count = 0
    assistant_count = 0
    cwd: str | None = None
    git_branch: str | None = None
    found_session_id: str | None = None

    try:
        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(f"Skipping malformed JSON at {file_path}:{line_num}")
                    continue

                msg_type = entry.get("type")
                timestamp_str = entry.get("timestamp")

                if timestamp_str:
                    try:
                        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        if first_timestamp is None or ts < first_timestamp:
                            first_timestamp = ts
                        if last_timestamp is None or ts > last_timestamp:
                            last_timestamp = ts
                    except (ValueError, AttributeError):
                        pass

                # Extract session ID
                if not found_session_id and entry.get("sessionId"):
                    found_session_id = entry["sessionId"]

                # Extract cwd and git branch
                if not cwd and entry.get("cwd"):
                    cwd = entry["cwd"]
                if git_branch is None and "gitBranch" in entry:
                    git_branch = entry["gitBranch"]

                if msg_type == "user":
                    # Skip meta/command messages
                    if entry.get("isMeta"):
                        continue
                    user_count += 1

                elif msg_type == "assistant":
                    assistant_count += 1
                    message = entry.get("message", {})

                    # Extract model
                    model = message.get("model")
                    if model:
                        models_used.add(model)

                    # Extract token usage
                    usage = message.get("usage", {})
                    total_input_tokens += usage.get("input_tokens", 0)
                    total_input_tokens += usage.get("cache_read_input_tokens", 0)
                    total_output_tokens += usage.get("output_tokens", 0)

                    # Extract tools and files from content blocks
                    content = message.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == TOOL_USE_TYPE:
                                tool_name = block.get("name", "")
                                if tool_name:
                                    tools_used.add(tool_name)
                                # Extract file paths from tool inputs
                                tool_input = block.get("input", {})
                                if isinstance(tool_input, dict):
                                    for key in ("file_path", "path", "command"):
                                        val = tool_input.get(key)
                                        if val and isinstance(val, str) and "/" in val:
                                            files_accessed.add(val)

                elif msg_type == "file-history-snapshot":
                    # Track file snapshots
                    pass

    except OSError as e:
        logger.warning(f"Could not read session file {file_path}: {e}")
        return None

    if not first_timestamp:
        return None

    actual_session_id = found_session_id or session_id

    return ClaudeSession(
        session_id=actual_session_id,
        project_path=str(file_path.parent),
        project_name=file_path.parent.name,
        start_time=first_timestamp,
        end_time=last_timestamp,
        message_count=user_count + assistant_count,
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        tools_used=sorted(tools_used),
        files_accessed=sorted(files_accessed),
        models_used=sorted(models_used),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        cwd=cwd,
        git_branch=git_branch or "",
    )


def find_session_files(claude_projects_dir: str, project_path: str | None = None) -> list[Path]:
    """Find all JSONL session files in the Claude projects directory.

    Args:
        claude_projects_dir: Base directory (~/.claude/projects/)
        project_path: If given, only look in the matching project subdirectory.
    """
    base = Path(claude_projects_dir)
    if not base.exists():
        return []

    files: list[Path] = []
    for entry in base.iterdir():
        if not entry.is_dir():
            continue

        # If filtering by project, check if this dir matches
        if project_path:
            # The encoded dir name should contain the project path
            decoded = _matches_project(entry.name, project_path)
            if not decoded:
                continue

        # Collect .jsonl files (excluding agent files in subdirectories)
        for jsonl in entry.glob("*.jsonl"):
            if jsonl.stem.startswith("agent-"):
                continue
            files.append(jsonl)

    return files


def _get_local_tz() -> ZoneInfo:
    """Get the system's local timezone."""
    try:
        import time as _time
        tz_name = _time.tzname[0]
        # Try the IANA name from TZ env or system
        import os
        tz_env = os.environ.get("TZ")
        if tz_env:
            return ZoneInfo(tz_env)
        # Fallback: compute offset and use a well-known zone
        local_dt = datetime.now(timezone.utc).astimezone()
        return local_dt.tzinfo  # type: ignore[return-value]
    except Exception:
        return timezone.utc  # type: ignore[return-value]


def _to_local_date_str(dt: datetime) -> str:
    """Convert a datetime to local date string (YYYY-MM-DD).

    Handles both aware (UTC) and naive (assumed local) datetimes.
    """
    if dt.tzinfo is not None:
        local_dt = dt.astimezone(_get_local_tz())
        return local_dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")


def parse_sessions_for_date(
    claude_projects_dir: str,
    date_str: str,
    project_path: str | None = None,
) -> list[ClaudeSession]:
    """Parse all sessions for a given date.

    Args:
        claude_projects_dir: Base directory for Claude projects
        date_str: Date string in YYYY-MM-DD format
        project_path: Optional project path filter
    """
    files = find_session_files(claude_projects_dir, project_path)
    sessions: list[ClaudeSession] = []

    for f in files:
        session = parse_session_file(f)
        if session is None:
            continue

        # Check if session falls on the target date (local timezone)
        session_date = _to_local_date_str(session.start_time)
        if session_date == date_str:
            sessions.append(session)

    return sessions


def _matches_project(encoded_dir_name: str, project_path: str) -> bool:
    """Check if an encoded directory name matches a project path.

    The encoded dir name is the filesystem path with '/' replaced by '-'.
    E.g., /Users/huansuh/Documents/workspace/howmuch
       -> -Users-huansuh-Documents-workspace-howmuch

    We also match worktree dirs that start with the encoded path.
    """
    # Encode the project path the same way Claude Code does
    encoded_path = project_path.replace("/", "-")
    # Exact match
    if encoded_dir_name == encoded_path:
        return True
    # Worktree dirs use double-dash: {encoded_path}--claude-worktrees-*
    if encoded_dir_name.startswith(encoded_path + "--"):
        return True
    return False
