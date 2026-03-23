"""DMT Web UI - FastAPI application."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import sessionmaker

from do_my_tasks.cli.commands.session import (
    _find_claude_processes,
    _get_cwd,
    _get_project_name,
    _get_session_state,
    _match_pids_to_logs,
)
from do_my_tasks.core.task_manager import TaskManager
from do_my_tasks.intelligence.summarizer import Summarizer
from do_my_tasks.models.task import TaskPriority, TaskStatus
from do_my_tasks.storage.database import get_session_factory
from do_my_tasks.storage.repository import (
    CommitRepository,
    ProjectRepository,
    SessionRepository,
    TaskRepository,
    UnitOfWork,
)
from do_my_tasks.storage.tables import CommitRow, SessionRow, TaskRow

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["app_version"] = pkg_version("do-my-tasks")

app = FastAPI(title="DMT Dashboard", docs_url=None, redoc_url=None)

# ─── helpers ──────────────────────────────────────────────────────────────────

def _get_session_factory() -> sessionmaker:
    return get_session_factory()


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _fmt_minutes(minutes: float) -> str:
    if minutes < 60:
        return f"{int(minutes)}m"
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h}h {m}m" if m else f"{h}h"


def _fmt_number(n: int) -> str:
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def _as_local(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Format a local naive datetime (DB values are stored as local time)."""
    if not dt:
        return ""
    # DB stores local naive datetimes; display as-is
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime(fmt)


templates.env.filters["fmt_minutes"] = _fmt_minutes
templates.env.filters["fmt_number"] = _fmt_number
templates.env.filters["as_local"] = _as_local


# ─── live session helpers ──────────────────────────────────────────────────────

def _get_git_branch(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip() or ""
    except Exception:
        return ""


def get_live_sessions() -> tuple[list[dict], list[dict]]:
    processes = _find_claude_processes()
    if not processes:
        return [], []

    pid_cwds: dict[str, str] = {}
    for proc in processes:
        cwd = _get_cwd(proc["pid"])
        if cwd:
            pid_cwds[proc["pid"]] = cwd

    pid_logs = _match_pids_to_logs(processes, pid_cwds)

    sessions = []
    untracked = []
    for proc in processes:
        pid = proc["pid"]
        cwd = pid_cwds.get(pid)
        project = _get_project_name(cwd) if cwd else "unknown"
        log_path, _ = pid_logs.get(pid, (None, None))

        elapsed = ""
        if proc["started"]:
            delta = datetime.now() - proc["started"]
            elapsed = _fmt_minutes(float(int(delta.total_seconds() / 60)))

        if not log_path:
            untracked.append({
                "pid": pid,
                "cwd": cwd or "",
                "started": proc["started"].strftime("%H:%M") if proc["started"] else "-",
                "elapsed": elapsed,
                "note": proc["note"],
            })
            continue

        state = _get_session_state(log_path) if log_path else {}
        status = state.get("status", "waiting")

        elapsed = ""
        if proc["started"]:
            delta = datetime.now() - proc["started"]
            elapsed = _fmt_minutes(float(int(delta.total_seconds() / 60)))

        branch = _get_git_branch(cwd) if cwd else ""

        last_ts = state.get("last_ts")

        sessions.append({
            "pid": pid,
            "project": project,
            "cwd": cwd or "",
            "branch": branch,
            "started": proc["started"].strftime("%H:%M") if proc["started"] else "-",
            "elapsed": elapsed,
            "status": status,
            "note": proc["note"],
            "last_user_msg": state.get("last_user_msg") or "",
            "tools": state.get("tools") or [],
            "files_modified": state.get("files_modified") or [],
            "commands_run": state.get("commands_run") or [],
            "last_ts": last_ts.strftime("%H:%M:%S") if last_ts else "",
        })
    return sessions, untracked


# ─── routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, date: str | None = None):
    date_str = date or _today()
    sf = _get_session_factory()
    summarizer = Summarizer(sf)
    summary = summarizer.generate(date_str)

    live_sessions, untracked_sessions = get_live_sessions()

    # All active projects with last activity
    with UnitOfWork(sf) as uow:
        proj_repo = ProjectRepository(uow.session)
        all_projects = proj_repo.list_active()

        all_projects_info = []
        for p in all_projects:
            last_session = (
                uow.session.query(SessionRow)
                .filter_by(project_name=p.name)
                .order_by(SessionRow.start_time.desc())
                .first()
            )
            last_commit = (
                uow.session.query(CommitRow)
                .filter_by(project_name=p.name)
                .order_by(CommitRow.timestamp.desc())
                .first()
            )
            candidates = [
                t for t in [
                    last_session.start_time if last_session else None,
                    last_commit.timestamp if last_commit else None,
                ] if t
            ]
            last_active = max(candidates) if candidates else None
            is_live = any(s["project"] == p.name for s in live_sessions)
            all_projects_info.append({
                "name": p.name,
                "path": p.path,
                "main_branch": p.main_branch,
                "last_active": last_active,
                "is_live": is_live,
            })
        all_projects_info.sort(key=lambda x: x["last_active"] or datetime.min, reverse=True)

        # Active tasks (pending + in_progress)
        task_repo = TaskRepository(uow.session)
        active_tasks = uow.session.query(TaskRow).filter(
            TaskRow.status.in_(["pending", "in_progress"])
        ).order_by(TaskRow.priority, TaskRow.date).all()

    # Date navigation
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
    is_today = date_str == _today()

    return templates.TemplateResponse(request, "dashboard.html", {
        "date": date_str,
        "prev_date": prev_date,
        "next_date": next_date,
        "is_today": is_today,
        "summary": summary,
        "live_sessions": live_sessions,
        "all_projects": all_projects_info,
        "active_tasks": active_tasks,
        "active_page": "dashboard",
    })


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    date: str | None = None,
    project: str | None = None,
    status: str | None = None,
):
    date_str = date or _today()
    sf = _get_session_factory()
    tm = TaskManager(sf)
    rows = tm.list(project_name=project, status=status, date=date_str if date else None)

    # Get project list for filter
    with UnitOfWork(sf) as uow:
        proj_repo = ProjectRepository(uow.session)
        projects = [p.name for p in proj_repo.list_active()]

    # Group by status
    pending = [r for r in rows if r.status == "pending"]
    in_progress = [r for r in rows if r.status == "in_progress"]
    completed = [r for r in rows if r.status == "completed"]
    rolled_over = [r for r in rows if r.status == "rolled_over"]

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
    is_today = date_str == _today()

    return templates.TemplateResponse(request, "tasks.html", {
        "date": date_str,
        "prev_date": prev_date,
        "next_date": next_date,
        "is_today": is_today,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "rolled_over": rolled_over,
        "all_tasks": rows,
        "projects": projects,
        "selected_project": project or "",
        "selected_status": status or "",
        "active_page": "tasks",
    })


