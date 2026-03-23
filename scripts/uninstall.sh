#!/usr/bin/env bash
# DMT uninstaller for macOS
set -euo pipefail

APP_DEST="/Applications/DMT.app"
LAUNCH_AGENT_ID="io.github.huansuh.dmt"
LAUNCH_AGENT_PLIST="$HOME/Library/LaunchAgents/${LAUNCH_AGENT_ID}.plist"

echo "Uninstalling DMT..."

# Stop and remove LaunchAgent
if [[ -f "$LAUNCH_AGENT_PLIST" ]]; then
    launchctl unload "$LAUNCH_AGENT_PLIST" 2>/dev/null || true
    rm -f "$LAUNCH_AGENT_PLIST"
    echo "  ✓ LaunchAgent removed"
fi

# Kill running menu bar app
pkill -f "DMT.app" 2>/dev/null || true

# Remove .app
if [[ -d "$APP_DEST" ]]; then
    rm -rf "$APP_DEST"
    echo "  ✓ DMT.app removed"
fi

# Remove package
if command -v pipx &>/dev/null; then
    pipx uninstall do-my-tasks 2>/dev/null && echo "  ✓ Package removed (pipx)"
elif python3 -m pipx --version &>/dev/null 2>&1; then
    python3 -m pipx uninstall do-my-tasks 2>/dev/null && echo "  ✓ Package removed (pipx)"
else
    python3 -m pip uninstall -y do-my-tasks 2>/dev/null && echo "  ✓ Package removed (pip)"
fi

echo
echo "  DMT has been uninstalled."
echo "  Data files (~/.config/do_my_tasks/) were NOT removed."
echo "  To also remove data: rm -rf ~/.config/do_my_tasks"
