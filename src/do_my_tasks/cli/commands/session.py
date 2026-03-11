"""dmt sessions - View Claude Code session information."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


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
        if "/claude" not in args_str and args_str.strip() not in ("claude", "claude --resume"):
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
            ["lsof", "-a", "-p", pid, "-d", "cwd"],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().splitlines()
        if len(lines) >= 2:
            return lines[-1].split()[-1]
    except OSError:
        pass
    return None


def _find_log_file(cwd: str) -> tuple[Path | None, datetime | None]:
    """Find the most recent JSONL log file for a given project cwd.

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
        # Worktree: cwd contains .claude/worktrees/<name>
        # Search for dirs matching *--claude-worktrees-<name>
        if "/.claude/worktrees/" in cwd:
            wt_name = cwd.split("/.claude/worktrees/")[-1].rstrip("/")
            for d in base.iterdir():
                if d.is_dir() and d.name.endswith(f"--claude-worktrees-{wt_name}"):
                    search_dirs.append(d)

    best_file: Path | None = None
    best_mtime: float = 0

    for search_dir in search_dirs:
        for jsonl in search_dir.glob("*.jsonl"):
            if jsonl.name.startswith("agent-"):
                continue
            mtime = jsonl.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best_file = jsonl

    if best_file:
        mod_time = datetime.fromtimestamp(best_mtime)
        return best_file, mod_time

    return None, None


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
    """Get the timestamp of the last entry in a JSONL log file."""
    for line in reversed(_read_tail(log_path)):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts_str = entry.get("timestamp")
            if ts_str:
                return datetime.fromisoformat(
                    ts_str.replace("Z", "+00:00")
                )
        except (json.JSONDecodeError, ValueError):
            continue
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
            if isinstance(content, str) and content.strip():
                last_user_msg = content.strip()
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
        console.print("[yellow]No running Claude Code sessions found.[/yellow]")
        raise typer.Exit()

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

    for proc in sorted(
        processes,
        key=lambda p: p["started"] or datetime.min,
        reverse=True,
    ):
        cwd = _get_cwd(proc["pid"])
        project = Path(cwd).name if cwd else "?"

        log_path, log_mtime = (
            _find_log_file(cwd) if cwd else (None, None)
        )

        if log_path:
            last_ts = _get_last_log_timestamp(log_path)
            last_update = last_ts.strftime("%m/%d %H:%M") if last_ts else (
                log_mtime.strftime("%m/%d %H:%M") if log_mtime else "-"
            )
        else:
            last_update = "-"

        started_str = (
            proc["started"].strftime("%m/%d %H:%M")
            if proc["started"] else "?"
        )

        if not detail:
            if log_path:
                if wide:
                    display_path = str(log_path).replace(
                        str(Path.home()), "~",
                    )
                else:
                    display_path = log_path.name
            else:
                display_path = "(no log)"
            table.add_row(
                proc["pid"], project, started_str,
                last_update, proc["note"], display_path,
            )
        else:
            if log_path:
                activity = _get_session_activity(log_path)
                msg = activity["last_message"] or "(no message)"
                if activity["time_ago"]:
                    msg = f"{msg} [dim]({activity['time_ago']})[/dim]"
                tools_str = ", ".join(activity["tools"]) if activity["tools"] else "-"
            else:
                msg = "(no log)"
                tools_str = "-"
            table.add_row(
                proc["pid"], project, started_str,
                last_update, proc["note"], msg, tools_str,
            )

    console.print(table)
    console.print(f"\n[dim]Total: {len(processes)} sessions[/dim]")
