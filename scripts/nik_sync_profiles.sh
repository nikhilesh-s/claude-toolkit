#!/usr/bin/env bash
# Make ~/.claude and ~/.claude-nebula match each other.
#
# nik_install_skills.sh already keeps the 230 REPO skills in both profiles.
# This handles everything else that drifts:
#
#   1. foreign skills  — skills a third-party CLI wrote into one profile only.
#      The Hyperframes CLI did this: `npx hyperframes` dropped 26 skill folders
#      into ~/.claude/skills/ and never touched ~/.claude-nebula/skills/.
#   2. marketplaces    — a marketplace added in one profile only.
#   3. plugins         — a plugin installed in one profile only.
#   4. enabled state   — installed in both, but switched on in only one.
#
# Foreign skills are mirrored by SYMLINK, not copy: the profile that owns the
# real folder stays the single source of truth, so when the CLI updates its
# skills the other profile sees the change too. No copy to go stale.
#
#   ./scripts/nik_sync_profiles.sh              make both match
#   ./scripts/nik_sync_profiles.sh --dry-run    report drift, change nothing
set -uo pipefail

# Real interpreter, not whatever is on PATH. modern-python@trailofbits shims
# `python3` to `uv run python`, which fails outside a uv project.
PY="$(command -v /opt/homebrew/bin/python3 2>/dev/null \
   || command -v /usr/bin/python3 2>/dev/null \
   || command -v python3)"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CB="/opt/homebrew/bin/claude"
A="$HOME/.claude"
B="$HOME/.claude-nebula"
SOURCES="$REPO_ROOT/scripts/marketplace_sources.tsv"
BLOCKLIST="$REPO_ROOT/scripts/plugin_blocklist.txt"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
run() { if [ "$DRY" = 1 ]; then echo "    would: $*"; else "$@" >/dev/null 2>&1; fi; }

for d in "$A" "$B"; do
  [ -d "$d" ] || { echo "missing profile: $d" >&2; exit 1; }
done

is_blocked() {
  [ -f "$BLOCKLIST" ] || return 1
  grep -v '^[[:space:]]*#' "$BLOCKLIST" 2>/dev/null \
    | grep -v '^[[:space:]]*$' | grep -qxF "$1"
}

changed=0

# --- 1. foreign skills ------------------------------------------------------
# Anything in <profile>/skills that is not a link into this repo.
foreign() {
  local prof="$1" p target
  for p in "$prof"/skills/*; do
    [ -e "$p" ] || continue
    target="$(cd "$(dirname "$p")" && readlink "$(basename "$p")" 2>/dev/null || true)"
    case "$target" in "$REPO_ROOT"/skills/*) continue ;; esac
    basename "$p"
  done
}

echo "==> foreign skills (not owned by this repo)"
for pair in "$A:$B" "$B:$A"; do
  src="${pair%%:*}"; dst="${pair##*:}"
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    [ -e "$dst/skills/$name" ] && continue
    real="$(cd "$src/skills" && pwd -P)/$name"
    echo "  $(basename "$dst") <- $name"
    run ln -sfn "$real" "$dst/skills/$name"
    changed=$((changed + 1))
  done < <(foreign "$src")
done
[ "$changed" -eq 0 ] && echo "  already matched"

# --- 2. marketplaces --------------------------------------------------------
echo "==> marketplaces"
mkts() { "$PY" -c "
import json,sys
try: print('\n'.join(json.load(open(sys.argv[1]+'/plugins/known_marketplaces.json'))))
except Exception: pass
" "$1" 2>/dev/null; }

for pair in "$A:$B" "$B:$A"; do
  src="${pair%%:*}"; dst="${pair##*:}"
  have="$(mkts "$dst")"
  while IFS= read -r m; do
    [ -n "$m" ] || continue
    printf '%s\n' "$have" | grep -qxF "$m" && continue
    repo="$(awk -F'\t' -v n="$m" '$1==n && $2!="UNRESOLVED"{print $2; exit}' "$SOURCES" 2>/dev/null)"
    [ -n "$repo" ] || { echo "  SKIP $m (no repo in marketplace_sources.tsv)"; continue; }
    echo "  $(basename "$dst") <- $m ($repo)"
    run env CLAUDE_CONFIG_DIR="$dst" "$CB" plugin marketplace add "$repo"
    changed=$((changed + 1))
  done < <(mkts "$src")
done

# --- 3. plugins -------------------------------------------------------------
echo "==> plugins"
ids() { "$PY" -c "
import json,sys
try: print('\n'.join(json.load(open(sys.argv[1]+'/plugins/installed_plugins.json'))['plugins']))
except Exception: pass
" "$1" 2>/dev/null; }

for pair in "$A:$B" "$B:$A"; do
  src="${pair%%:*}"; dst="${pair##*:}"
  have="$(ids "$dst")"
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    is_blocked "$id" && continue
    printf '%s\n' "$have" | grep -qxF "$id" && continue
    echo "  $(basename "$dst") <- $id"
    run env CLAUDE_CONFIG_DIR="$dst" "$CB" plugin install "$id"
    changed=$((changed + 1))
  done < <(ids "$src")
done

# --- 4. enabled state -------------------------------------------------------
# A plugin can be installed in both but switched on in only one. Union wins:
# if it is enabled anywhere and not blocked, enable it in both.
echo "==> enabled state"
MISMATCH="$("$PY" - "$A" "$B" <<'EOF'
import json, sys
a, b = sys.argv[1], sys.argv[2]
def reg(p): return set(json.load(open(p+'/plugins/installed_plugins.json'))['plugins'])
def en(p):
    try: return json.load(open(p+'/settings.json')).get('enabledPlugins', {})
    except Exception: return {}
ra, rb, ea, eb = reg(a), reg(b), en(a), en(b)
for k in sorted(ra | rb):
    if bool(ea.get(k)) != bool(eb.get(k)):
        print(k)
EOF
)"

if [ -z "$MISMATCH" ]; then
  echo "  already matched"
else
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    is_blocked "$id" && continue
    echo "  enabling everywhere: $id"
    for d in "$A" "$B"; do
      run env CLAUDE_CONFIG_DIR="$d" "$CB" plugin enable "$id"
    done
    changed=$((changed + 1))
  done <<<"$MISMATCH"
fi

# --- report -----------------------------------------------------------------
echo
"$PY" - "$A" "$B" <<'EOF'
import json, os, sys
for p in sys.argv[1:]:
    reg = json.load(open(p+'/plugins/installed_plugins.json'))['plugins']
    en  = json.load(open(p+'/settings.json')).get('enabledPlugins', {})
    sk  = len(os.listdir(os.path.join(p, 'skills')))
    print(f"  {os.path.basename(p):18} {sk:4} skills  {len(reg):3} plugins  "
          f"{sum(1 for k in reg if en.get(k)):3} enabled")
EOF

echo
if [ "$DRY" = 1 ]; then
  echo "dry run — nothing changed ($changed drift item(s) found)"
else
  echo "profile parity done ($changed change(s))"
  if [ "$changed" -gt 0 ]; then
    echo "Restart Claude Code for changes to load."
  fi
fi

# Explicit. Without it the last command above is the exit status, so a clean
# run with 0 changes would exit 1 and the daily job would report a failure.
exit 0
