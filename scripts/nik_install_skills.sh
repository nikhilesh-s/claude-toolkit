#!/usr/bin/env bash
# Links every portable skill in this repo into Claude Code AND Codex, and removes
# stale repo-owned links that point at skills the repo no longer has.
#
# This machine has TWO Claude config directories:
#   ~/.claude          the plain `claude` CLI in a terminal
#   ~/.claude-nebula   the Claude Desktop app (it exports CLAUDE_CONFIG_DIR)
#
# Codex uses the Agent Skills open-standard user directory:
#   ~/.agents/skills
#
# Repo skills remain single-source-of-truth in ~/claude-toolkit/skills/. This
# script symlinks those same folders into both Claude profiles and Codex, so a
# skill update is immediately shared across all three surfaces after restart.
#
# It also exposes standalone skill folders installed directly in a Claude
# skills/ directory (for example parametric-3d-printing) to Codex when Codex
# does not already have a skill with the same name. Claude plugin-bundled skills
# under ~/.claude/plugins/cache are deliberately NOT mirrored here: they can be
# versioned/overwritten by the plugin and may depend on Claude-specific plugin
# tools or MCP servers.
#
# It is idempotent. Run it after every `git pull` from upstream — that is what
# makes new repo skills show up in Claude and Codex without manual linking.
#
#   ./scripts/nik_install_skills.sh            link everything, prune stale links
#   ./scripts/nik_install_skills.sh --dry-run  say what would change, change nothing
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
CODEX_ROOT="$HOME/.agents"
CODEX_SKILLS="$CODEX_ROOT/skills"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

CLAUDE_DIRS=()
for d in "$HOME/.claude" "$HOME/.claude-nebula" "${CLAUDE_CONFIG_DIR:-}"; do
  [ -n "$d" ] && [ -d "$d" ] || continue
  case " ${CLAUDE_DIRS[*]:-} " in *" $d "*) continue ;; esac
  CLAUDE_DIRS+=("$d")
done

# Codex's ~/.agents directory does not need to exist yet; this script creates it.
TARGET_ROOTS=("${CLAUDE_DIRS[@]}" "$CODEX_ROOT")

run() { if [ "$DRY_RUN" = 1 ]; then echo "  would: $*"; else "$@"; fi; }

total_added=0 total_pruned=0 total_kept=0 total_replaced=0 standalone_added=0

for ROOT in "${TARGET_ROOTS[@]}"; do
  DEST="$ROOT/skills"
  if [ "$ROOT" = "$CODEX_ROOT" ]; then
    echo "==> $DEST (Codex)"
  else
    echo "==> $DEST (Claude)"
  fi
  [ -d "$DEST" ] || run mkdir -p "$DEST"

  added=0 kept=0 pruned=0 replaced=0

  # 1. Link every repo skill folder into this target.
  for src in "$SKILLS_DIR"/*/; do
    name="$(basename "$src")"
    [ -e "$src/SKILL.md" ] || { echo "  skip $name (no SKILL.md)"; continue; }
    link="$DEST/$name"

    if [ -L "$link" ]; then
      current="$(readlink "$link")"
      if [ "$current" = "$SKILLS_DIR/$name" ]; then kept=$((kept + 1)); continue; fi
      run ln -sfn "$SKILLS_DIR/$name" "$link"; replaced=$((replaced + 1))
    elif [ -e "$link" ]; then
      # A real folder is shadowing the repo's copy. Move it OUT of skills/ first.
      # Anything left inside skills/ is loaded as another skill by that agent.
      backup="$ROOT/backups/skills-replaced/$name"
      echo "  real folder in the way: $name -> $backup"
      run mkdir -p "$(dirname "$backup")"
      run rm -rf "$backup"
      run mv "$link" "$backup"
      run ln -sfn "$SKILLS_DIR/$name" "$link"; replaced=$((replaced + 1))
    else
      run ln -sfn "$SKILLS_DIR/$name" "$link"; added=$((added + 1))
    fi
  done

  # 2. Prune only links that this script owns: links into this repo at skills that
  # no longer exist. Never prune unrelated user/third-party skills.
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
  total_kept=$((total_kept + kept)); total_replaced=$((total_replaced + replaced))
done

# 3. Mirror standalone (non-repo) Claude skills into Codex when there is no
# existing Codex skill with the same name. This catches skills installed directly
# into ~/.claude/skills or ~/.claude-nebula/skills without copying their files.
[ -d "$CODEX_SKILLS" ] || run mkdir -p "$CODEX_SKILLS"
for CDIR in "${CLAUDE_DIRS[@]}"; do
  [ -d "$CDIR/skills" ] || continue
  for src in "$CDIR/skills"/*; do
    [ -e "$src/SKILL.md" ] || continue
    name="$(basename "$src")"

    # Repo-owned skills were already handled above.
    resolved="$(cd "$src" 2>/dev/null && pwd -P || true)"
    case "$resolved" in "$SKILLS_DIR"/*) continue ;; esac

    dest="$CODEX_SKILLS/$name"
    [ -e "$dest" ] || [ -L "$dest" ] && continue

    # Resolve the source so Codex never points at an intermediate Claude symlink.
    [ -n "$resolved" ] || continue
    echo "  standalone -> Codex: $name"
    run ln -s "$resolved" "$dest"
    standalone_added=$((standalone_added + 1))
  done
done

echo
echo "Done. repo_added=$total_added repo_relinked=$total_replaced unchanged=$total_kept pruned=$total_pruned standalone_to_codex=$standalone_added"
[ "$DRY_RUN" = 1 ] && echo "(dry run — nothing was changed)"

broken=0
for ROOT in "${TARGET_ROOTS[@]}"; do
  DEST="$ROOT/skills"
  [ -d "$DEST" ] || continue
  while IFS= read -r l; do
    [ -e "$l" ] || { echo "BROKEN: $l -> $(readlink "$l")"; broken=$((broken + 1)); }
  done < <(find "$DEST" -maxdepth 1 -type l 2>/dev/null)
done
echo "broken links: $broken"

echo
echo "Restart Claude Code / Claude Desktop and start a fresh Codex session for skill changes to load."
