"""dmt config - Configuration management."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from do_my_tasks.storage.database import get_session_factory
from do_my_tasks.storage.repository import ProjectRepository, UnitOfWork
from do_my_tasks.utils.config import (
    discover_projects,
    get_config_path,
    load_config,
    save_config,
)

app = typer.Typer()
console = Console()


@app.command("show")
def show_config():
    """Show current configuration."""
    config = load_config()
    console.print(f"[bold]Config file:[/bold] {get_config_path()}")
    console.print(f"[bold]Claude projects dir:[/bold] {config.claude_projects_dir}")
    console.print(f"[bold]Reports dir:[/bold] {config.reports_dir}")
    console.print(f"[bold]Registered projects:[/bold] {len(config.projects)}")
    for p in config.projects:
        exists = Path(p.path).exists()
        status = "[green]OK[/green]" if exists else "[red]NOT FOUND[/red]"
        console.print(f"  - {p.name}: {p.path} {status}")


@app.command("add")
def add_project(
    path: str = typer.Argument(..., help="Project directory path."),
    name: str | None = typer.Option(None, "--name", "-n", help="Project name (default: dirname)."),
    main_branch: str = typer.Option("main", "--branch", "-b", help="Main branch name."),
):
    """Register a project for tracking."""
    project_path = Path(path).resolve()
    if not project_path.exists():
        console.print(f"[red]Path does not exist: {project_path}[/red]")
        raise typer.Exit(1)

    project_name = name or project_path.name
    config = load_config()

    # Check if already registered
    if any(p.name == project_name for p in config.projects):
        console.print(f"[yellow]Project '{project_name}' already registered.[/yellow]")
        raise typer.Exit()

    from do_my_tasks.utils.config import ProjectConfig

    config.projects.append(
        ProjectConfig(name=project_name, path=str(project_path), main_branch=main_branch)
    )
    save_config(config)

    # Also save to DB
    session_factory = get_session_factory()
    with UnitOfWork(session_factory) as uow:
        repo = ProjectRepository(uow.session)
        repo.upsert(project_name, str(project_path), main_branch)
        uow.commit()

    console.print(f"[green]Added project '{project_name}' ({project_path})[/green]")


@app.command("remove")
def remove_project(
    name: str = typer.Argument(..., help="Project name to remove."),
):
    """Unregister a project."""
    config = load_config()
    config.projects = [p for p in config.projects if p.name != name]
    save_config(config)

    session_factory = get_session_factory()
    with UnitOfWork(session_factory) as uow:
        repo = ProjectRepository(uow.session)
        repo.remove(name)
        uow.commit()

    console.print(f"[green]Removed project '{name}'[/green]")


@app.command("list")
def list_projects():
    """List all registered projects."""
    config = load_config()
    if not config.projects:
        console.print(
            "[dim]No projects registered. Run 'dmt config discover' to find projects.[/dim]"
        )
        raise typer.Exit()

    table = Table(title="Registered Projects")
    table.add_column("Name")
    table.add_column("Path")
    table.add_column("Branch", style="dim")
    table.add_column("Status")

    for p in config.projects:
        exists = Path(p.path).exists()
        status = "[green]OK[/green]" if exists else "[red]NOT FOUND[/red]"
        table.add_row(p.name, p.path, p.main_branch, status)

    console.print(table)


@app.command("discover")
def discover():
    """Auto-discover projects from ~/.claude/projects/."""
    config = load_config()
    discovered = discover_projects(config.claude_projects_dir)

    if not discovered:
        console.print("[yellow]No projects found in Claude projects directory.[/yellow]")
        raise typer.Exit()

    registered_names = {p.name for p in config.projects}
    new_projects = [p for p in discovered if p.name not in registered_names]

    if not new_projects:
        console.print("[dim]All discovered projects are already registered.[/dim]")
        raise typer.Exit()

    console.print(f"[bold]Found {len(new_projects)} new project(s):[/bold]")
    for p in new_projects:
        console.print(f"  - {p.name}: {p.path}")

    if typer.confirm("Register all discovered projects?"):
        config.projects.extend(new_projects)
        save_config(config)

        session_factory = get_session_factory()
        with UnitOfWork(session_factory) as uow:
            repo = ProjectRepository(uow.session)
            for p in new_projects:
                repo.upsert(p.name, p.path)
            uow.commit()

        console.print(f"[green]Registered {len(new_projects)} project(s).[/green]")
