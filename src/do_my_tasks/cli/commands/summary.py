"""dmt summary - Generate daily summary report."""

from __future__ import annotations

from datetime import date, datetime

import typer
from rich.console import Console

from do_my_tasks.intelligence.summarizer import Summarizer
from do_my_tasks.reporting.generator import ReportGenerator
from do_my_tasks.storage.database import get_session_factory
from do_my_tasks.utils.config import load_config

app = typer.Typer()
console = Console()


@app.callback(invoke_without_command=True)
def summary(
    target_date: str | None = typer.Option(
        None, "--date", "-d", help="Date to summarize (YYYY-MM-DD). Default: today.",
    ),
    save: bool = typer.Option(True, "--save/--no-save", help="Save report to file."),
):
    """Generate daily summary report."""
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

    summarizer = Summarizer(session_factory)
    daily_summary = summarizer.generate(date_str)

    if not daily_summary.projects:
        console.print(f"[yellow]No activity found for {date_str}.[/yellow]")
        console.print("[dim]Run 'dmt collect' first to gather data.[/dim]")
        raise typer.Exit()

    generator = ReportGenerator(config)
    report_md = generator.render(daily_summary)

    # Display in terminal
    console.print()
    console.print(report_md)

    # Save to file
    if save:
        report_path = generator.save(daily_summary, report_md)
        console.print(f"\n[dim]Report saved to {report_path}[/dim]")
