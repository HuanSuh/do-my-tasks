# DMT — Do My Tasks

**Intelligent daily activity tracker & task manager for Claude Code power users.**

Automatically collects Claude Code session logs and Git commits, tracks tasks with priority analysis, and monitors live sessions — all from a single CLI or web dashboard.

[한국어 README →](README.ko.md)

---

## Screenshots

| Dashboard | Sessions |
|-----------|----------|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Sessions](docs/screenshots/sessions.png) |

| Projects | Activity |
|----------|----------|
| ![Projects](docs/screenshots/projects.png) | ![Activity](docs/screenshots/activity.png) |

---

## Overview

DMT integrates with Claude Code's session lifecycle to give you a clear picture of what you worked on, what got committed, and what still needs to be done. It runs in the background, auto-collects on session end, and surfaces everything through a clean web UI or terminal commands.

```
┌─────────────────────────────────────────────────────┐
│  Claude Code session ends                           │
│       ↓  (Stop hook)                                │
│  dmt collect  →  parses JSONL + git commits         │
│       ↓                                             │
│  SQLite DB  →  web dashboard / CLI / menu bar       │
└─────────────────────────────────────────────────────┘
```

---

## Install

### macOS — One-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/HuanSuh/do-my-tasks/main/scripts/install.sh | bash
```

This script:
1. Installs the package via `pipx` (or `pip` as fallback)
2. Builds `/Applications/DoMyTasks.app` — a lightweight status bar app
3. Registers a LaunchAgent for auto-start at login
4. Adds `dmt collect` to Claude Code's `Stop` hook automatically

After install, look for the **◆** icon in your menu bar.

### Manual (dev / non-macOS)

```bash
git clone https://github.com/HuanSuh/do-my-tasks.git
cd do-my-tasks
poetry install
poetry run dmt --version
```

### Requirements

- Python 3.11+
- macOS (menu bar app); Linux/Windows work for CLI only
- Git (for commit analysis)

### Uninstall

```bash
bash scripts/uninstall.sh
```

---

## Quick Start

```bash
# 1. Register your projects
dmt config discover           # Auto-detect from ~/.claude/projects/
dmt config add /path/to/repo  # Or register manually

# 2. Collect today's activity
dmt collect

# 3. View summary
dmt summary

# 4. Open web dashboard
dmt web
```

---

## Claude Code Hook Setup

DMT auto-collects when a Claude session ends. The installer sets this up automatically, but you can also add it manually to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "dmt collect" }]
      }
    ]
  }
}
```

---

## Menu Bar App

The macOS status bar app provides quick access without opening a terminal:

| Menu Item | Action |
|-----------|--------|
| **Open Dashboard** | Opens `http://127.0.0.1:7317` in browser |
| **Session Watch: OFF / ON** | Toggles real-time session monitoring |
| **Notifications** | Toggle macOS notifications on/off (checkmark) |
| **Poll Interval ▶** | Submenu: 5s / 10s / 30s / 60s (checkmark on current) |
| **Quit DMT** | Stops all background processes |

- Web server starts automatically in the background on launch
- Watch mode icon changes to **◆●** when active
- Registered as a LaunchAgent — starts at login
- Settings (notifications, interval) persist across restarts in `~/.config/do_my_tasks/menubar.json`
- Changing a setting while Watch is running applies immediately without manual restart

---

## CLI Reference

### `dmt collect`

Parses Claude Code session logs and Git commits for a given date.

```bash
dmt collect                        # Today
dmt collect --date 2026-03-15      # Specific date
dmt collect --project myapp        # One project only
```

**What gets collected:**
- Claude sessions: message counts, tools used, token usage, duration, cwd, git branch
- Git commits: author, message, files changed, additions/deletions, commit type
- **Resume segments:** If you run `claude --resume <uuid>`, the new activity is saved as a separate daily entry (linked to the original session)

---

### `dmt summary`

Generates a daily activity report.

```bash
dmt summary                        # Print to terminal
dmt summary --save                 # Save to ~/.config/do_my_tasks/reports/
dmt summary --date 2026-03-15
```

Report includes: project stats, token usage, code changes, task progress.

---

### `dmt plan`

Shows a prioritized TODO list based on recent commits and tasks.

```bash
dmt plan                           # Print plan
dmt plan --save                    # Also create tasks in DB
```

Generates three sections: rolled-over tasks, high-priority items (from commit analysis), and suggested follow-ups.

---

### `dmt sessions`

