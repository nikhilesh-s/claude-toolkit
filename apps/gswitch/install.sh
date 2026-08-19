#!/bin/bash
# gswitch installer: builds GSwitch.app, installs `gswitch` CLI wrapper, and
# (once ngrok is configured) loads the LaunchAgent that keeps the server up.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GS="$HOME/.gswitch"
mkdir -p "$GS"

# real uv, skipping any dev-shell shims
UV_BIN="$(ls /opt/homebrew/bin/uv "$HOME/.local/bin/uv" /usr/local/bin/uv 2>/dev/null | head -1 || true)"
[ -n "$UV_BIN" ] || { echo "ERROR: uv not found; install from https://docs.astral.sh/uv/"; exit 1; }

# 1. Dock app
rm -rf "$HERE/GSwitch.app"
osacompile -o "$HERE/GSwitch.app" "$HERE/GSwitch.applescript"
echo "built $HERE/GSwitch.app  (drag it to your Dock)"

# 2. CLI wrapper
mkdir -p "$HOME/.local/bin"
printf '#!/bin/bash\nexec "%s" run "%s" "$@"\n' "$UV_BIN" "$HERE/gswitch.py" > "$HOME/.local/bin/gswitch"
chmod +x "$HOME/.local/bin/gswitch"
echo "installed ~/.local/bin/gswitch  (ensure ~/.local/bin is on PATH)"

# 3. LaunchAgent — only once ngrok domain is configured, else it would crash-loop
PLIST="$HOME/Library/LaunchAgents/com.nik.gswitch.plist"
if [ -s "$GS/ngrok_domain" ]; then
    sed -e "s|__UV__|$UV_BIN|g" -e "s|__SCRIPT__|$HERE/gswitch.py|g" -e "s|__HOME__|$HOME|g" \
        "$HERE/com.nik.gswitch.plist.template" > "$PLIST"
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "LaunchAgent loaded — server + ngrok now run automatically"
    "$HOME/.local/bin/gswitch" url
else
    echo "SKIPPED LaunchAgent: no $GS/ngrok_domain yet."
    echo "After ngrok setup (see README), put your static domain in that file and re-run install.sh"
fi
