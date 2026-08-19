#!/bin/bash
# One-time local setup: install the `gswitch` CLI wrapper, build the menu bar app,
# and report what still needs doing. Safe to re-run.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.gswitch" "$HOME/.local/bin"

printf '#!/bin/bash\nexec "%s/gswitch" "$@"\n' "$HERE" > "$HOME/.local/bin/gswitch"
chmod +x "$HOME/.local/bin/gswitch" "$HERE/gswitch"
echo "installed ~/.local/bin/gswitch"

"$HERE/build_menubar.sh"

echo
"$HERE/gswitch" doctor || true
