"""dmt summary - Generate daily summary report."""

from __future__ import annotations

import json
from datetime import date, datetime

import typer
from rich.console import Console

from do_my_tasks.cli.output import is_json_mode
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
            if is_json_mode():
                print(json.dumps({"error": f"Invalid date format: {target_date}"}))
            else:
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
        if is_json_mode():
            print(json.dumps({"date": date_str, "projects": [], "message": "No activity found"}))
        else:
            console.print(f"[yellow]No activity found for {date_str}.[/yellow]")
            console.print("[dim]Run 'dmt collect' first to gather data.[/dim]")
        raise typer.Exit()

    generator = ReportGenerator(config)
    report_md = generator.render(daily_summary)

    if is_json_mode():
        output = {
            "date": date_str,
            "projects": [
                {
                    "name": p.project_name,
                    "path": p.project_path,
                    "commits": len(p.commits),
                    "sessions": len(p.sessions),
                    "active_minutes": p.total_session_minutes,
                    "lines_added": p.total_additions,
                    "lines_deleted": p.total_deletions,
                    "input_tokens": p.total_input_tokens,
                    "output_tokens": p.total_output_tokens,
                }
                for p in daily_summary.projects
            ],
            "statistics": {
                "total_sessions": daily_summary.total_sessions,
                "total_commits": daily_summary.total_commits,
                "total_files_changed": daily_summary.total_files_changed,
                "total_lines_added": daily_summary.total_additions,
                "total_lines_deleted": daily_summary.total_deletions,
                "total_active_minutes": daily_summary.total_active_minutes,
                "total_input_tokens": daily_summary.total_input_tokens,
                "total_output_tokens": daily_summary.total_output_tokens,
            },
            "report_markdown": report_md,
        }

        if save:
            report_path = generator.save(daily_summary, report_md)
            output["report_path"] = str(report_path)

        print(json.dumps(output, ensure_ascii=False))
    else:
        console.print()
        console.print(report_md)

        if save:
            report_path = generator.save(daily_summary, report_md)
            console.print(f"\n[dim]Report saved to {report_path}[/dim]")
