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


def _get_last_log_timestamp(log_path: Path) -> datetime | None:
    """Get the timestamp of the last entry in a JSONL log file."""
    last_ts = None
    try:
        # Read last few lines efficiently
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            # Read last 4KB
            read_size = min(size, 4096)
            f.seek(size - read_size)
            data = f.read().decode("utf-8", errors="replace")

        for line in reversed(data.strip().splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts_str = entry.get("timestamp")
                if ts_str:
                    last_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    break
            except (json.JSONDecodeError, ValueError):
                continue
    except OSError:
        pass
    return last_ts


@app.callback(invoke_without_command=True)
def sessions(
    ctx: typer.Context,
    wide: bool = typer.Option(False, "--wide", "-w", help="Show full log paths."),
):
    """View Claude Code session information."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(live, wide=wide)


@app.command()
def live(
    wide: bool = typer.Option(
        False, "--wide", "-w", help="Show full log paths.",
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
    table.add_column("Log Path", style="dim")

    for proc in sorted(processes, key=lambda p: p["started"] or datetime.min, reverse=True):
        cwd = _get_cwd(proc["pid"])
        project = Path(cwd).name if cwd else "?"

        log_path, log_mtime = _find_log_file(cwd) if cwd else (None, None)

        if log_path:
            last_ts = _get_last_log_timestamp(log_path)
            last_update = last_ts.strftime("%m/%d %H:%M") if last_ts else (
                log_mtime.strftime("%m/%d %H:%M") if log_mtime else "-"
            )
            if wide:
                short_path = str(log_path).replace(str(Path.home()), "~")
            else:
                short_path = log_path.name
        else:
            last_update = "-"
            short_path = "(no log)"

        started_str = proc["started"].strftime("%m/%d %H:%M") if proc["started"] else "?"

        table.add_row(
            proc["pid"],
            project,
            started_str,
            last_update,
            proc["note"],
            short_path,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(processes)} sessions[/dim]")
