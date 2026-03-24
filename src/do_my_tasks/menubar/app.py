"""DMT Menu Bar App — macOS status bar integration via rumps."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from importlib.metadata import version as pkg_version
from pathlib import Path

import rumps

DASHBOARD_URL = "http://127.0.0.1:7317"
DMT_PORT = 7317
ICON_PATH = str(Path(__file__).parent / "icon.png")
ICON_WATCH_PATH = str(Path(__file__).parent / "icon_watch.png")

WATCH_INTERVALS = [5, 10, 30, 60]  # seconds
WATCH_PID_FILE = Path.home() / ".dmt" / "watch.pid"
SETTINGS_PATH = Path.home() / ".config" / "do_my_tasks" / "menubar.json"
GITHUB_RELEASES_URL = "https://api.github.com/repos/HuanSuh/do-my-tasks/releases/latest"
INSTALL_URL = "git+https://github.com/HuanSuh/do-my-tasks.git"
UPDATE_SIGNAL_PATH = Path("/tmp/dmt_updated_to")


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.lstrip("v").split("."))


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
        super().__init__("DoMyTasks", icon=ICON_PATH, template=True, quit_button=None)

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

        self._update_item = rumps.MenuItem("Check for Updates…", callback=self._check_update)
        self._quit_item = rumps.MenuItem("Quit DMT", callback=self._quit)

        self.menu = [
            self._dash_item,
            None,
            self._watch_item,
            None,
            self._notify_item,
            self._interval_menu,
            None,
            self._update_item,
            None,
            self._quit_item,
        ]

        # Start web server
        threading.Thread(target=self._start_web, daemon=True).start()

        # 시작 시 외부에서 실행 중인 watch 상태 반영
        if self._watch_running():
            self._watch_item.title = "Session Watch: ON ✓"
            self.icon = ICON_WATCH_PATH
            self.template = False

        # 주기적으로 watch 상태를 UI에 동기화 (3초마다)
        rumps.Timer(self._sync_watch_state, 3).start()

        # 업데이트 후 재시작 시 완료 팝업
        if UPDATE_SIGNAL_PATH.exists():
            version = UPDATE_SIGNAL_PATH.read_text().strip()
            UPDATE_SIGNAL_PATH.unlink(missing_ok=True)
            rumps.Timer(lambda _: rumps.alert(f"Updated to v{version}", "DoMyTasks has been updated successfully."), 1).start()

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
        # 직접 실행한 subprocess 확인
        if self._watch_proc is not None and self._watch_proc.poll() is None:
            return True
        # CLI 등 외부에서 실행된 watch 확인 (PID 파일)
        try:
            pid = int(WATCH_PID_FILE.read_text().strip())
            os.kill(pid, 0)  # 프로세스 존재 여부만 확인
            return True
        except (OSError, ValueError, FileNotFoundError):
            return False

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
        self.icon = ICON_WATCH_PATH
        self.template = False

    def _stop_watch(self):
        if self._watch_proc:
            self._watch_proc.terminate()
            self._watch_proc = None
        # CLI 등 외부에서 실행된 watch도 종료
        try:
            pid = int(WATCH_PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError, FileNotFoundError):
            pass
        self._watch_item.title = "Session Watch: OFF"
        self.icon = ICON_PATH
        self.template = True

    def _restart_watch_if_running(self):
        """Restart watch so new settings take effect immediately."""
        if self._watch_running():
            self._stop_watch()
            self._start_watch()

    def _sync_watch_state(self, _):
        """watch 실제 실행 상태를 메뉴바 UI에 반영한다."""
        running = self._watch_running()
        currently_shown_on = self._watch_item.title == "Session Watch: ON ✓"
        if running and not currently_shown_on:
            self._watch_item.title = "Session Watch: ON ✓"
            self.icon = ICON_WATCH_PATH
            self.template = False
        elif not running and currently_shown_on:
            self._watch_proc = None
            self._watch_item.title = "Session Watch: OFF"
            self.icon = ICON_PATH
            self.template = True

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

    # ── Update ────────────────────────────────────────────────────────────────

    def _check_update(self, _):
        self._update_item.title = "Checking…"
        self._update_pending: dict | None = None
        threading.Thread(target=self._fetch_update_info, daemon=True).start()
        t = rumps.Timer(self._on_update_timer, 0.3)
        t.start()

    def _fetch_update_info(self):
        try:
            current = pkg_version("do-my-tasks")
        except Exception:
            current = "0.0.0"
        try:
            proc = subprocess.run(
                ["curl", "-s", "--max-time", "10",
                 "-H", "Accept: application/vnd.github+json",
                 "-H", "User-Agent: DoMyTasks",
                 GITHUB_RELEASES_URL],
                capture_output=True, text=True,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                raise RuntimeError(f"Network error (curl exit {proc.returncode})")
            data = json.loads(proc.stdout)
            if "tag_name" not in data:
                raise RuntimeError("No releases found on GitHub")
            latest = data["tag_name"].lstrip("v")
            tarball_url = data.get("tarball_url", INSTALL_URL)
            self._update_pending = {"ok": True, "current": current, "latest": latest, "tarball_url": tarball_url}
        except Exception as e:
            self._update_pending = {"ok": False, "error": str(e)}

    def _on_update_timer(self, timer):
        if self._update_pending is None:
            return  # 아직 로딩 중
        timer.stop()
        result = self._update_pending
        self._update_pending = None
        self._update_item.title = "Check for Updates…"

        if not result["ok"]:
            rumps.alert("Update check failed", result["error"])
            return

        current, latest = result["current"], result["latest"]
        if _version_tuple(latest) > _version_tuple(current):
            resp = rumps.alert(
                title=f"v{latest} Available",
                message=f"Current: v{current}  →  Latest: v{latest}\nWould you like to update now?",
                ok="Update",
                cancel="Later",
            )
            if resp == 1:
                threading.Thread(target=self._do_update, args=(latest, result["tarball_url"]), daemon=True).start()
        else:
            rumps.alert(f"You're up to date (v{current})")

    def _do_update(self, latest: str, tarball_url: str = INSTALL_URL):
        # 앱을 종료하고 외부 스크립트가 install → relaunch 처리
        relaunch_cmd = f"{sys.executable} -c 'from do_my_tasks.menubar.app import main; main()'"
        UPDATE_SIGNAL_PATH.write_text(latest)
        script = (
            f"sleep 2 && "
            f"{sys.executable} -m pip install --user --force-reinstall --quiet {tarball_url} && "
            f"nohup {relaunch_cmd} &>/dev/null &"
        )
        subprocess.Popen(["bash", "-c", script])
        self._stop_watch()
        if self._web_proc:
            self._web_proc.terminate()
        rumps.quit_application()

    # ── Quit ──────────────────────────────────────────────────────────────────

    def _quit(self, _):
        self._stop_watch()
        if self._web_proc:
            self._web_proc.terminate()
        rumps.quit_application()


def _kill_existing_instances() -> None:
    """현재 프로세스를 제외한 다른 menubar 인스턴스를 종료한다."""
    import os
    import signal

    current_pid = os.getpid()
    try:
        result = subprocess.run(
            ["pgrep", "-f", "do_my_tasks.menubar.app"],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().splitlines():
            pid = int(line.strip())
            if pid != current_pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
    except Exception:
        pass


def main():
    _kill_existing_instances()
    DMTApp().run()


if __name__ == "__main__":
    main()