@app.post("/tasks/add")
async def add_task(
    title: str = Form(...),
    project: str = Form(...),
    priority: str = Form("medium"),
    description: str = Form(""),
    date: str = Form(""),
):
    sf = _get_session_factory()
    tm = TaskManager(sf)
    task_date = date or _today()
    tm.create(
        title=title,
        project_name=project,
        priority=TaskPriority(priority),
        description=description or None,
        date=task_date,
    )
    return RedirectResponse(url=f"/tasks?date={task_date}", status_code=303)


@app.post("/tasks/{task_id}/complete")
async def complete_task(task_id: int, date: str = Form("")):
    sf = _get_session_factory()
    tm = TaskManager(sf)
    result = tm.update_status(task_id, TaskStatus.COMPLETED)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    redirect_date = date or _today()
    return RedirectResponse(url=f"/tasks?date={redirect_date}", status_code=303)


@app.post("/tasks/{task_id}/delete")
async def delete_task(task_id: int, date: str = Form("")):
    sf = _get_session_factory()
    tm = TaskManager(sf)
    result = tm.delete(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    redirect_date = date or _today()
    return RedirectResponse(url=f"/tasks?date={redirect_date}", status_code=303)


@app.post("/tasks/{task_id}/status")
async def update_task_status(task_id: int, status: str = Form(...), date: str = Form("")):
    sf = _get_session_factory()
    tm = TaskManager(sf)
    tm.update_status(task_id, TaskStatus(status))
    redirect_date = date or _today()
    return RedirectResponse(url=f"/tasks?date={redirect_date}", status_code=303)


@app.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request, date: str | None = None):
    date_str = date or _today()
    sf = _get_session_factory()

    live, untracked = get_live_sessions()

    with UnitOfWork(sf) as uow:
        repo = SessionRepository(uow.session)
        session_rows = repo.get_by_date(date_str)

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
    is_today = date_str == _today()

    return templates.TemplateResponse(request, "sessions.html", {
        "date": date_str,
        "prev_date": prev_date,
        "next_date": next_date,
        "is_today": is_today,
        "live_sessions": live,
        "untracked_sessions": untracked,
        "session_rows": session_rows,
        "active_page": "sessions",
    })


@app.get("/activity", response_class=HTMLResponse)
async def activity_page(request: Request, date: str | None = None):
    date_str = date or _today()
    sf = _get_session_factory()

    with UnitOfWork(sf) as uow:
        commit_repo = CommitRepository(uow.session)
        commits = commit_repo.get_by_date(date_str)

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
    is_today = date_str == _today()

    # Group commits by project
    by_project: dict[str, list[Any]] = {}
    for c in commits:
        by_project.setdefault(c.project_name, []).append(c)

    return templates.TemplateResponse(request, "activity.html", {
        "date": date_str,
        "prev_date": prev_date,
        "next_date": next_date,
        "is_today": is_today,
        "commits": commits,
        "by_project": by_project,
        "active_page": "activity",
    })


