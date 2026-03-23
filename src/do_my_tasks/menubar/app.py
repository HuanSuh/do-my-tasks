"""DMT Menu Bar App — macOS status bar integration via rumps."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import rumps

DASHBOARD_URL = "http://127.0.0.1:7317"
DMT_PORT = 7317

# SVG-sourced monochrome icon embedded as PNG bytes (fallback: text title)
# Using rumps title-only mode keeps things simple without an asset file.
ICON_TITLE = "◆"  # shown in menu bar if no icon file


def _find_dmt() -> str:
    """Locate the dmt executable (handles pipx venvs and direct installs)."""
    import shutil
    path = shutil.which("dmt")
    if path:
        return path
    # Common pipx location
    pipx_bin = Path.home() / ".local" / "bin" / "dmt"
    if pipx_bin.exists():
        return str(pipx_bin)
    raise RuntimeError("dmt executable not found. Is it installed?")


class DMTApp(rumps.App):
    def __init__(self):
        super().__init__("DMT", title=ICON_TITLE, quit_button=None)

        self._dmt = _find_dmt()
        self._web_proc: subprocess.Popen | None = None
        self._watch_proc: subprocess.Popen | None = None

        # Build menu
        self._watch_item = rumps.MenuItem("Session Watch: OFF", callback=self._toggle_watch)
        self._dash_item = rumps.MenuItem("Open Dashboard", callback=self._open_dashboard)
        self._quit_item = rumps.MenuItem("Quit DMT", callback=self._quit)

        self.menu = [
            self._dash_item,
            None,  # separator
            self._watch_item,
            None,
            self._quit_item,
        ]

        # Start web server in background
        threading.Thread(target=self._start_web, daemon=True).start()

    # ── Web server ────────────────────────────────────────────────────────────

    def _start_web(self):
        """Start the web dashboard server; retry a few times if the port is busy."""
        for attempt in range(3):
            try:
                self._web_proc = subprocess.Popen(
                    [self._dmt, "web", "--no-open", "--port", str(DMT_PORT)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception as e:
                if attempt == 2:
                    rumps.alert("DMT", f"Failed to start web server: {e}")
                time.sleep(2)

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def _open_dashboard(self, _):
        webbrowser.open(DASHBOARD_URL)

    # ── Session Watch ─────────────────────────────────────────────────────────

    def _toggle_watch(self, sender):
        if self._watch_running():
            self._stop_watch()
        else:
            self._start_watch()

    def _watch_running(self) -> bool:
        return self._watch_proc is not None and self._watch_proc.poll() is None

    def _start_watch(self):
        try:
            self._watch_proc = subprocess.Popen(
                [self._dmt, "sessions", "watch"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            rumps.alert("DMT", f"Failed to start session watch: {e}")
            return
        self._watch_item.title = "Session Watch: ON ✓"
        self.title = "◆●"

    def _stop_watch(self):
        if self._watch_proc:
            self._watch_proc.terminate()
            self._watch_proc = None
        self._watch_item.title = "Session Watch: OFF"
        self.title = ICON_TITLE

    # ── Quit ──────────────────────────────────────────────────────────────────

    def _quit(self, _):
        self._stop_watch()
        if self._web_proc:
            self._web_proc.terminate()
        rumps.quit_application()


def main():
    DMTApp().run()


if __name__ == "__main__":
    main()
