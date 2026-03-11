"""dmt tasks - Task CRUD management."""

from __future__ import annotations

import json
from datetime import date

import typer
from rich.console import Console
from rich.table import Table

from do_my_tasks.cli.output import is_json_mode
from do_my_tasks.core.task_manager import TaskManager
from do_my_tasks.models.task import TaskPriority, TaskStatus
from do_my_tasks.storage.database import get_session_factory

app = typer.Typer()
console = Console()

PRIORITY_COLORS = {"high": "red", "medium": "yellow", "low": "green"}
STATUS_ICONS = {
    "pending": "[ ]",
    "in_progress": "[~]",
    "completed": "[x]",
    "rolled_over": "[>]",
}


def _task_to_dict(t) -> dict:
    """Convert a task row to a JSON-serializable dict."""
    return {
        "id": f"T-{t.id:04d}",
        "status": t.status,
        "priority": t.priority,
        "title": t.title,
        "project": t.project_name,
        "date": t.date,
        "rollover_count": t.rollover_count,
        "requires_review": t.requires_review,
    }


@app.command("add")
def add_task(
    title: str = typer.Argument(..., help="Task title."),
    project: str = typer.Option("general", "--project", "-p", help="Project name."),
    priority: str = typer.Option("medium", "--priority", "-P", help="Priority: high/medium/low."),
    description: str | None = typer.Option(None, "--desc", "-d", help="Task description."),
):
    """Add a new task."""
    try:
        pri = TaskPriority(priority.lower())
    except ValueError:
        if is_json_mode():
            print(json.dumps({"error": f"Invalid priority: {priority}"}))
        else:
            console.print(f"[red]Invalid priority: {priority}. Use high/medium/low.[/red]")
        raise typer.Exit(1)

    session_factory = get_session_factory()
    manager = TaskManager(session_factory)
    task_row = manager.create(
        title=title,
        project_name=project,
        priority=pri,
        description=description,
        date=date.today().isoformat(),
    )

    if is_json_mode():
        print(json.dumps({
            "id": f"T-{task_row.id:04d}",
            "title": title,
            "project": project,
            "priority": priority.lower(),
            "status": "pending",
        }))
    else:
        console.print(f"[green]Created task T-{task_row.id:04d}: {title}[/green]")


@app.command("list")
def list_tasks(
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project."),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status."),
    target_date: str | None = typer.Option(None, "--date", "-d", help="Filter by date."),
    stale: bool = typer.Option(False, "--stale", help="Show only stale (3+ rollover) tasks."),
):
    """List tasks."""
    session_factory = get_session_factory()
    manager = TaskManager(session_factory)

    if stale:
        tasks = manager.get_stale()
    else:
        tasks = manager.list(project_name=project, status=status, date=target_date)

    if is_json_mode():
        print(json.dumps({
            "tasks": [_task_to_dict(t) for t in tasks],
            "count": len(tasks),
        }, ensure_ascii=False))
        return

    if not tasks:
        console.print("[dim]No tasks found.[/dim]")
        raise typer.Exit()

    table = Table(show_header=True, title="Tasks")
    table.add_column("ID", style="dim", width=7)
    table.add_column("Status", width=5)
    table.add_column("Priority", width=8)
    table.add_column("Title")
    table.add_column("Project", style="dim")
    table.add_column("Date", style="dim")
    table.add_column("Roll", justify="right", width=4)

    for t in tasks:
        pri_color = PRIORITY_COLORS.get(t.priority, "white")
        status_icon = STATUS_ICONS.get(t.status, "?")
        review = " !" if t.requires_review else ""
        table.add_row(
            f"T-{t.id:04d}",
            status_icon,
            f"[{pri_color}]{t.priority.upper()}[/{pri_color}]",
            f"{t.title}{review}",
            t.project_name,
            t.date,
            str(t.rollover_count) if t.rollover_count > 0 else "",
        )
    console.print(table)


@app.command("complete")
def complete_task(
    task_id: str = typer.Argument(..., help="Task ID (e.g., T-0001 or just 1)."),
):
    """Mark a task as completed."""
    tid = _parse_task_id(task_id)
    session_factory = get_session_factory()
    manager = TaskManager(session_factory)
    result = manager.update_status(tid, TaskStatus.COMPLETED)
    if result:
        if is_json_mode():
            print(json.dumps({"id": f"T-{tid:04d}", "title": result.title, "status": "completed"}))
        else:
            console.print(f"[green]Completed T-{tid:04d}: {result.title}[/green]")
    else:
        if is_json_mode():
            print(json.dumps({"error": f"Task T-{tid:04d} not found"}))
        else:
            console.print(f"[red]Task T-{tid:04d} not found.[/red]")
        raise typer.Exit(1)


