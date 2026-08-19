#!/bin/bash
# One-time local setup: build the Dock app, install the `gswitch` CLI wrapper,
# and report what still needs doing. Safe to re-run.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.gswitch" "$HOME/.local/bin"

rm -rf "$HERE/GSwitch.app"
osacompile -o "$HERE/GSwitch.app" "$HERE/GSwitch.applescript"
echo "built $HERE/GSwitch.app  — drag it to your Dock"

printf '#!/bin/bash\nexec "%s/gswitch" "$@"\n' "$HERE" > "$HOME/.local/bin/gswitch"
chmod +x "$HOME/.local/bin/gswitch" "$HERE/gswitch"
echo "installed ~/.local/bin/gswitch"

echo
"$HERE/gswitch" doctor || true
