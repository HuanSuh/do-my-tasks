"""DMT Menu Bar App — macOS status bar integration via rumps."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import rumps

DASHBOARD_URL = "http://127.0.0.1:7317"
DMT_PORT = 7317
ICON_TITLE = "◆"
ICON_WATCH = "◆●"

WATCH_INTERVALS = [5, 10, 30, 60]  # seconds
SETTINGS_PATH = Path.home() / ".config" / "do_my_tasks" / "menubar.json"


def _find_dmt() -> str:
    """Locate the dmt executable (handles pipx venvs, pip --user, and direct installs)."""
    import shutil
    import sys
    import sysconfig

    # 1. PATH lookup (works when launched from terminal or correctly configured LaunchAgent)
    path = shutil.which("dmt")
    if path:
        return path

    candidates = [
        # 2. Same bin dir as the running Python (venv / pip --user same interpreter)
        Path(sys.executable).parent / "dmt",
        # 3. pipx default location
        Path.home() / ".local" / "bin" / "dmt",
        # 4. macOS pip --user scripts dir (e.g. ~/Library/Python/3.11/bin/dmt)
        Path(sysconfig.get_path("scripts", "posix_user") or "") / "dmt",
        # 5. Homebrew Python user scripts
        Path.home() / "Library" / "Python" /
        f"{sys.version_info.major}.{sys.version_info.minor}" / "bin" / "dmt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "dmt executable not found. "
        f"Searched: {', '.join(str(c) for c in candidates)}"
    )


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        return {}


def _save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    except Exception:
        pass


class DMTApp(rumps.App):
    def __init__(self):
        super().__init__("DMT", title=ICON_TITLE, quit_button=None)

        self._dmt = _find_dmt()
        self._web_proc: subprocess.Popen | None = None
        self._watch_proc: subprocess.Popen | None = None
        self._settings = _load_settings()

        # ── Menu items ────────────────────────────────────────────────────────

        self._dash_item = rumps.MenuItem("Open Dashboard", callback=self._open_dashboard)
        self._watch_item = rumps.MenuItem("Session Watch: OFF", callback=self._toggle_watch)

        # Notifications toggle (checkmark = enabled)
        self._notify_item = rumps.MenuItem("Notifications", callback=self._toggle_notify)
        self._notify_item.state = self._settings.get("notify", True)

        # Poll interval submenu
        self._interval_menu = rumps.MenuItem("Poll Interval")
        self._interval_items: dict[int, rumps.MenuItem] = {}
        for secs in WATCH_INTERVALS:
            item = rumps.MenuItem(f"{secs}s", callback=self._set_interval)
            self._interval_items[secs] = item
            self._interval_menu.add(item)
        self._sync_interval_checkmarks()

        self._quit_item = rumps.MenuItem("Quit DMT", callback=self._quit)

        self.menu = [
            self._dash_item,
            None,
            self._watch_item,
            None,
            self._notify_item,
            self._interval_menu,
            None,
            self._quit_item,
        ]

        # Start web server
        threading.Thread(target=self._start_web, daemon=True).start()

    # ── Persistence ───────────────────────────────────────────────────────────

    @property
    def _interval(self) -> int:
        return self._settings.get("interval", 10)

    @property
    def _notify(self) -> bool:
        return self._settings.get("notify", True)

    def _sync_interval_checkmarks(self):
        current = self._interval
        for secs, item in self._interval_items.items():
            item.state = secs == current

    # ── Web server ────────────────────────────────────────────────────────────

    def _start_web(self):
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

    def _toggle_watch(self, _):
        if self._watch_running():
            self._stop_watch()
        else:
            self._start_watch()

    def _watch_running(self) -> bool:
        return self._watch_proc is not None and self._watch_proc.poll() is None

    def _start_watch(self):
        cmd = [self._dmt, "sessions", "watch", "--interval", str(self._interval)]
        if not self._notify:
            cmd.append("--no-notify")
        try:
            self._watch_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            rumps.alert("DMT", f"Failed to start session watch: {e}")
            return
        self._watch_item.title = "Session Watch: ON ✓"
        self.title = ICON_WATCH

    def _stop_watch(self):
        if self._watch_proc:
            self._watch_proc.terminate()
            self._watch_proc = None
        self._watch_item.title = "Session Watch: OFF"
        self.title = ICON_TITLE

    def _restart_watch_if_running(self):
        """Restart watch so new settings take effect immediately."""
        if self._watch_running():
            self._stop_watch()
            self._start_watch()

    # ── Notifications toggle ──────────────────────────────────────────────────

    def _toggle_notify(self, sender):
        self._settings["notify"] = not self._notify
        sender.state = self._settings["notify"]
        _save_settings(self._settings)
        self._restart_watch_if_running()

    # ── Poll interval ─────────────────────────────────────────────────────────

    def _set_interval(self, sender):
        # Find selected interval from title (e.g. "10s" → 10)
        try:
            secs = int(sender.title.rstrip("s"))
        except ValueError:
            return
        self._settings["interval"] = secs
        _save_settings(self._settings)
        self._sync_interval_checkmarks()
        self._restart_watch_if_running()

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
