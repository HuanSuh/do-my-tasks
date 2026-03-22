"""Main CLI entry point using Typer."""

from __future__ import annotations

import typer

from do_my_tasks import __version__
from do_my_tasks.cli.commands.collect import app as collect_app
from do_my_tasks.cli.commands.config import app as config_app
from do_my_tasks.cli.commands.plan import app as plan_app
from do_my_tasks.cli.commands.session import app as session_app
from do_my_tasks.cli.commands.summary import app as summary_app
from do_my_tasks.cli.commands.task import app as task_app
from do_my_tasks.cli.commands.web import app as web_app
from do_my_tasks.utils.logger import setup_logger

app = typer.Typer(
    name="dmt",
    help="DMT - Intelligent daily activity tracker & task manager for Claude Code.",
    no_args_is_help=True,
)

# Register sub-commands
app.add_typer(collect_app, name="collect", help="Collect daily activity data (sessions + git).")
app.add_typer(summary_app, name="summary", help="Generate daily summary report.")
app.add_typer(plan_app, name="plan", help="Show tomorrow's TODO list.")
app.add_typer(task_app, name="tasks", help="Manage tasks (add/list/update/complete/delete).")
app.add_typer(session_app, name="sessions", help="View Claude Code session information.")
app.add_typer(config_app, name="config", help="Manage configuration and projects.")
app.add_typer(web_app, name="web", help="Launch the web dashboard on localhost.")


from do_my_tasks.cli.output import set_json_mode


def version_callback(value: bool):
    if value:
        typer.echo(f"dmt version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool | None = typer.Option(
        None, "--version", "-V", callback=version_callback, is_eager=True,
        help="Show version and exit.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format."),
):
    """DMT - Intelligent daily activity tracker & task manager for Claude Code."""
    set_json_mode(json_output)
    setup_logger(verbose=verbose)