@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    sf = _get_session_factory()

    with UnitOfWork(sf) as uow:
        proj_repo = ProjectRepository(uow.session)
        projects = proj_repo.list_active()

        project_stats = []
        for p in projects:
            sessions = uow.session.query(SessionRow).filter_by(project_name=p.name).all()
            commits = uow.session.query(CommitRow).filter_by(project_name=p.name).all()
            tasks = uow.session.query(TaskRow).filter_by(project_name=p.name).all()

            active_tasks = [t for t in tasks if t.status in ("pending", "in_progress")]
            total_minutes = sum(s.duration_minutes or 0 for s in sessions)
            total_tokens = sum(
                (s.total_input_tokens or 0) + (s.total_output_tokens or 0) for s in sessions
            )
            total_additions = sum(c.additions or 0 for c in commits)
            total_deletions = sum(c.deletions or 0 for c in commits)

            last_session_time = max(
                (s.start_time for s in sessions if s.start_time), default=None
            )
            last_commit_time = max(
                (c.timestamp for c in commits if c.timestamp), default=None
            )
            candidates = [t for t in (last_session_time, last_commit_time) if t]
            last_active = max(candidates) if candidates else None

            project_stats.append({
                "name": p.name,
                "slug": p.slug or "",
                "path": p.path,
                "main_branch": p.main_branch,
                "created_at": p.created_at,
                "total_sessions": len(sessions),
                "total_minutes": total_minutes,
                "total_tokens": total_tokens,
                "total_commits": len(commits),
                "total_additions": total_additions,
                "total_deletions": total_deletions,
                "active_tasks": len(active_tasks),
                "last_active": last_active,
            })

    project_stats.sort(key=lambda x: x["last_active"] or datetime.min, reverse=True)

    return templates.TemplateResponse(request, "projects.html", {
        "projects": project_stats,
        "active_page": "projects",
    })


@app.post("/projects/add")
async def add_project(
    path: str = Form(...),
    name: str = Form(""),
    main_branch: str = Form("main"),
    slug: str = Form(""),
):
    from do_my_tasks.utils.config import ProjectConfig, load_config, save_config

    resolved = Path(path.strip().rstrip("/")).expanduser()
    project_name = name.strip() or resolved.name
    project_slug = slug.strip() or None

    # Update config.toml
    config = load_config()
    if not any(p.name == project_name for p in config.projects):
        config.projects.append(
            ProjectConfig(name=project_name, path=str(resolved), main_branch=main_branch)
        )
        save_config(config)

    # Update DB
    sf = _get_session_factory()
    with UnitOfWork(sf) as uow:
        ProjectRepository(uow.session).upsert(project_name, str(resolved), main_branch, slug=project_slug)
        uow.commit()

    return RedirectResponse(url="/projects", status_code=303)


@app.post("/projects/edit")
async def edit_project(
    original_name: str = Form(...),
    name: str = Form(...),
    path: str = Form(...),
    main_branch: str = Form("main"),
    slug: str = Form(""),
):
    from do_my_tasks.utils.config import load_config, save_config

    resolved = str(Path(path.strip().rstrip("/")).expanduser())
    new_name = name.strip()
    new_slug = slug.strip() or None

    # Update config.toml
    config = load_config()
    for p in config.projects:
        if p.name == original_name:
            p.name = new_name
            p.path = resolved
            p.main_branch = main_branch
            break
    save_config(config)

    # Update DB
    sf = _get_session_factory()
    with UnitOfWork(sf) as uow:
        repo = ProjectRepository(uow.session)
        row = repo.get_by_name(original_name)
        if row:
            row.name = new_name
            row.path = resolved
            row.main_branch = main_branch
            row.slug = new_slug
        else:
            repo.upsert(new_name, resolved, main_branch, slug=new_slug)
        uow.commit()

    return RedirectResponse(url="/projects", status_code=303)


@app.get("/guide", response_class=HTMLResponse)
async def guide_page(request: Request):
    return templates.TemplateResponse(request, "guide.html", {
        "active_page": "guide",
    })


@app.get("/api/live-sessions")
async def api_live_sessions():
    """JSON endpoint for auto-refreshing live session data."""
    sessions, untracked = get_live_sessions()
    return {"sessions": sessions, "untracked": untracked}


@app.post("/api/sessions/{pid}/kill")
async def kill_session(pid: str):
    """Send SIGTERM to a live session process."""
    import os
    import signal

    # Only allow killing idle sessions
    sessions, _ = get_live_sessions()
    match = next((s for s in sessions if s["pid"] == pid), None)
    if not match:
        raise HTTPException(status_code=404, detail="Session not found")

    status = match.get("status", "")
    if status in ("working", "permission", "waiting"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot kill session with status '{status}'",
        )

    try:
        os.kill(int(pid), signal.SIGTERM)
        return {"ok": True, "pid": pid}
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail="Process already gone")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
