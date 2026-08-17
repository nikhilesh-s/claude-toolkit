#!/usr/bin/env bash
# Install every plugin Arnav lists that is not installed here — into BOTH
# Claude profiles.
#
# Git cannot deliver a plugin. Upstream's repo only records that Arnav installed
# one, as a row in scripts/skill_index.tsv. This script reads those rows, works
# out what is missing on this machine, resolves each marketplace name to its
# GitHub repo, and runs the real install into ~/.claude AND ~/.claude-nebula.
#
#   ./scripts/nik_install_plugins.sh              install everything missing
#   ./scripts/nik_install_plugins.sh --dry-run    list what would be installed
#   ./scripts/nik_install_plugins.sh --list       just show missing plugins
#
# WHAT THIS ACTUALLY DOES: downloads and enables third-party code from ~29
# separate GitHub marketplaces, which then runs inside your agent sessions. Nik
# asked for full parity with Arnav's setup and for it to stay automatic, so the
# daily job calls this. Every install is logged. To go back to review-first,
# drop the nik_install_plugins.sh call from nik_daily_sync.sh.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

CB="/opt/homebrew/bin/claude"   # the real binary. The `claude` shell alias is
                                # `claude code`, which eats the `plugin` subcommand.
SOURCES="$REPO_ROOT/scripts/marketplace_sources.tsv"
RESOLVER="$REPO_ROOT/scripts/nik_resolve_marketplaces.sh"
PROFILES=("$HOME/.claude" "$HOME/.claude-nebula")

MODE="install"
case "${1:-}" in
  --dry-run) MODE="dry" ;;
  --list)    MODE="list" ;;
esac

[ -x "$CB" ] || { echo "claude binary not found at $CB" >&2; exit 1; }

# ---------------------------------------------------------------- what exists
installed_ids() {
  python3 -c "
import json,os,sys
p=os.path.join(sys.argv[1],'plugins','installed_plugins.json')
try: print('\n'.join(json.load(open(p)).get('plugins',{}).keys()))
except Exception: pass
" "$1" 2>/dev/null
}

# A plugin counts as present only if it is in BOTH profiles.
missing_for_profile() {
  local prof="$1" have
  have="$(installed_ids "$prof")"
  git show upstream/main:scripts/skill_index.tsv 2>/dev/null \
    | awk -F'\t' '$1=="plugin" && $2!="" && $3!="" {print $2"@"$3}' | sort -u \
    | while IFS= read -r id; do
        printf '%s\n' "$have" | grep -qxF "$id" || echo "$id"
      done
}

git fetch --quiet upstream main 2>/dev/null

ALL_MISSING="$(for p in "${PROFILES[@]}"; do missing_for_profile "$p"; done | sort -u)"

if [ -z "$ALL_MISSING" ]; then
  echo "Every plugin Arnav lists is already installed in both profiles."
  exit 0
fi

COUNT="$(printf '%s\n' "$ALL_MISSING" | grep -c .)"
echo "Missing in at least one profile: $COUNT plugin(s)"

if [ "$MODE" = "list" ] || [ "$MODE" = "dry" ]; then
  printf '%s\n' "$ALL_MISSING" | sed 's/^/  /'
  [ "$MODE" = "dry" ] && echo "(dry run — nothing installed)"
  exit 0
fi

# ------------------------------------------------------- resolve marketplaces
NEEDED_MKTS="$(printf '%s\n' "$ALL_MISSING" | awk -F'@' '{print $2}' | sort -u)"

for mkt in $NEEDED_MKTS; do
  grep -q "^$mkt	" "$SOURCES" 2>/dev/null && continue
  echo "resolving new marketplace: $mkt"
  row="$("$RESOLVER" "$mkt" 2>/dev/null | head -1)"
  [ -n "$row" ] && printf '%s\n' "$row" >>"$SOURCES"
done

# ------------------------------------------------------------------- install
ok=0; failed=0; skipped=0
FAILED_LIST=""

for prof in "${PROFILES[@]}"; do
  [ -d "$prof" ] || continue
  echo
  echo "=== profile: $prof ==="
  have="$(installed_ids "$prof")"

  # add every marketplace this profile will need, once
  for mkt in $NEEDED_MKTS; do
    repo="$(awk -F'\t' -v m="$mkt" '$1==m{print $2; exit}' "$SOURCES")"
    [ -n "$repo" ] && [ "$repo" != "UNRESOLVED" ] || continue
    CLAUDE_CONFIG_DIR="$prof" "$CB" plugin marketplace add "$repo" >/dev/null 2>&1
  done

  while IFS= read -r id; do
    [ -n "$id" ] || continue
    printf '%s\n' "$have" | grep -qxF "$id" && continue

    mkt="${id##*@}"
    repo="$(awk -F'\t' -v m="$mkt" '$1==m{print $2; exit}' "$SOURCES")"
    if [ -z "$repo" ] || [ "$repo" = "UNRESOLVED" ]; then
      echo "  SKIP  $id — marketplace '$mkt' could not be resolved to a repo"
      skipped=$((skipped + 1))
      continue
    fi

    if CLAUDE_CONFIG_DIR="$prof" "$CB" plugin install "$id" >/dev/null 2>&1; then
      echo "  ok    $id"
      ok=$((ok + 1))
    else
      echo "  FAIL  $id  (from $repo)"
      failed=$((failed + 1))
      FAILED_LIST="$FAILED_LIST$id "
    fi
  done <<<"$ALL_MISSING"
done

echo
echo "installed=$ok failed=$failed skipped=$skipped"
[ -n "$FAILED_LIST" ] && echo "failed: $FAILED_LIST"

for prof in "${PROFILES[@]}"; do
  [ -d "$prof" ] && echo "$(basename "$prof"): $(installed_ids "$prof" | grep -c .) plugins"
done

echo "Restart Claude Code for plugin changes to load."
