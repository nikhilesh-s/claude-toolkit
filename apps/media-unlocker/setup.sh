#!/bin/bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$HOME/.media-unlocker"
VENV="$BASE/venv"
BIN="$HOME/.local/bin"
PLIST="$HOME/Library/LaunchAgents/com.nik.mediaunlock.plist"
PORT="${MEDIAUNLOCK_PORT:-8770}"
TAILSCALE_HOST="${MEDIAUNLOCK_TAILSCALE_HOST:-}"

if [ -z "$TAILSCALE_HOST" ] && command -v tailscale >/dev/null 2>&1; then
  TAILSCALE_HOST="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Self",{}).get("DNSName","").rstrip("."))' 2>/dev/null || true)"
fi

ALLOWED_HOSTS="127.0.0.1:*,localhost:*"
[ -z "$TAILSCALE_HOST" ] || ALLOWED_HOSTS="$ALLOWED_HOSTS,$TAILSCALE_HOST:8443,$TAILSCALE_HOST"

mkdir -p "$BASE" "$BIN" "$HOME/Library/LaunchAgents"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required: https://brew.sh" >&2
  exit 1
fi

brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list gallery-dl >/dev/null 2>&1 || brew install gallery-dl
brew list yt-dlp >/dev/null 2>&1 || brew install yt-dlp

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$HERE/requirements.txt"
"$VENV/bin/python" "$HERE/smoke_test.py"

cp "$HERE/mediaunlock" "$BIN/mediaunlock"
chmod +x "$BIN/mediaunlock"

python3 - <<PY
from pathlib import Path
src = Path("$HERE/com.nik.mediaunlock.plist.template").read_text()
src = src.replace("__PYTHON__", "$VENV/bin/python")
src = src.replace("__SERVER__", "$HERE/server.py")
src = src.replace("__HOME__", str(Path.home()))
src = src.replace("__PORT__", "$PORT")
src = src.replace("__ALLOWED_HOSTS__", "$ALLOWED_HOSTS")
Path("$PLIST").write_text(src)
PY

launchctl bootout "gui/$(id -u)/com.nik.mediaunlock" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 1

echo
echo "Installed. Next:"
echo "  mediaunlock doctor"
echo "  mediaunlock funnel"
echo "  mediaunlock url"
echo
echo "Then add the printed /mcp URL to ChatGPT Developer Mode as a custom connector named Media Unlocker."
echo "For Instagram, Safari cookies are used by default. Set MEDIAUNLOCK_BROWSER=chrome if Chrome is your logged-in browser."