@app.command("update")
def update_task(
    task_id: str = typer.Argument(..., help="Task ID."),
    status: str | None = typer.Option(None, "--status", "-s", help="New status."),
    priority: str | None = typer.Option(None, "--priority", "-P", help="New priority."),
):
    """Update a task's status or priority."""
    tid = _parse_task_id(task_id)
    session_factory = get_session_factory()
    manager = TaskManager(session_factory)
    updates: dict = {"id": f"T-{tid:04d}"}

    if status:
        try:
            new_status = TaskStatus(status.lower())
        except ValueError:
            if is_json_mode():
                print(json.dumps({"error": f"Invalid status: {status}"}))
            else:
                console.print(f"[red]Invalid status: {status}[/red]")
            raise typer.Exit(1)
        result = manager.update_status(tid, new_status)
        if result:
            updates["status"] = new_status.value
            if not is_json_mode():
                console.print(f"[green]Updated T-{tid:04d} status → {new_status.value}[/green]")
        else:
            if is_json_mode():
                print(json.dumps({"error": f"Task T-{tid:04d} not found"}))
            else:
                console.print(f"[red]Task T-{tid:04d} not found.[/red]")
            raise typer.Exit(1)

    if priority:
        try:
            new_priority = TaskPriority(priority.lower())
        except ValueError:
            if is_json_mode():
                print(json.dumps({"error": f"Invalid priority: {priority}"}))
            else:
                console.print(f"[red]Invalid priority: {priority}[/red]")
            raise typer.Exit(1)
        result = manager.update_priority(tid, new_priority)
        if result:
            updates["priority"] = new_priority.value
            if not is_json_mode():
                console.print(f"[green]Updated T-{tid:04d} priority → {new_priority.value}[/green]")
        else:
            if is_json_mode():
                print(json.dumps({"error": f"Task T-{tid:04d} not found"}))
            else:
                console.print(f"[red]Task T-{tid:04d} not found.[/red]")
            raise typer.Exit(1)

    if is_json_mode():
        print(json.dumps(updates))


@app.command("delete")
def delete_task(
    task_id: str = typer.Argument(..., help="Task ID."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
):
    """Delete a task."""
    tid = _parse_task_id(task_id)
    session_factory = get_session_factory()
    manager = TaskManager(session_factory)

    if not force and not is_json_mode():
        confirm = typer.confirm(f"Delete task T-{tid:04d}?")
        if not confirm:
            raise typer.Abort()

    if manager.delete(tid):
        if is_json_mode():
            print(json.dumps({"id": f"T-{tid:04d}", "deleted": True}))
        else:
            console.print(f"[green]Deleted T-{tid:04d}.[/green]")
    else:
        if is_json_mode():
            print(json.dumps({"error": f"Task T-{tid:04d} not found"}))
        else:
            console.print(f"[red]Task T-{tid:04d} not found.[/red]")
        raise typer.Exit(1)


@app.command("rollover")
def rollover_tasks(
    from_date: str | None = typer.Option(None, "--from", help="Date to rollover from."),
):
    """Manually rollover incomplete tasks."""
    from datetime import date as date_type
    from datetime import timedelta

    if from_date:
        source = from_date
    else:
        yesterday = date_type.today() - timedelta(days=1)
        source = yesterday.isoformat()

    target = date.today().isoformat()

    session_factory = get_session_factory()
    manager = TaskManager(session_factory)
    rolled = manager.rollover(source, target)

    if is_json_mode():
        print(json.dumps({
            "from_date": source,
            "to_date": target,
            "rolled_over": rolled,
        }))
    else:
        console.print(f"[green]Rolled over {rolled} tasks from {source} to {target}.[/green]")


def _parse_task_id(task_id: str) -> int:
    """Parse task ID from T-0001 or plain number format."""
    cleaned = task_id.strip().upper()
    if cleaned.startswith("T-"):
        cleaned = cleaned[2:]
    try:
        return int(cleaned)
    except ValueError:
        if is_json_mode():
            print(json.dumps({"error": f"Invalid task ID: {task_id}"}))
        else:
            console.print(f"[red]Invalid task ID: {task_id}[/red]")
        raise typer.Exit(1)
