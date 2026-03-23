#!/usr/bin/env bash
# DMT installer for macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/HuanSuh/do-my-tasks/main/scripts/install.sh | bash
set -euo pipefail

REPO="git+https://github.com/HuanSuh/do-my-tasks.git"
APP_NAME="DMT"
APP_DEST="/Applications/${APP_NAME}.app"
LAUNCH_AGENT_ID="io.github.huansuh.dmt"
LAUNCH_AGENT_PLIST="$HOME/Library/LaunchAgents/${LAUNCH_AGENT_ID}.plist"
DMT_PORT=7317

# ── helpers ───────────────────────────────────────────────────────────────────

info()    { echo "  ▸ $*"; }
success() { echo "  ✓ $*"; }
error()   { echo "  ✗ $*" >&2; exit 1; }
step()    { echo; echo "── $* ──────────────────────────────────────────"; }

# ── preflight ─────────────────────────────────────────────────────────────────

step "Checking requirements"

# macOS only
[[ "$(uname)" == "Darwin" ]] || error "This installer is macOS-only."

# Python 3.11+
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 11 ]]; }; then
        error "Python 3.11+ required (found $PY_VERSION). Install from https://python.org"
    fi
    PYTHON=$(command -v python3)
    success "Python $PY_VERSION"
else
    error "Python 3 not found. Install from https://python.org"
fi

# pip
$PYTHON -m pip --version &>/dev/null || error "pip not found."
success "pip found"

# ── install package ───────────────────────────────────────────────────────────

step "Installing DMT"

# Prefer pipx for isolated install; fall back to pip --user
if command -v pipx &>/dev/null; then
    info "Using pipx"
    # Uninstall first if already present (to pick up updates)
    pipx uninstall do-my-tasks 2>/dev/null || true
    pipx install "${REPO}[menubar]"
    DMT_BIN="$HOME/.local/bin/dmt"
elif $PYTHON -m pipx --version &>/dev/null 2>&1; then
    info "Using python -m pipx"
    $PYTHON -m pipx uninstall do-my-tasks 2>/dev/null || true
    $PYTHON -m pipx install "${REPO}[menubar]"
    DMT_BIN="$HOME/.local/bin/dmt"
else
    info "pipx not found — falling back to pip install --user"
    $PYTHON -m pip install --quiet --user "${REPO}[menubar]"
    DMT_BIN="$($PYTHON -m site --user-base)/bin/dmt"
fi

[[ -f "$DMT_BIN" ]] || DMT_BIN=$(command -v dmt 2>/dev/null || true)
[[ -n "$DMT_BIN" ]] || error "dmt binary not found after install."
success "dmt installed → $DMT_BIN"

# Also install rumps into the same environment that dmt lives in
VENV_PYTHON=$(dirname "$DMT_BIN")/../lib/python*/site-packages 2>/dev/null || true
# rumps should already be installed via [menubar] extra — just verify
if ! $PYTHON -c "import rumps" 2>/dev/null; then
    info "Installing rumps separately"
    $PYTHON -m pip install --quiet --user "rumps>=0.4.0"
fi
success "rumps ready"

# ── build .app bundle ─────────────────────────────────────────────────────────

step "Building ${APP_NAME}.app"

TMP_APP=$(mktemp -d)/"${APP_NAME}.app"
mkdir -p "${TMP_APP}/Contents/MacOS"
mkdir -p "${TMP_APP}/Contents/Resources"

# Info.plist
cat > "${TMP_APP}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>             <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>       <string>${LAUNCH_AGENT_ID}</string>
  <key>CFBundleVersion</key>          <string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleExecutable</key>       <string>${APP_NAME}</string>
  <key>LSUIElement</key>              <true/>
  <key>NSHighResolutionCapable</key>  <true/>
  <key>LSMinimumSystemVersion</key>   <string>12.0</string>
</dict>
</plist>
PLIST

# Launcher script (the actual executable inside .app)
LAUNCHER="${TMP_APP}/Contents/MacOS/${APP_NAME}"
cat > "$LAUNCHER" <<LAUNCHER
#!/usr/bin/env bash
# Add pipx bin to PATH in case it's not in the login environment
export PATH="\$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:\$PATH"
exec "${PYTHON}" -m do_my_tasks.menubar.app "\$@"
LAUNCHER
chmod +x "$LAUNCHER"

# Copy to /Applications (ask for confirmation if already exists)
if [[ -d "$APP_DEST" ]]; then
    info "Replacing existing ${APP_NAME}.app"
    rm -rf "$APP_DEST"
fi
cp -R "$TMP_APP" "$APP_DEST"
rm -rf "$(dirname "$TMP_APP")"
success "App installed → $APP_DEST"

# ── LaunchAgent (start at login) ──────────────────────────────────────────────

step "Configuring auto-start"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$LAUNCH_AGENT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>${LAUNCH_AGENT_ID}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${APP_DEST}/Contents/MacOS/${APP_NAME}</string>
  </array>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <false/>
  <key>StandardOutPath</key>   <string>/tmp/dmt-menubar.log</string>
  <key>StandardErrorPath</key> <string>/tmp/dmt-menubar.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST

# Load it now
launchctl unload "$LAUNCH_AGENT_PLIST" 2>/dev/null || true
launchctl load -w "$LAUNCH_AGENT_PLIST"
success "LaunchAgent registered (starts at login)"

# ── Claude hooks ──────────────────────────────────────────────────────────────

step "Setting up Claude Code hook"

CLAUDE_SETTINGS="$HOME/.claude/settings.json"
if [[ -f "$CLAUDE_SETTINGS" ]]; then
    # Check if Stop hook already exists
    if grep -q '"Stop"' "$CLAUDE_SETTINGS" 2>/dev/null; then
        info "Claude Stop hook already configured — skipping"
    else
        # Inject Stop hook using Python (safe JSON manipulation)
        $PYTHON - <<PYEOF
import json, sys
from pathlib import Path

p = Path("${CLAUDE_SETTINGS}")
data = json.loads(p.read_text())

hook = {"matcher": "", "hooks": [{"type": "command", "command": "${DMT_BIN} collect"}]}
data.setdefault("hooks", {}).setdefault("Stop", [])
if not any(
    any(h.get("command","").startswith("${DMT_BIN} collect") for h in entry.get("hooks",[]))
    for entry in data["hooks"]["Stop"]
):
    data["hooks"]["Stop"].append(hook)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print("  ✓ Added 'dmt collect' to Claude Stop hook")
else:
    print("  ▸ Hook already present")
PYEOF
    fi
else
    info "~/.claude/settings.json not found — skipping hook setup"
    info "To add manually, add to ~/.claude/settings.json:"
    info '  "hooks": {"Stop": [{"matcher":"","hooks":[{"type":"command","command":"dmt collect"}]}]}'
fi

# ── done ──────────────────────────────────────────────────────────────────────

echo
echo "╔════════════════════════════════════════════╗"
echo "║          DMT installed successfully!       ║"
echo "╚════════════════════════════════════════════╝"
echo
echo "  App:        $APP_DEST"
echo "  Dashboard:  http://127.0.0.1:${DMT_PORT}"
echo "  Auto-start: enabled (login)"
echo
echo "  Starting DMT now..."
open "$APP_DEST"
echo
echo "  ◆ Look for the ◆ icon in your menu bar."
echo "  Run 'dmt config discover' to register your projects."
echo
