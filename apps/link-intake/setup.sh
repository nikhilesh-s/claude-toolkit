#!/bin/bash
# Installs the linkintake CLI (uv project + ~/.local/bin symlink) and the Raycast extension deps.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
command -v uv >/dev/null || { echo "uv missing: https://docs.astral.sh/uv/"; exit 1; }
(cd "$HERE" && uv sync --quiet)
mkdir -p "$HOME/.local/bin"
ln -sfn "$HERE/bin/linkintake" "$HOME/.local/bin/linkintake"
echo "linkintake -> $HOME/.local/bin/linkintake"
if command -v npm >/dev/null; then
  (cd "$HERE/raycast" && npm install --silent --no-audit --no-fund)
  echo "Raycast extension deps installed. Import it: Raycast -> Import Extension -> $HERE/raycast  (or: cd raycast && npm run dev)"
fi
"$HOME/.local/bin/linkintake" doctor || true
