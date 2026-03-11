"""dmt collect - Collect daily activity data."""

from __future__ import annotations

from datetime import date, datetime

import typer
from rich.console import Console

from do_my_tasks.core.collector import DailyCollector
from do_my_tasks.storage.database import get_session_factory
from do_my_tasks.utils.config import load_config

app = typer.Typer()
console = Console()


@app.callback(invoke_without_command=True)
def collect(
    target_date: str | None = typer.Option(
        None, "--date", "-d", help="Date to collect (YYYY-MM-DD). Default: today.",
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Collect only this project.",
    ),
):
    """Collect daily activity data (Claude sessions + Git commits)."""
    if target_date:
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Invalid date format: {target_date}. Use YYYY-MM-DD.[/red]")
            raise typer.Exit(1)
    else:
        dt = date.today()

    date_str = dt.isoformat()
    config = load_config()
    session_factory = get_session_factory()

    collector = DailyCollector(config, session_factory)
    result = collector.collect(date_str, project_filter=project)

    console.print()
    console.print(f"[bold green]Collection complete for {date_str}[/bold green]")
    console.print(f"  Sessions parsed: {result['sessions']}")
    console.print(f"  Commits found:   {result['commits']}")
    console.print(f"  Projects:        {result['projects']}")
    if result.get("errors"):
        console.print(f"  [yellow]Errors: {len(result['errors'])}[/yellow]")
        for err in result["errors"]:
            console.print(f"    [dim]- {err}[/dim]")
