#!/usr/bin/env bash
# Links every skill in this repo into every Claude Code config directory on this
# machine, and removes stale links that point at skills the repo no longer has.
#
# This machine has TWO config directories:
#   ~/.claude          the plain `claude` CLI in a terminal
#   ~/.claude-nebula   the Claude Desktop app (it exports CLAUDE_CONFIG_DIR)
# They share ~/.claude/plugins, but each keeps its OWN skills/ folder. A skill
# linked into only one of them is invisible in the other, so this script does both.
#
# It is idempotent. Run it after every `git pull` from upstream — that is what
# makes Arnav's new skills show up here without any manual linking.
#
#   ./scripts/nik_install_skills.sh            link everything, prune stale links
#   ./scripts/nik_install_skills.sh --dry-run  say what would change, change nothing
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

CONFIG_DIRS=()
for d in "$HOME/.claude" "$HOME/.claude-nebula" "${CLAUDE_CONFIG_DIR:-}"; do
  [ -n "$d" ] && [ -d "$d" ] || continue
  case " ${CONFIG_DIRS[*]:-} " in *" $d "*) continue ;; esac
  CONFIG_DIRS+=("$d")
done

if [ ${#CONFIG_DIRS[@]} -eq 0 ]; then
  echo "No Claude config directory found (looked for ~/.claude, ~/.claude-nebula)." >&2
  exit 1
fi

run() { if [ "$DRY_RUN" = 1 ]; then echo "  would: $*"; else "$@"; fi; }

total_added=0 total_pruned=0 total_kept=0

for CDIR in "${CONFIG_DIRS[@]}"; do
  DEST="$CDIR/skills"
  echo "==> $DEST"
  [ -d "$DEST" ] || run mkdir -p "$DEST"

  added=0 kept=0 pruned=0 replaced=0

  # 1. link every skill folder the repo ships
  for src in "$SKILLS_DIR"/*/; do
    name="$(basename "$src")"
    [ -e "$src/SKILL.md" ] || { echo "  skip $name (no SKILL.md)"; continue; }
    link="$DEST/$name"

    if [ -L "$link" ]; then
      current="$(readlink "$link")"
      if [ "$current" = "$SKILLS_DIR/$name" ]; then kept=$((kept + 1)); continue; fi
      run ln -sfn "$SKILLS_DIR/$name" "$link"; replaced=$((replaced + 1))
    elif [ -e "$link" ]; then
      # A real folder is shadowing the repo's copy. Move it OUT of skills/ first —
      # anything left inside skills/ is loaded by Claude Code as another skill.
      backup="$CDIR/backups/skills-replaced/$name"
      echo "  real folder in the way: $name -> $backup"
      run mkdir -p "$(dirname "$backup")"
      run rm -rf "$backup"
      run mv "$link" "$backup"
      run ln -sfn "$SKILLS_DIR/$name" "$link"; replaced=$((replaced + 1))
    else
      run ln -sfn "$SKILLS_DIR/$name" "$link"; added=$((added + 1))
    fi
  done

  # 2. prune links that point into this repo at a skill that no longer exists
  for link in "$DEST"/*; do
    [ -L "$link" ] || continue
    target="$(readlink "$link")"
    case "$target" in
      "$SKILLS_DIR"/*)
        [ -e "$link" ] && continue
        echo "  stale: $(basename "$link") (upstream removed it)"
        run rm -f "$link"; pruned=$((pruned + 1))
        ;;
    esac
  done

  echo "    added=$added relinked=$replaced unchanged=$kept pruned=$pruned"
  total_added=$((total_added + added)); total_pruned=$((total_pruned + pruned))
  total_kept=$((total_kept + kept))
done

echo
echo "Done. added=$total_added unchanged=$total_kept pruned=$total_pruned"
[ "$DRY_RUN" = 1 ] && echo "(dry run — nothing was changed)"

broken=0
for CDIR in "${CONFIG_DIRS[@]}"; do
  while IFS= read -r l; do
    [ -e "$l" ] || { echo "BROKEN: $l -> $(readlink "$l")"; broken=$((broken + 1)); }
  done < <(find "$CDIR/skills" -maxdepth 1 -type l 2>/dev/null)
done
echo "broken links: $broken"

echo
echo "Restart Claude Code for skill changes to load."
