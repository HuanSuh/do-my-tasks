"""dmt sessions - View Claude Code session information."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from do_my_tasks.cli.output import is_json_mode

app = typer.Typer()
console = Console()

# Watch log directory and file handle
_watch_log_dir = Path.home() / ".dmt" / "logs"
_watch_log_file = None

# PID file for single-instance enforcement
_WATCH_PID_FILE = Path.home() / ".dmt" / "watch.pid"


def _acquire_watch_lock() -> None:
    """기존 watch 인스턴스를 종료하고 현재 PID를 기록한다."""
    if _WATCH_PID_FILE.exists():
        try:
            old_pid = int(_WATCH_PID_FILE.read_text().strip())
            os.kill(old_pid, signal.SIGTERM)
            # 종료될 때까지 최대 3초 대기
            for _ in range(30):
                time.sleep(0.1)
                try:
                    os.kill(old_pid, 0)
                except ProcessLookupError:
                    break
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    _WATCH_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _WATCH_PID_FILE.write_text(str(os.getpid()))


def _release_watch_lock() -> None:
    """PID 파일을 삭제한다."""
    try:
        if _WATCH_PID_FILE.exists() and _WATCH_PID_FILE.read_text().strip() == str(os.getpid()):
            _WATCH_PID_FILE.unlink()
    except OSError:
        pass


def _init_watch_log() -> Path:
    """Create watch log file and clean up old logs (5+ days)."""
    global _watch_log_file
    _watch_log_dir.mkdir(parents=True, exist_ok=True)

    # Clean up logs older than 5 days
    cutoff = time.time() - 5 * 86400
    for old_log in _watch_log_dir.glob("dmt_watch_log_*.log"):
        try:
            if old_log.stat().st_mtime < cutoff:
                old_log.unlink()
        except OSError:
            pass

    # Create new log file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = _watch_log_dir / f"dmt_watch_log_{ts}.log"
    _watch_log_file = open(log_path, "a", encoding="utf-8")
    return log_path


def _watch_log(message: str) -> None:
    """Append a timestamped message to the watch log."""
    if _watch_log_file and not _watch_log_file.closed:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _watch_log_file.write(f"[{ts}] {message}\n")
        _watch_log_file.flush()


def _watch_log_error(context: str, exc: Exception) -> None:
    """Log an error with traceback to the watch log."""
    import traceback
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    _watch_log(f"ERROR: {context}: {exc}")
    for line in tb:
        for sub in line.rstrip().split("\n"):
            _watch_log(f"  {sub}")


def _char_width(ch: str) -> int:
    """Return display width of a character (CJK = 2, others = 1)."""
    cp = ord(ch)
    # CJK Unified Ideographs, Hangul, Fullwidth forms, etc.
    if (
        0x1100 <= cp <= 0x115F   # Hangul Jamo
        or 0x2E80 <= cp <= 0x9FFF  # CJK
        or 0xAC00 <= cp <= 0xD7AF  # Hangul Syllables
        or 0xF900 <= cp <= 0xFAFF  # CJK Compatibility
        or 0xFE30 <= cp <= 0xFE6F  # CJK Forms
        or 0xFF01 <= cp <= 0xFF60  # Fullwidth
        or 0x20000 <= cp <= 0x2FA1F  # CJK Extension
    ):
        return 2
    return 1


def _truncate_display(text: str, max_width: int) -> str:
    """Truncate text to fit within max_width display columns."""
    width = 0
    for i, ch in enumerate(text):
        cw = _char_width(ch)
        if width + cw > max_width - 3:  # Reserve 3 for "..."
            return text[:i] + "..."
        width += cw
    return text


def _find_claude_processes() -> list[dict]:
    """Find running Claude Code CLI processes."""
    try:
        result = subprocess.run(
            ["ps", "axo", "pid,lstart,args"],
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "LC_ALL": "C"},
        )
    except OSError:
        return []

    processes = []
    for line in result.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue

        # ps lstart format: "DOW Mon DD HH:MM:SS YYYY"
        pid = parts[0]
        lstart = " ".join(parts[1:6])
        args_str = " ".join(parts[6:])

        # Match claude CLI processes, skip helpers/renderers
        # args_str may be: "claude", "claude .", "claude --resume", "/path/to/claude", etc.
        cmd = args_str.strip().split()[0] if args_str.strip() else ""
        is_claude = cmd == "claude" or cmd.endswith("/claude")
        if not is_claude:
            continue
        skip_words = ("Helper", "Renderer", "MacOS/Auto-Claude", "chrome-native")
        if any(skip in args_str for skip in skip_words):
            continue

        note = ""
        if "--resume" in args_str:
            note = "--resume"

        try:
            started = datetime.strptime(lstart, "%a %b %d %H:%M:%S %Y")
        except ValueError:
            started = None

        processes.append({
            "pid": pid,
            "started": started,
            "note": note,
        })

    return processes


def _get_cwd(pid: str) -> str | None:
    """Get the current working directory of a process."""
    try:
        result = subprocess.run(
            ["/usr/sbin/lsof", "-a", "-p", pid, "-d", "cwd"],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().splitlines()
        if len(lines) >= 2:
            return lines[-1].split()[-1]
    except OSError:
        pass
    return None


def _get_project_name(cwd: str) -> str:
    """Extract project name from cwd, handling worktree paths.

    Normal:    /Users/me/workspace/myapp                              -> myapp
    Worktree:  /Users/me/workspace/myapp/.claude/worktrees/feat-x    -> myapp
    Worktree:  /Users/me/workspace/myapp/.worktrees/feat-x           -> myapp
    """
    if "/.claude/worktrees/" in cwd:
        return Path(cwd.split("/.claude/worktrees/")[0]).name
    if "/.worktrees/" in cwd:
        return Path(cwd.split("/.worktrees/")[0]).name
    return Path(cwd).name


def _get_project_log_dirs(cwd: str) -> list[Path]:
    """Get all log directories for a project cwd.

    Searches both ~/.claude/projects/ and ~/.claude-profiles/*/projects/.
    Handles worktree paths (.claude/worktrees/<name>) by searching for
    matching --claude-worktrees-<name> directories.
    """
    home = Path.home()
    # Claude Code encodes both / and _ as -
    encoded = cwd.replace("/", "-")
    encoded_alt = cwd.replace("/", "-").replace("_", "-")

    # Collect all base directories to search
    base_dirs = [home / ".claude" / "projects"]
    profiles_base = home / ".claude-profiles"
    if profiles_base.exists():
        for profile_dir in profiles_base.iterdir():
            candidate = profile_dir / "projects"
            if candidate.exists():
                base_dirs.append(candidate)

    search_dirs: list[Path] = []
    for base in base_dirs:
        # Try both encodings (with and without _ → -)
        for enc in (encoded, encoded_alt):
            direct = base / enc
            if direct.exists() and direct not in search_dirs:
                search_dirs.append(direct)
        # Worktree: cwd contains .claude/worktrees/<name> or .worktrees/<name>
        # Claude Code encodes these as *--claude-worktrees-<name> or *--worktrees-<name>
        # Claude Code also encodes _ as - in worktree names.
        for wt_marker, wt_prefix in (
            ("/.claude/worktrees/", "--claude-worktrees-"),
            ("/.worktrees/", "--worktrees-"),
        ):
            if wt_marker not in cwd:
                continue
            wt_name = cwd.split(wt_marker)[-1].rstrip("/")
            wt_name_alt = wt_name.replace("_", "-")
            for d in base.iterdir():
                if not d.is_dir():
                    continue
                if d.name.endswith(f"{wt_prefix}{wt_name}"):
                    if d not in search_dirs:
                        search_dirs.append(d)
                elif wt_name_alt != wt_name and d.name.endswith(
                    f"{wt_prefix}{wt_name_alt}"
                ):
                    if d not in search_dirs:
                        search_dirs.append(d)

    return search_dirs


def _find_all_log_files(cwd: str) -> list[tuple[Path, float]]:
    """Find all JSONL log files for a project cwd.

    Returns list of (path, mtime) sorted by mtime descending.
    """
    files: list[tuple[Path, float]] = []
    for search_dir in _get_project_log_dirs(cwd):
        for jsonl in search_dir.glob("*.jsonl"):
            if jsonl.name.startswith("agent-"):
                continue
            try:
                mtime = jsonl.stat().st_mtime
                files.append((jsonl, mtime))
            except OSError:
                continue
    files.sort(key=lambda x: x[1], reverse=True)
    return files


def _find_log_file(cwd: str) -> tuple[Path | None, datetime | None]:
    """Find the most recent JSONL log file for a given project cwd."""
    files = _find_all_log_files(cwd)
    if files:
        best, mtime = files[0]
        return best, datetime.fromtimestamp(mtime)
    return None, None


def _lsof_find_jsonl(pid: str) -> Path | None:
    """Find JSONL file opened by a process via lsof."""
    try:
        result = subprocess.run(
            ["/usr/sbin/lsof", "-a", "-p", pid],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if ".jsonl" in line and "agent-" not in line:
                path_str = line.split()[-1]
                path = Path(path_str)
                if path.suffix == ".jsonl" and path.exists():
                    return path
    except OSError:
        pass
    return None


def _match_pids_to_logs(
    processes: list[dict],
    pid_cwds: dict[str, str],
) -> dict[str, tuple[Path | None, datetime | None]]:
    """Match PIDs to their specific JSONL log files.

    Uses a 3-tier matching strategy:
    1. lsof: check if the process has a JSONL file open
    2. birth time: match non-resume sessions by file creation time
    3. mtime: match resume sessions to actively modified files

    Returns: {pid: (log_path, log_mtime_dt)}
    """
    result: dict[str, tuple[Path | None, datetime | None]] = {}

    def _assign(pid: str, path: Path, mtime: float) -> None:
        result[pid] = (path, datetime.fromtimestamp(mtime))

    # Group PIDs by cwd
    cwd_groups: dict[str, list[dict]] = {}
    for proc in processes:
        cwd = pid_cwds.get(proc["pid"])
        if not cwd:
            result[proc["pid"]] = (None, None)
            continue
        cwd_groups.setdefault(cwd, []).append(proc)

    for cwd, procs in cwd_groups.items():
        all_files = _find_all_log_files(cwd)

        if not all_files:
            for p in procs:
                result[p["pid"]] = (None, None)
            continue

        # Single PID: assign most recent file
        if len(procs) == 1:
            best = all_files[0]
            _assign(procs[0]["pid"], best[0], best[1])
            continue

        # Single file: all PIDs share it
        if len(all_files) == 1:
            for p in procs:
                _assign(p["pid"], all_files[0][0], all_files[0][1])
            continue

        # Multiple PIDs & files: 3-tier matching
        remaining = list(all_files)
        file_mtime_map = {str(p): m for p, m in all_files}

        def _remove_from_remaining(target: Path) -> None:
            nonlocal remaining
            remaining = [(p, m) for p, m in remaining if p != target]

        # --- Tier 1: lsof ---
        tier1_unmatched: list[dict] = []
        for proc in procs:
            jsonl_path = _lsof_find_jsonl(proc["pid"])
            if jsonl_path:
                mtime = file_mtime_map.get(
                    str(jsonl_path),
                )
                if mtime is None:
                    try:
                        mtime = jsonl_path.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                _assign(proc["pid"], jsonl_path, mtime)
                _remove_from_remaining(jsonl_path)
            else:
                tier1_unmatched.append(proc)

        if not tier1_unmatched or not remaining:
            for proc in tier1_unmatched:
                result.setdefault(proc["pid"], (None, None))
            continue

        # Separate resume vs normal sessions
        normal_procs = [
            p for p in tier1_unmatched if p.get("note") != "--resume"
        ]
        resume_procs = [
            p for p in tier1_unmatched if p.get("note") == "--resume"
        ]

        # --- Tier 2: birth time (normal sessions only) ---
        # Claude Code creates JSONL lazily on first message, so the file is
        # always born AFTER the process starts. Files born before process
        # start belong to a previous/different session and must be excluded.
        _BIRTH_GRACE = 5.0   # seconds: allow small clock/timing skew
        _BIRTH_MAX = 3600.0  # seconds: max window after process start

        tier2_unmatched: list[dict] = []
        sorted_normal = sorted(
            normal_procs,
            key=lambda p: (p["started"] or datetime.min).timestamp(),
        )

        for proc in sorted_normal:
            if not proc["started"]:
                tier2_unmatched.append(proc)
                continue

            pid_ts = proc["started"].timestamp()
            best_match = None
            best_delta = _BIRTH_MAX

            for path, mtime in remaining:
                try:
                    birth = path.stat().st_birthtime
                except (OSError, AttributeError):
                    continue
                # signed delta: positive = file born after process started
                signed = birth - pid_ts
                # Only accept files born at or after process start
                # (with small grace for clock skew)
                if signed >= -_BIRTH_GRACE and signed < best_delta:
                    best_delta = signed
                    best_match = (path, mtime)

            if best_match:
                _assign(proc["pid"], best_match[0], best_match[1])
                _remove_from_remaining(best_match[0])
            else:
                tier2_unmatched.append(proc)

        # --- Tier 3: mtime (resume sessions + remaining unmatched) ---
        tier3_procs = resume_procs + tier2_unmatched
        # Sort by start time descending — most recent process gets
        # the most recently modified file
        tier3_procs.sort(
            key=lambda p: (p["started"] or datetime.min).timestamp(),
            reverse=True,
        )
        remaining.sort(key=lambda x: x[1], reverse=True)

        for proc in tier3_procs:
            if not remaining:
                result.setdefault(proc["pid"], (None, None))
                continue

            if proc["started"] and len(remaining) > 1:
                pid_ts = proc["started"].timestamp()
                # Pick files modified after process start (with 1 min tolerance)
                candidates = [
                    (p, m) for p, m in remaining
                    if m >= pid_ts - 60
                ]
                if candidates:
                    best = candidates[0]  # most recent mtime
                    _assign(proc["pid"], best[0], best[1])
                    _remove_from_remaining(best[0])
                    continue

            # Fallback: most recently modified remaining file
            best = remaining[0]
            _assign(proc["pid"], best[0], best[1])
            _remove_from_remaining(best[0])

    return result


def _read_tail(log_path: Path, size: int = 4096) -> list[str]:
    """Read the last `size` bytes of a file and return lines."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            read_size = min(file_size, size)
            f.seek(file_size - read_size)
            data = f.read().decode("utf-8", errors="replace")
        return data.strip().splitlines()
    except OSError:
        return []


def _get_last_log_timestamp(log_path: Path) -> datetime | None:
    """Get the timestamp of the last entry in a JSONL log file (local naive)."""
    for line in reversed(_read_tail(log_path)):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts_str = entry.get("timestamp")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                return ts.astimezone().replace(tzinfo=None)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


_AMEND_PREFIX = "To tell you how to proceed, the user said:\n"

# System-injected messages to skip (not real user input)
_SYSTEM_MSG_PREFIXES = (
    "<",                          # XML tags: <bash-stdout>, <system-reminder>, etc.
    "This session is being continued from a previous conversation",
)


def _extract_user_text(content) -> str | None:
    """Extract user message text from JSONL user entry content.

    Handles both plain string content and tool_result lists
    (Tab-amended permission responses contain user text after
    'To tell you how to proceed, the user said:' prefix).

    Skips system-injected messages (XML tags, context carry-over).
    Returns the first non-empty line, stripped of whitespace.
    """
    raw: str | None = None

    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "tool_result":
                continue
            rc = item.get("content", "")
            if isinstance(rc, str) and _AMEND_PREFIX in rc:
                raw = rc.split(_AMEND_PREFIX, 1)[1]
                break

    if not raw:
        return None

    # Take the first non-empty line
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped:
            # Skip system-injected messages
            if any(stripped.startswith(p) for p in _SYSTEM_MSG_PREFIXES):
                return None
            return stripped
    return None


def _get_session_activity(log_path: Path) -> dict:
    """Extract last user message and recent tools from a JSONL log.

    Returns dict with keys: last_message, tools, time_ago.
    """
    result = {
        "last_message": None,
        "tools": [],
        "time_ago": None,
    }

    # Read more data for detail view to find the last user message
    lines = _read_tail(log_path, size=32768)

    last_user_msg = None
    last_user_ts = None
    tools_after_user: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = entry.get("type")

        if msg_type == "user":
            # Skip meta messages (commands like /help, /clear)
            if entry.get("isMeta"):
                continue
            message = entry.get("message", {})
            content = message.get("content", "")
            user_text = _extract_user_text(content)
            if user_text:
                last_user_msg = user_text
                ts_str = entry.get("timestamp")
                if ts_str:
                    try:
                        last_user_ts = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
                tools_after_user = []

        elif msg_type == "assistant":
            message = entry.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                    ):
                        tool_name = block.get("name", "")
                        if tool_name and tool_name not in tools_after_user:
                            tools_after_user.append(tool_name)

    if last_user_msg:
        # Take first line only
        last_user_msg = last_user_msg.split("\n")[0].strip()
        # Truncate - use display width (CJK chars = 2 cols)
        last_user_msg = _truncate_display(last_user_msg, 30)
        result["last_message"] = last_user_msg

    if tools_after_user:
        result["tools"] = tools_after_user[-5:]  # Last 5 tools

    if last_user_ts:
        now = datetime.now(tz=last_user_ts.tzinfo)
        delta = now - last_user_ts
        minutes = int(delta.total_seconds() / 60)
        if minutes < 1:
            result["time_ago"] = "just now"
        elif minutes < 60:
            result["time_ago"] = f"{minutes}min ago"
        elif minutes < 1440:
            result["time_ago"] = f"{minutes // 60}h ago"
        else:
            result["time_ago"] = f"{minutes // 1440}d ago"

    return result


def _get_session_state(log_path: Path) -> dict:
    """Determine current session state from the JSONL log tail.

    Returns dict with:
        last_type: "user" | "assistant" | None
        last_ts: datetime | None
        last_user_msg: str | None
        tools: list[str]
        files_modified: list[str]  - files written/edited
        commands_run: list[str]    - bash commands executed
        stop_reason: str | None    - "end_turn" | "tool_use"
        status: str  - "idle" | "permission" | "working" | "waiting"
        file_size: int
    """
    state: dict = {
        "last_type": None,
        "last_ts": None,
        "last_user_msg": None,
        "tools": [],
        "files_modified": [],
        "commands_run": [],
        "stop_reason": None,
        "status": "waiting",
        "file_size": 0,
    }
    try:
        state["file_size"] = log_path.stat().st_size
    except OSError:
        return state

    lines = _read_tail(log_path, size=32768)
    last_user_msg = None
    tools_after_user: list[str] = []
    files_modified: list[str] = []
    commands_run: list[str] = []
    last_stop_reason: str | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = entry.get("type")
        ts_str = entry.get("timestamp")

        if msg_type == "user":
            if entry.get("isMeta"):
                continue
            message = entry.get("message", {})
            content = message.get("content", "")
            user_text = _extract_user_text(content)
            if user_text:
                # Real user input — mark as "user" turn
                state["last_type"] = "user"
                last_user_msg = user_text.split("\n")[0]
                tools_after_user = []
                files_modified = []
                commands_run = []
                last_stop_reason = None
            # Tool approvals (empty content / tool_result without text)
            # don't change last_type — keep previous state
        elif msg_type == "assistant":
            state["last_type"] = "assistant"
            message = entry.get("message", {})
            last_stop_reason = message.get("stop_reason")
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    name = block.get("name", "")
                    if name and name not in tools_after_user:
                        tools_after_user.append(name)
                    # Extract file paths and commands
                    inp = block.get("input", {})
                    if not isinstance(inp, dict):
                        continue
                    if name in ("Write", "Edit"):
                        fp = inp.get("file_path", "")
                        if fp:
                            fname = Path(fp).name
                            if fname not in files_modified:
                                files_modified.append(fname)
                    elif name == "Bash":
                        cmd = inp.get("command", "")
                        if cmd:
                            # First token of command
                            short = cmd.split()[0] if cmd.split() else cmd
                            # For common patterns, show more
                            if short in ("poetry", "git", "npm"):
                                parts = cmd.split()[:3]
                                short = " ".join(parts)
                            if short not in commands_run:
                                commands_run.append(short)

        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                state["last_ts"] = ts.astimezone().replace(tzinfo=None)
            except ValueError:
                pass

    state["last_user_msg"] = last_user_msg
    state["tools"] = tools_after_user[-5:]
    state["files_modified"] = files_modified[-8:]
    state["commands_run"] = commands_run[-5:]
    state["stop_reason"] = last_stop_reason

    # Determine status
    if state["last_type"] == "assistant":
        if last_stop_reason == "tool_use":
            state["status"] = "permission"
        else:
            state["status"] = "idle"
    elif state["last_type"] == "user":
        state["status"] = "working"
    else:
        state["status"] = "waiting"

    return state


def _get_tty_for_pid(pid: str) -> str | None:
    """Get the TTY device path for a given PID."""
    try:
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", pid],
            capture_output=True, text=True, timeout=3,
        )
        tty = result.stdout.strip()
        if tty and tty != "??":
            return f"/dev/{tty}"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _build_activate_terminal_script(tty: str) -> str:
    """Build AppleScript to activate the terminal tab with the given TTY."""
    import os
    term_program = os.environ.get("TERM_PROGRAM", "")

    if "iTerm" in term_program:
        return (
            'tell application "iTerm"\n'
            "  activate\n"
            "  repeat with aWindow in windows\n"
            "    repeat with aTab in tabs of aWindow\n"
            "      repeat with aSession in sessions of aTab\n"
            f'        if tty of aSession is "{tty}" then\n'
            "          select aTab\n"
            "          select aWindow\n"
            "        end if\n"
            "      end repeat\n"
            "    end repeat\n"
            "  end repeat\n"
            "end tell"
        )
    else:
        # Terminal.app
        return (
            'tell application "Terminal"\n'
            "  activate\n"
            "  repeat with aWindow in windows\n"
            "    repeat with aTab in tabs of aWindow\n"
            f'      if tty of aTab is "{tty}" then\n'
            "        set selected tab of aWindow to aTab\n"
            "        set index of aWindow to 1\n"
            "      end if\n"
            "    end repeat\n"
            "  end repeat\n"
            "end tell"
        )


def _send_notification(title: str, message: str, pid: str | None = None) -> None:
    """Send macOS notification. Click activates the session's terminal tab."""
    import shutil

    terminal_notifier = shutil.which("terminal-notifier")

    if terminal_notifier:
        cmd = [
            terminal_notifier,
            "-title", title,
            "-message", message,
            "-sound", "Glass",
            "-group", f"dmt-{pid}" if pid else "dmt",
        ]
        # If we have a PID, add click-to-activate behavior
        if pid:
            tty = _get_tty_for_pid(pid)
            if tty:
                script = _build_activate_terminal_script(tty)
                cmd.extend(["-execute", f'osascript -e \'{script}\''])
            else:
                # Fallback: just activate the terminal app
                import os
                term = os.environ.get("TERM_PROGRAM", "")
                bundle_id = (
                    "com.googlecode.iterm2" if "iTerm" in term
                    else "com.apple.Terminal"
                )
                cmd.extend(["-activate", bundle_id])
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        # Fallback: plain osascript (no click action)
        script = (
            f'display notification "{message}" '
            f'with title "{title}" sound name "Glass"'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def _get_next_tasks(project_name: str | None = None) -> list[str]:
    """Get pending tasks, optionally filtered by project."""
    try:
        from do_my_tasks.core.task_manager import TaskManager
        from do_my_tasks.storage.database import get_session_factory

        factory = get_session_factory()
        manager = TaskManager(factory)
        tasks = manager.list(
            project_name=project_name, status="pending",
        )
        result = []
        for t in tasks[:5]:
            pri = t.priority.upper()
            result.append(f"T-{t.id:04d} [{pri}] {t.title}")
        return result
    except Exception:
        return []


@app.callback(invoke_without_command=True)
def sessions(
    ctx: typer.Context,
    wide: bool = typer.Option(False, "--wide", "-w", help="Show full log paths."),
    detail: bool = typer.Option(
        False, "--detail", "-d", help="Show last activity per session.",
    ),
):
    """View Claude Code session information."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(live, wide=wide, detail=detail)


@app.command()
def live(
    wide: bool = typer.Option(
        False, "--wide", "-w", help="Show full log paths.",
    ),
    detail: bool = typer.Option(
        False, "--detail", "-d", help="Show last activity per session.",
    ),
):
    """Show currently running Claude Code sessions."""
    processes = _find_claude_processes()

    if not processes:
        if is_json_mode():
            print(json.dumps({"sessions": [], "total": 0}))
        else:
            console.print("[yellow]No running Claude Code sessions found.[/yellow]")
        raise typer.Exit()

    # Resolve cwds for all PIDs first
    pid_cwds: dict[str, str] = {}
    for proc in processes:
        cwd = _get_cwd(proc["pid"])
        if cwd:
            pid_cwds[proc["pid"]] = cwd

    # Match PIDs to their specific log files
    pid_logs = _match_pids_to_logs(processes, pid_cwds)

    # Build session data for all processes
    sessions_data: list[dict] = []
    for proc in sorted(
        processes,
        key=lambda p: p["started"] or datetime.min,
        reverse=True,
    ):
        cwd = pid_cwds.get(proc["pid"])
        project = _get_project_name(cwd) if cwd else "?"

        log_path, log_mtime = pid_logs.get(
            proc["pid"], (None, None),
        )

        if log_path:
            last_ts = _get_last_log_timestamp(log_path)
            last_update_str = last_ts.strftime("%m/%d %H:%M") if last_ts else (
                log_mtime.strftime("%m/%d %H:%M") if log_mtime else "-"
            )
        else:
            last_ts = None
            last_update_str = "-"

        started_str = (
            proc["started"].strftime("%m/%d %H:%M")
            if proc["started"] else "?"
        )

        session_info: dict = {
            "pid": proc["pid"],
            "project": project,
            "started": proc["started"].isoformat() if proc["started"] else None,
            "started_display": started_str,
            "last_update": last_ts.isoformat() if last_ts else (
                log_mtime.isoformat() if log_mtime else None
            ),
            "last_update_display": last_update_str,
            "note": proc["note"],
            "log_path": str(log_path) if log_path else None,
        }

        if detail and log_path:
            activity = _get_session_activity(log_path)
            session_info["last_message"] = activity["last_message"]
            session_info["tools"] = activity["tools"]
            session_info["time_ago"] = activity["time_ago"]
        elif detail:
            session_info["last_message"] = None
            session_info["tools"] = []
            session_info["time_ago"] = None

        sessions_data.append(session_info)

    # JSON output
    if is_json_mode():
        print(json.dumps({
            "sessions": sessions_data,
            "total": len(sessions_data),
        }, ensure_ascii=False))
        return

    # Rich table output
    table = Table(title="Live Claude Code Sessions", show_lines=True)
    table.add_column("PID", style="cyan", width=7)
    table.add_column("Project", style="bold")
    table.add_column("Started", style="green")
    table.add_column("Last Update", style="yellow")
    table.add_column("Note")
    if not detail:
        table.add_column("Log Path", style="dim")
    else:
        table.add_column("Last Message", style="white")
        table.add_column("Tools", style="dim")

    for s in sessions_data:
        if not detail:
            if s["log_path"]:
                if wide:
                    display_path = s["log_path"].replace(
                        str(Path.home()), "~",
                    )
                else:
                    display_path = Path(s["log_path"]).name
            else:
                display_path = "(no log)"
            table.add_row(
                s["pid"], s["project"], s["started_display"],
                s["last_update_display"], s["note"], display_path,
            )
        else:
            msg = s.get("last_message") or "(no message)"
            if s.get("time_ago"):
                msg = f"{msg} [dim]({s['time_ago']})[/dim]"
            tools_str = ", ".join(s.get("tools", [])) if s.get("tools") else "-"
            table.add_row(
                s["pid"], s["project"], s["started_display"],
                s["last_update_display"], s["note"], msg, tools_str,
            )

    console.print(table)
    console.print(f"\n[dim]Total: {len(sessions_data)} sessions[/dim]")


@app.command()
def watch(
    interval: int = typer.Option(
        10, "--interval", "-i",
        help="Polling interval in seconds.",
    ),
    idle_threshold: int = typer.Option(
        30, "--idle", help="Seconds of inactivity before notifying.",
    ),
    notify: bool = typer.Option(
        True, "--notify/--no-notify", help="Send OS notifications.",
    ),
    project: str | None = typer.Option(
        None, "--project", "-p",
        help="Only watch sessions for this project.",
    ),
    tail: bool = typer.Option(
        False, "--tail", "-t",
        help="Print live log activity (user messages + tool calls) as they arrive.",
    ),
    web: bool = typer.Option(
        False, "--web", "-w",
        help="Also launch the web dashboard (default port 7317).",
    ),
    web_port: int = typer.Option(
        7317, "--web-port",
        help="Port for the web dashboard (used with --web).",
    ),
):
    """Watch sessions and notify with next tasks when idle.

    Monitors active Claude Code sessions. When a session finishes
    working (assistant done, no new activity), sends a notification
    with pending tasks so you can assign the next one.
    """
    # 단일 인스턴스 보장 — 기존 watch 프로세스 종료 후 PID 기록
    _acquire_watch_lock()

    # Init watch log
    log_path = _init_watch_log()

    # Launch web dashboard in background thread if requested
    if web:
        import threading

        import uvicorn

        def _run_web():
            uvicorn.run(
                "do_my_tasks.web.app:app",
                host="127.0.0.1",
                port=web_port,
                log_level="warning",
            )

        web_thread = threading.Thread(target=_run_web, daemon=True)
        web_thread.start()

        # Open browser after a short delay
        import webbrowser

        def _open_browser():
            time.sleep(1.5)
            webbrowser.open(f"http://127.0.0.1:{web_port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    console.clear()
    _watch_log(f"Watch started (poll: {interval}s, idle: {idle_threshold}s)")
    if project:
        _watch_log(f"Filtering project: {project}")
    if web:
        _watch_log(f"Web: http://127.0.0.1:{web_port}")

    # ── info panel text (rebuilt each iteration when using Live) ──────────────
    def _build_info_text(session_statuses: list[str]) -> str:
        lines = [
            f"[bold]Watching sessions[/bold] "
            f"(poll: [cyan]{interval}s[/cyan], idle: [cyan]{idle_threshold}s[/cyan])",
        ]
        if web:
            lines.append(f"Web: [link]http://127.0.0.1:{web_port}[/link]")
        lines.append(f"Log: [dim]{log_path}[/dim]")
        if session_statuses:
            lines.append("")
            lines.extend(session_statuses)
        lines.append("")
        lines.append("Press [bold]Ctrl+C[/bold] to stop.")
        return "\n".join(lines)

    # Track state per log file: {path: {size, last_ts, notified}}
    tracked: dict[str, dict] = {}
    # Track which PIDs we've resolved cwd for
    pid_cwd_cache: dict[str, str] = {}
    # Track tail read offset per log file (byte position)
    tail_offsets: dict[str, int] = {}
    # Rolling tail buffer (markup strings) used with Live display
    tail_buffer: list[str] = []
    MAX_TAIL_LINES = 40
    last_heartbeat = time.time()

    # ── Live display builder ──────────────────────────────────────────────────
    def _build_live(session_statuses: list[str]) -> Layout:
        info_text = _build_info_text(session_statuses)
        # Fixed height: base lines + 1 per session + borders
        info_height = info_text.count("\n") + 3

        tail_content = "\n".join(tail_buffer[-MAX_TAIL_LINES:]) if tail_buffer \
            else "[dim]Waiting for activity…[/dim]"

        layout = Layout()
        layout.split_column(
            Layout(
                Panel(info_text, title="dmt sessions watch", border_style="blue"),
                name="info",
                size=info_height,
            ),
            Layout(
                Panel(Text.from_markup(tail_content), title="[dim]Live Log[/dim]", border_style="dim"),
                name="tail",
            ),
        )
        return layout

    # ── session status lines for info panel ───────────────────────────────────
    STATUS_LINE_EMOJI = {"idle": "⏸", "working": "🔄", "permission": "⚠️", "waiting": "💤"}

    def _session_status_lines(pid_cwd_cache: dict, pid_logs: dict, processes: list) -> list[str]:
        lines = []
        for proc in processes:
            pid = proc["pid"]
            cwd = pid_cwd_cache.get(pid)
            if not cwd:
                continue
            proj = _get_project_name(cwd)
            lp, _ = pid_logs.get(pid, (None, None))
            st = _get_session_state(lp).get("status", "waiting") if lp else "waiting"
            emoji = STATUS_LINE_EMOJI.get(st, "💤")
            lines.append(f"  {emoji} [cyan]{proj}[/cyan] [dim](PID {pid})[/dim] — [dim]{st}[/dim]")
        return lines

    # ── main loop ─────────────────────────────────────────────────────────────
    def _run_loop(live: Live | None) -> None:
        nonlocal last_heartbeat

        while True:
            try:
                processes = _find_claude_processes()
            except Exception as e:
                _watch_log_error("Failed to find processes", e)
                time.sleep(interval)
                continue

            for proc in processes:
                pid = proc["pid"]
                if pid not in pid_cwd_cache:
                    try:
                        cwd = _get_cwd(pid)
                        if cwd:
                            pid_cwd_cache[pid] = cwd
                    except Exception as e:
                        _watch_log_error(f"cwd lookup for PID {pid}", e)

            pid_logs = _match_pids_to_logs(processes, pid_cwd_cache)

            for proc in processes:
                pid = proc["pid"]

                try:
                    cwd = pid_cwd_cache.get(pid)
                    if not cwd:
                        continue

                    proj_name = _get_project_name(cwd)
                    if project and proj_name != project:
                        continue

                    log_path_proc, _ = pid_logs.get(pid, (None, None))
                    if not log_path_proc:
                        continue

                    log_key = str(log_path_proc)
                    state = _get_session_state(log_path_proc)
                    prev = tracked.get(log_key)

                    # --tail: read new log entries
                    if tail:
                        if log_key not in tail_offsets:
                            try:
                                tail_offsets[log_key] = log_path_proc.stat().st_size
                            except OSError:
                                tail_offsets[log_key] = 0
                        else:
                            new_lines, new_offset = _read_new_lines(
                                log_path_proc, tail_offsets[log_key]
                            )
                            tail_offsets[log_key] = new_offset
                            for raw in new_lines:
                                raw = raw.strip()
                                if not raw:
                                    continue
                                try:
                                    entry = json.loads(raw)
                                    formatted = _format_tail_entry(entry, proj_name)
                                    if live is not None:
                                        tail_buffer.extend(formatted)
                                    else:
                                        for line in formatted:
                                            console.print(Text.from_markup(line))
                                except json.JSONDecodeError:
                                    pass

                    now = time.time()

                    if prev is None:
                        tracked[log_key] = {
                            "size": state["file_size"],
                            "last_change": now,
                            "notified": False,
                            "project": proj_name,
                            "pid": pid,
                            "last_user_msg": state["last_user_msg"],
                            "tools": state["tools"],
                        }
                        _watch_log(
                            f"Tracking: {proj_name} (PID {pid}) "
                            f"status={state.get('status', '?')}"
                        )
                        continue

                    if state["file_size"] != prev["size"]:
                        prev["size"] = state["file_size"]
                        prev["last_change"] = now
                        prev["notified"] = False
                        prev["perm_notified"] = False
                        prev["last_user_msg"] = state["last_user_msg"]
                        prev["tools"] = state["tools"]
                        prev["files_modified"] = state["files_modified"]
                        prev["commands_run"] = state["commands_run"]
                        active_msg = (state.get("last_user_msg") or "")[:50]
                        _watch_log(
                            f"Active: {proj_name} (PID {pid}) "
                            f"status={state.get('status', '?')}"
                            + (f" msg=\"{active_msg}\"" if active_msg else "")
                        )
                        continue

                    idle_secs = now - prev["last_change"]
                    is_idle = idle_secs >= idle_threshold and state["status"] == "idle"

                    if is_idle and not prev["notified"]:
                        prev["notified"] = True
                        idle_dur = _format_idle_duration(idle_secs)
                        idle_msg = (prev.get("last_user_msg") or "")[:50]
                        _watch_log(
                            f"Idle: {proj_name} (PID {pid}) "
                            f"status={state.get('status', '?')} idle={idle_dur}"
                            + (f" msg=\"{idle_msg}\"" if idle_msg else "")
                        )
                        _handle_idle_session(
                            proj_name, pid, prev, state, notify,
                            tail_buffer=tail_buffer if live is not None else None,
                        )

                    needs_perm = (
                        idle_secs >= idle_threshold
                        and state["status"] == "permission"
                        and not prev.get("perm_notified")
                    )
                    if needs_perm:
                        prev["perm_notified"] = True
                        pending_tool = state.get("tools", ["?"])[-1]
                        _watch_log(
                            f"Permission: {proj_name} (PID {pid}) "
                            f"status={state.get('status', '?')} tool={pending_tool}"
                        )
                        _handle_permission_session(
                            proj_name, pid, state, notify,
                            tail_buffer=tail_buffer if live is not None else None,
                        )

                except Exception as e:
                    _watch_log_error(f"PID {pid} processing failed", e)

            # Clean up dead PIDs
            live_pids = {p["pid"] for p in processes}
            for p in [p for p in pid_cwd_cache if p not in live_pids]:
                del pid_cwd_cache[p]

            # Heartbeat
            if time.time() - last_heartbeat >= 60:
                last_heartbeat = time.time()
                counts: dict[str, int] = {}
                for t in tracked.values():
                    idle = time.time() - t["last_change"]
                    s = "active" if idle < idle_threshold else (
                        "permission" if t.get("perm_notified") else
                        "idle" if t.get("notified") else "waiting"
                    )
                    counts[s] = counts.get(s, 0) + 1
                parts = [
                    f"{counts.get(s, 0)} {s}"
                    for s in ("active", "permission", "idle", "waiting")
                    if counts.get(s, 0) > 0
                ]
                _watch_log(
                    f"Heartbeat: {len(tracked)} sessions "
                    f"({', '.join(parts) or 'none tracked'})"
                )

            # Update Live display
            if live is not None:
                status_lines = _session_status_lines(pid_cwd_cache, pid_logs, processes)
                live.update(_build_live(status_lines))

            time.sleep(interval)

    try:
        if tail:
            with Live(
                _build_live([]),
                console=console,
                refresh_per_second=2,
                screen=True,
            ) as live:
                _run_loop(live)
        else:
            console.print(
                Panel(
                    _build_info_text([]),
                    title="dmt sessions watch",
                    border_style="blue",
                )
            )
            _run_loop(live=None)

    except KeyboardInterrupt:
        _watch_log("Watch stopped by user (Ctrl+C)")
        console.print("\n[dim]Watch stopped.[/dim]")
    except Exception as e:
        _watch_log_error("Watch crashed", e)
        console.print(f"\n[red]Watch error: {e}[/red]")
        raise
    finally:
        _release_watch_lock()
        if _watch_log_file and not _watch_log_file.closed:
            _watch_log_file.close()


STATUS_EMOJI = {
    "idle": "✅",
    "permission": "⏸️",
    "working": "🔄",
    "waiting": "💤",
}


def _build_work_summary(prev: dict, state: dict) -> str:
    """Build a human-readable summary of work done."""
    parts: list[str] = []

    files = prev.get("files_modified") or state.get("files_modified", [])
    cmds = prev.get("commands_run") or state.get("commands_run", [])

    if files:
        if len(files) <= 3:
            parts.append(", ".join(files))
        else:
            parts.append(f"{', '.join(files[:3])} 외 {len(files) - 3}개")

    if cmds:
        parts.append(" | ".join(cmds[:3]))

    return " → ".join(parts) if parts else ""


def _handle_idle_session(
    project: str,
    pid: str,
    prev: dict,
    state: dict,
    send_notify: bool,
    tail_buffer: list[str] | None = None,
) -> None:
    """Handle a session that has become idle."""
    now_str = datetime.now().strftime("%H:%M:%S")
    emoji = STATUS_EMOJI.get(state.get("status", "idle"), "✅")

    user_msg = prev.get("last_user_msg") or ""
    if user_msg:
        user_msg = _truncate_display(user_msg, 40)

    summary = _build_work_summary(prev, state)

    body_lines = []
    body_lines.append(
        f"{emoji} [bold green]완료[/bold green] "
        f"[dim]({state.get('status', 'idle')})[/dim] — "
        f"[cyan]{project}[/cyan] (PID {pid})"
    )
    if user_msg:
        body_lines.append(f'[dim]요청:[/dim] "{user_msg}"')
    if summary:
        body_lines.append(f"[dim]작업:[/dim] {summary}")

    if tail_buffer is not None:
        tail_buffer.append("")
        tail_buffer.append(
            f"[dim]{'─' * 50}[/dim] [bold]{now_str}[/bold]"
        )
        tail_buffer.extend(body_lines)
        tail_buffer.append(f"[dim]{'─' * 50}[/dim]")
    else:
        console.print()
        console.print(
            Panel(
                "\n".join(body_lines),
                title=f"[bold]{now_str}[/bold]",
                border_style="green",
            )
        )

    if send_notify:
        notif_title = f"{emoji} DMT — {project}"
        notif_parts = []
        if user_msg:
            notif_parts.append(user_msg)
        if summary:
            notif_parts.append(summary)
        _send_notification(
            notif_title,
            "\\n".join(notif_parts) if notif_parts else "작업 완료",
            pid=pid,
        )


def _handle_permission_session(
    project: str,
    pid: str,
    state: dict,
    send_notify: bool,
    tail_buffer: list[str] | None = None,
) -> None:
    """Handle a session waiting for user permission."""
    now_str = datetime.now().strftime("%H:%M:%S")
    emoji = STATUS_EMOJI["permission"]

    tools = state.get("tools", [])
    pending_tool = tools[-1] if tools else "unknown"

    body_lines = [
        f"{emoji} [bold yellow]권한 필요[/bold yellow] "
        f"[dim]({state.get('status', 'permission')})[/dim] — "
        f"[cyan]{project}[/cyan] (PID {pid})",
        f"[dim]대기 중:[/dim] {pending_tool} 실행 승인 대기",
    ]

    if tail_buffer is not None:
        tail_buffer.append("")
        tail_buffer.append(
            f"[dim]{'─' * 50}[/dim] [bold]{now_str}[/bold]"
        )
        tail_buffer.extend(body_lines)
        tail_buffer.append(f"[dim]{'─' * 50}[/dim]")
    else:
        console.print()
        console.print(
            Panel(
                "\n".join(body_lines),
                title=f"[bold]{now_str}[/bold]",
                border_style="yellow",
            )
        )

    if send_notify:
        _send_notification(
            f"{emoji} DMT — {project}",
            f"권한 필요: {pending_tool} 승인 대기 중",
            pid=pid,
        )


def _read_new_lines(log_path: Path, offset: int) -> tuple[list[str], int]:
    """Read new lines from log_path starting at byte offset.

    Returns (new_lines, new_offset).
    """
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            if end <= offset:
                return [], offset
            f.seek(offset)
            data = f.read(end - offset).decode("utf-8", errors="replace")
        lines = [l for l in data.splitlines() if l.strip()]
        return lines, end
    except OSError:
        return [], offset


_TOOL_KEY_FIELDS = {
    "Bash": ("command",),
    "Read": ("file_path",),
    "Write": ("file_path",),
    "Edit": ("file_path",),
    "Glob": ("pattern",),
    "Grep": ("pattern",),
    "WebFetch": ("url",),
    "WebSearch": ("query",),
    "Agent": ("description",),
    "NotebookEdit": ("notebook_path",),
}

_TOOL_COLORS = {
    "Bash": "yellow",
    "Read": "cyan",
    "Write": "green",
    "Edit": "green",
    "Glob": "cyan",
    "Grep": "cyan",
    "WebFetch": "magenta",
    "WebSearch": "magenta",
    "Agent": "blue",
}


def _format_tool_input(name: str, inp: dict) -> str:
    """Extract the most meaningful field from tool input."""
    keys = _TOOL_KEY_FIELDS.get(name, ())
    for k in keys:
        v = inp.get(k, "")
        if v:
            v = str(v)
            # First line only, truncated
            v = v.split("\n")[0]
            if len(v) > 60:
                v = v[:57] + "…"
            return v
    return ""


def _format_tail_entry(entry: dict, project: str) -> list[str]:
    """Format a single JSONL log entry as rich markup lines (may be empty)."""
    msg_type = entry.get("type")
    ts_str = entry.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        ts_display = ts.astimezone().strftime("%H:%M:%S")
    except (ValueError, AttributeError):
        ts_display = "--:--:--"

    prefix = f"[dim]{ts_display}[/dim] [bold cyan]{project}[/bold cyan]"
    lines: list[str] = []

    if msg_type == "user":
        if entry.get("isMeta"):
            return lines
        content = entry.get("message", {}).get("content", "")
        text = _extract_user_text(content)
        if not text:
            return lines
        if len(text) > 80:
            text = text[:77] + "…"
        lines.append(f"{prefix} [bold white]▶[/bold white] {text}")

    elif msg_type == "assistant":
        message = entry.get("message", {})
        content = message.get("content", [])
        stop_reason = message.get("stop_reason")

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    color = _TOOL_COLORS.get(name, "white")
                    detail = _format_tool_input(name, inp)
                    detail_str = f" [dim]{detail}[/dim]" if detail else ""
                    lines.append(f"{prefix}   [{color}]{name}[/{color}]{detail_str}")
                elif btype == "text":
                    text = block.get("text", "").strip()
                    if text:
                        first_line = text.split("\n")[0]
                        if len(first_line) > 80:
                            first_line = first_line[:77] + "…"
                        lines.append(f"{prefix} [dim italic]{first_line}[/dim italic]")

        if stop_reason == "end_turn":
            lines.append(f"{prefix} [dim]↩ done[/dim]")

    return lines


def _format_idle_duration(seconds: float) -> str:
    """Format seconds into a human-readable idle duration."""
    minutes = int(seconds / 60)
    if minutes < 1:
        return "< 1min"
    if minutes < 60:
        return f"{minutes}min"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    days = hours // 24
    return f"{days}d {hours % 24}h"


@app.command()
def clean(
    pids: list[str] = typer.Argument(
        None,
        help="Specific PID(s) to kill. If given, skips idle check.",
    ),
    idle_minutes: int = typer.Option(
        60, "--idle", "-i",
        help="Kill sessions idle longer than N minutes.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Skip confirmation prompt.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="Show what would be killed without doing it.",
    ),
):
    """Find and kill idle Claude Code sessions.

    Scans running sessions, checks log activity, and terminates
    those idle beyond the threshold. Shows session details before
    killing so you can review.

    You can also pass specific PID(s) to kill directly:

        dmt sessions clean 12345 67890
    """
    processes = _find_claude_processes()
    if not processes:
        console.print("[yellow]No running Claude Code sessions found.[/yellow]")
        raise typer.Exit()

    live_pids = {p["pid"] for p in processes}

    # Resolve cwds and match logs for all processes
    pid_cwds: dict[str, str] = {}
    for proc in processes:
        cwd = _get_cwd(proc["pid"])
        if cwd:
            pid_cwds[proc["pid"]] = cwd
    pid_logs = _match_pids_to_logs(processes, pid_cwds)

    def _build_session_info(pid: str, proc: dict) -> dict:
        cwd = pid_cwds.get(pid)
        project = _get_project_name(cwd) if cwd else "?"
        log_path, _ = pid_logs.get(pid, (None, None))
        state = _get_session_state(log_path) if log_path else {}
        last_msg = state.get("last_user_msg") or ""
        if last_msg:
            last_msg = _truncate_display(last_msg.split("\n")[0], 35)
        try:
            mtime = log_path.stat().st_mtime if log_path else 0
            idle_secs = time.time() - mtime if mtime else 0
        except OSError:
            idle_secs = 0
        return {
            "pid": pid,
            "project": project,
            "started": proc["started"],
            "idle_secs": idle_secs,
            "last_msg": last_msg,
            "status": state.get("status", "?"),
        }

    # If specific PIDs given, target those directly
    if pids:
        target_sessions: list[dict] = []
        for pid in pids:
            if pid not in live_pids:
                console.print(
                    f"[yellow]PID {pid} is not a running "
                    f"Claude Code session.[/yellow]"
                )
                continue
            proc = next(p for p in processes if p["pid"] == pid)
            target_sessions.append(_build_session_info(pid, proc))
        if not target_sessions:
            raise typer.Exit(1)
        idle_sessions = target_sessions
    else:
        threshold = idle_minutes * 60
        idle_sessions: list[dict] = []

        for proc in processes:
            info = _build_session_info(proc["pid"], proc)
            if (
                info["idle_secs"] >= threshold
                and info["status"] in ("idle", "permission")
            ):
                idle_sessions.append(info)

    if not idle_sessions:
        console.print(
            f"[green]No sessions idle for more than "
            f"{idle_minutes} minutes.[/green]"
        )
        raise typer.Exit()

    # Show target sessions
    title = (
        f"Target Sessions (PID: {', '.join(pids)})"
        if pids
        else f"Idle Sessions (> {idle_minutes}min)"
    )
    table = Table(title=title, show_lines=True)
    table.add_column("PID", style="cyan", width=7)
    table.add_column("Project", style="bold")
    table.add_column("Idle", style="red")
    table.add_column("Status")
    table.add_column("Last Message", style="dim")

    for s in sorted(
        idle_sessions,
        key=lambda x: x["idle_secs"],
        reverse=True,
    ):
        emoji = STATUS_EMOJI.get(s["status"], "?")
        table.add_row(
            s["pid"],
            s["project"],
            _format_idle_duration(s["idle_secs"]),
            emoji,
            s["last_msg"] or "(unknown)",
        )

    console.print(table)
    console.print(
        f"\n[bold]{len(idle_sessions)}[/bold] idle session(s) found."
    )

    if dry_run:
        console.print("[dim]Dry run — no sessions killed.[/dim]")
        raise typer.Exit()

    # Kill sessions one by one
    sorted_sessions = sorted(
        idle_sessions,
        key=lambda x: x["idle_secs"],
        reverse=True,
    )
    killed = 0
    skipped = 0
    kill_all = force

    for s in sorted_sessions:
        pid = s["pid"]
        emoji = STATUS_EMOJI.get(s["status"], "?")
        idle_str = _format_idle_duration(s["idle_secs"])
        msg = s["last_msg"] or "(unknown)"

        console.print()
        console.print(
            f"  {emoji} [cyan]{s['project']}[/cyan] "
            f"(PID [bold]{pid}[/bold], idle [red]{idle_str}[/red])"
        )
        console.print(f"  [dim]Last: {msg}[/dim]")

        if kill_all:
            do_kill = True
        else:
            choice = _prompt_kill(pid)
            if choice == "all":
                kill_all = True
                do_kill = True
            else:
                do_kill = choice == "yes"

        if not do_kill:
            skipped += 1
            console.print("  [dim]Skipped.[/dim]")
            continue

        try:
            subprocess.run(
                ["kill", pid],
                capture_output=True,
                timeout=5,
            )
            console.print("  [red]Killed.[/red]")
            killed += 1
        except (OSError, subprocess.TimeoutExpired):
            console.print("  [yellow]Failed to kill.[/yellow]")

    console.print(
        f"\n[green]Done.[/green] "
        f"Killed: {killed}, Skipped: {skipped}"
    )


def _prompt_kill(pid: str) -> str:
    """Prompt user: y/N/a. Returns 'yes', 'no', or 'all'."""
    while True:
        choice = console.input(
            f"  Kill PID {pid}? [dim](y/N/a=all)[/dim] ",
        ).strip().lower()
        if choice in ("y", "yes"):
            return "yes"
        if choice in ("a", "all"):
            return "all"
        # Default to no (empty, n, or anything else)
        return "no"