Monitor live Claude Code processes.

```bash
dmt sessions                       # List running sessions
dmt sessions --detail              # Show last message, tools, files
dmt sessions watch                 # Real-time monitoring + notifications
dmt sessions watch --idle 20       # Custom idle threshold (seconds)
dmt sessions clean                 # Interactive cleanup of idle sessions
dmt sessions clean --force         # Kill all idle sessions without prompt
```

**Session statuses:**

| Status | Meaning |
|--------|---------|
| `idle` | Waiting for your input |
| `permission` | Waiting for tool approval |
| `working` | Processing your request |
| `waiting` | Session open, no activity yet |

**Watch mode** polls sessions and sends macOS notifications:
- ✅ **Completion** — Shows what was done + next task suggestion
- ⏸️ **Permission needed** — Shows which tool is waiting for approval

---

### `dmt tasks`

Manage daily tasks.

```bash
dmt tasks add "Fix auth bug" --priority high --project myapp
dmt tasks list
dmt tasks list --status pending --project myapp
dmt tasks complete T-0001
dmt tasks update T-0001 --priority high
dmt tasks delete T-0001
dmt tasks rollover                 # Move incomplete tasks to today
```

Task IDs use the `T-0001` format. Priority: `high`, `medium`, `low`. Status: `pending`, `in_progress`, `completed`.

---

### `dmt config`

Manage registered projects and configuration.

```bash
dmt config discover                # Auto-detect projects
dmt config add /path/to/repo       # Register a project
dmt config add /path --name myapp --branch develop
dmt config remove myapp
dmt config list                    # Show registered projects
dmt config show                    # Show full config
```

---

### `dmt web`

Launch the web dashboard.

```bash
dmt web                            # http://127.0.0.1:7317
dmt web --port 8080
dmt web --no-open                  # Don't auto-open browser
```

---

### Global options

```bash
dmt --verbose collect              # Debug logging
dmt --json tasks list              # JSON output
dmt --version
```

---

## Web Dashboard

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Today's overview: sessions, commits, tasks, live activity |
| Tasks | `/tasks` | Create, complete, filter tasks by project/status/date |
| Sessions | `/sessions` | Live sessions + recorded history with resume tracking |
| Activity | `/activity` | Commit history grouped by project |
| Projects | `/projects` | Project stats and management |
| Guide | `/guide` | Built-in documentation (English / 한국어) |

---

## Priority Scoring

Commit priority is calculated automatically from four signals:

| Signal | Weight | What it looks at |
|--------|--------|-----------------|
| Keywords | 40% | fix, bug, security, urgent → high; chore, docs → low |
| Change volume | 30% | Lines added + deleted |
| File criticality | 20% | auth, config, schema, migration files score high |
| Temporal | 10% | More recent = higher score |

Thresholds: **HIGH** > 7.5 · **MEDIUM** > 4.0 · **LOW** ≤ 4.0

Weights and keywords are customizable in `~/.config/do_my_tasks/config.toml`.

---

## Session Resume Tracking

When you run `claude --resume <uuid>`, Claude appends new messages to the existing session file. DMT detects this and saves the resumed activity as a new **segment** tied to today's date, so your daily stats stay accurate.

- Segment 0 = original session
- Segment 1, 2, … = each subsequent resume
- Sessions page shows a **↩ resume** badge for resumed segments

---

## Data Storage

| What | Where |
|------|-------|
| Database | `~/.config/do_my_tasks/data.db` |
| Config | `~/.config/do_my_tasks/config.toml` |
| Reports | `~/.config/do_my_tasks/reports/YYYY-MM-DD.md` |
| Watch logs | `~/.dmt/logs/dmt_watch_log_*.log` (auto-deleted after 5 days) |

Set `DMT_DB_PATH` to override the database location.

---

## Project Structure

```
src/do_my_tasks/
├── cli/commands/       # collect, summary, plan, tasks, sessions, config, web
├── core/               # collector, session_parser, git_analyzer, task_manager
├── intelligence/       # summarizer, priority_analyzer, todo_generator
├── menubar/            # macOS status bar app (rumps)
├── models/             # Pydantic domain models
├── storage/            # SQLAlchemy ORM + Repository pattern
├── web/                # FastAPI app + Jinja2 templates
└── utils/              # Config loader, logging
```

---

## Development

```bash
poetry install
poetry run pytest
poetry run ruff check src/
poetry run mypy src/
```

---

## License

MIT
