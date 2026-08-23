#!/bin/bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$HOME/.media-unlocker"
VENV="$BASE/venv"
BIN="$HOME/.local/bin"
PLIST="$HOME/Library/LaunchAgents/com.nik.mediaunlock.plist"
PORT="${MEDIAUNLOCK_PORT:-8770}"

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
