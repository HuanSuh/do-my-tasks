"""dmt web - Launch the local web dashboard."""

from __future__ import annotations

import typer

app = typer.Typer()


@app.callback(invoke_without_command=True)
def web(
    host: str = typer.Option("127.0.0.1", help="Host to bind to."),
    port: int = typer.Option(7317, help="Port to listen on."),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser automatically."),
):
    """Launch the DMT web dashboard on localhost."""
    try:
        import uvicorn
    except ImportError:
        typer.echo("uvicorn is required. Install it: pip install uvicorn", err=True)
        raise typer.Exit(1)

    if not no_open:
        import threading
        import time
        import webbrowser

        def _open_browser():
            time.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    typer.echo(f"DMT Dashboard → http://{host}:{port}")
    uvicorn.run(
        "do_my_tasks.web.app:app",
        host=host,
        port=port,
        log_level="warning",
    )
