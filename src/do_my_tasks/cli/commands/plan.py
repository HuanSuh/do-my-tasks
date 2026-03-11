"""dmt plan - Show tomorrow's TODO list."""

from __future__ import annotations

import json
from datetime import date

import typer
from rich.console import Console
from rich.table import Table

from do_my_tasks.cli.output import is_json_mode
from do_my_tasks.intelligence.todo_generator import TodoGenerator
from do_my_tasks.storage.database import get_session_factory
from do_my_tasks.utils.config import load_config

app = typer.Typer()
console = Console()


@app.callback(invoke_without_command=True)
def plan(
    save: bool = typer.Option(False, "--save", help="Save plan items as tasks."),
    target_date: str | None = typer.Option(
        None, "--date", "-d", help="Date to plan for (YYYY-MM-DD). Default: today.",
    ),
):
    """Show today's TODO list: rollover tasks + high priority items + follow-ups."""
    date_str = target_date or date.today().isoformat()
    config = load_config()
    session_factory = get_session_factory()

    generator = TodoGenerator(session_factory, config)
    plan_items = generator.generate(date_str)

    if is_json_mode():
        output: dict = {
            "date": date_str,
            "rolled_over": [
                {
                    "id": task.task_id or (f"T-{task.id:04d}" if task.id else None),
                    "priority": task.priority.value,
                    "title": task.title,
                    "project": task.project_name,
                    "rollover_count": task.rollover_count,
                    "requires_review": task.requires_review,
                }
                for task in plan_items.rolled_over
            ],
            "high_priority": plan_items.high_priority,
            "follow_ups": plan_items.follow_ups,
        }
        if save:
            saved = generator.save_as_tasks(plan_items, date_str)
            output["saved"] = saved
        print(json.dumps(output, ensure_ascii=False))
        return

    if not plan_items.has_items():
        console.print("[bold green]All clear! No pending items.[/bold green]")
        raise typer.Exit()

    # Rolled over tasks
    if plan_items.rolled_over:
        console.print("\n[bold]Rolled Over Tasks[/bold]")
        table = Table(show_header=True)
        table.add_column("ID", style="dim")
        table.add_column("Priority")
        table.add_column("Title")
        table.add_column("Project", style="dim")
        table.add_column("Rollover", justify="right")

        for task in plan_items.rolled_over:
            priority_color = {"high": "red", "medium": "yellow", "low": "green"}.get(
                task.priority.value, "white"
            )
            review = " [bold red]REVIEW[/bold red]" if task.requires_review else ""
            table.add_row(
                task.task_id or f"T-{task.id:04d}" if task.id else "?",
                f"[{priority_color}]{task.priority.value.upper()}[/{priority_color}]",
                f"{task.title}{review}",
                task.project_name,
                str(task.rollover_count),
            )
        console.print(table)

    # High priority items
    if plan_items.high_priority:
        console.print("\n[bold]High Priority Items[/bold]")
        for item in plan_items.high_priority:
            console.print(f"  [red]HIGH[/red] {item}")

    # Suggested follow-ups
    if plan_items.follow_ups:
        console.print("\n[bold]Suggested Follow-ups[/bold]")
        for item in plan_items.follow_ups:
            console.print(f"  [dim]-[/dim] {item}")

    if save:
        saved = generator.save_as_tasks(plan_items, date_str)
        console.print(f"\n[green]Saved {saved} items as tasks.[/green]")
