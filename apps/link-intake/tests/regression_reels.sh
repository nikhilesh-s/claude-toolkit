#!/bin/bash
# Runs all 10 wishlist Reels (manifest read from apps/media-unlocker/test_wishlist_reels.sh, never edited)
# through link-intake as Wishlist intents. Uses the media-unlocker cache; never deletes pre-existing jobs.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LI="$HERE/bin/linkintake"
SAVE=(); [ "${SMOKE_SAVE:-0}" = "1" ] && SAVE=(--save)
fail=0; n=0
while read -r url; do
  n=$((n+1)); echo; echo "=== reel $n: $url"
  "$LI" ingest "$url" -d wishlist -i "identify the product shown so I can add it to my dorm wishlist" ${SAVE[@]+"${SAVE[@]}"} || fail=1
done < <(grep -o "https://www.instagram.com/reel/[^']*" "$HERE/../media-unlocker/test_wishlist_reels.sh")
echo; [ "$fail" = 0 ] && echo "regression_reels: $n passed" || echo "regression_reels: FAILURES"
exit $fail
