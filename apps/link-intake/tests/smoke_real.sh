#!/bin/bash
# The one V1 end-to-end test, CLI form. Same flow as Raycast: one Reel, one destination, one instruction,
# extraction, review, save (local store; Google export is pending until Claude exports it).
# Raycast form: open Raycast -> "Intake Link" -> paste the Reel -> Personal Instagram Inspiration -> type the
# instruction -> Enter -> review -> Save.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LI="$HERE/bin/linkintake"
(cd "$HERE" && uv run --quiet python tests/test_router.py) || exit 1
REEL="$(grep -o "https://www.instagram.com/reel/[^']*" "$HERE/../media-unlocker/test_wishlist_reels.sh" | head -1)"
"$LI" ingest "$REEL" -d personal_ig -i "I like the cinematic wide shots and pacing near the beginning." --save --force
rc=$?
echo; "$LI" exports | head -12
exit $rc
