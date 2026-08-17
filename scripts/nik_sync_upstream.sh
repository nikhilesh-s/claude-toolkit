#!/usr/bin/env bash
# Pull Arnav's new skills into this branch WITHOUT losing Nik's README.
#
# What it does, in order:
#   1. refuses to run if the working tree is dirty
#   2. fetches upstream (ArnavKakani/claude-toolkit) main
#   3. shows exactly which skills upstream added, changed, or removed
#   4. merges upstream/main into this branch
#      - README.md is protected by a `merge=ours` driver (see .gitattributes),
#        so upstream's README never overwrites this one
#   5. updates the gstack / task-observer submodules
#   6. rewrites any absolute symlinks upstream committed (it hardcodes
#      /Users/arnavkakani/... paths, which are dead on this machine)
#   7. relinks every skill into every Claude config dir
#   8. regenerates the README inventory block
#
# Usage:
#   ./scripts/nik_sync_upstream.sh              merge, relink, regenerate
#   ./scripts/nik_sync_upstream.sh --preview    show what upstream changed, merge nothing
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

UPSTREAM_REMOTE="upstream"
UPSTREAM_BRANCH="main"
PREVIEW=0
[ "${1:-}" = "--preview" ] && PREVIEW=1

info() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --- 0. sanity ---------------------------------------------------------------
if ! git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1; then
  echo "No '$UPSTREAM_REMOTE' remote. Add it with:" >&2
  echo "  git remote add $UPSTREAM_REMOTE https://github.com/ArnavKakani/claude-toolkit.git" >&2
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" = "$UPSTREAM_BRANCH" ]; then
  echo "You are on '$UPSTREAM_BRANCH'. Switch to your own branch first:" >&2
  echo "  git checkout nik-claude-toolkit" >&2
  exit 1
fi

if [ "$PREVIEW" = 0 ] && [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is dirty. Commit or stash first, then re-run." >&2
  git status --short >&2
  exit 1
fi

# The merge=ours driver has to exist locally; .gitattributes alone does nothing.
# This is per-clone config, not tracked in the repo, so make sure it is set.
if [ "$(git config --get merge.ours.driver || true)" != "true" ]; then
  info "Registering the 'ours' merge driver (protects README.md)"
  git config merge.ours.driver true
fi

# --- 1. fetch ----------------------------------------------------------------
info "Fetching $UPSTREAM_REMOTE/$UPSTREAM_BRANCH"
git fetch "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH"

BASE="$(git merge-base HEAD "$UPSTREAM_REMOTE/$UPSTREAM_BRANCH")"
HEAD_UP="$(git rev-parse "$UPSTREAM_REMOTE/$UPSTREAM_BRANCH")"

if [ "$BASE" = "$HEAD_UP" ]; then
  info "Already up to date with upstream. Nothing to merge."
  [ "$PREVIEW" = 1 ] && exit 0
else
  # --- 2. what changed -------------------------------------------------------
  info "Upstream commits not yet in $BRANCH"
  git log --oneline --no-merges "$BASE..$HEAD_UP" | sed 's/^/  /'

  info "Skill folders upstream added"
  git diff --name-status --diff-filter=A "$BASE" "$HEAD_UP" -- skills/ \
    | awk -F/ '{print $2}' | sort -u | sed 's/^/  + /' || true

  info "Skill folders upstream removed"
  git diff --name-status --diff-filter=D "$BASE" "$HEAD_UP" -- skills/ \
    | awk -F/ '{print $2}' | sort -u | sed 's/^/  - /' || true

  info "Other files upstream touched"
  git diff --name-only "$BASE" "$HEAD_UP" -- . ':(exclude)skills/' | sed 's/^/  ~ /' || true

  if [ "$PREVIEW" = 1 ]; then
    info "Preview only — nothing was merged."
    exit 0
  fi

  # --- 3. merge --------------------------------------------------------------
  info "Merging $UPSTREAM_REMOTE/$UPSTREAM_BRANCH into $BRANCH"
  if ! git merge --no-edit "$UPSTREAM_REMOTE/$UPSTREAM_BRANCH"; then
    echo >&2
    echo "Merge stopped on a conflict. README.md should NOT be among them." >&2
    echo "Resolve, 'git add' the files, then run 'git commit' and re-run this script." >&2
    git diff --name-only --diff-filter=U >&2
    exit 1
  fi
fi

# --- 4. submodules -----------------------------------------------------------
info "Updating submodules (gstack, task-observer)"
git submodule update --init --recursive

# --- 5. de-hardcode upstream's absolute symlinks -----------------------------
info "Rewriting absolute symlinks that point at /Users/arnavkakani"
python3 - <<'PY'
import os, pathlib
root = pathlib.Path(__file__).resolve().parent if False else pathlib.Path(os.getcwd())
PREFIX = '/Users/arnavkakani/claude-toolkit/'
fixed = []
for p in root.rglob('*'):
    if '.git' in p.parts or not p.is_symlink():
        continue
    tgt = os.readlink(p)
    if not tgt.startswith(PREFIX):
        continue
    rel = os.path.relpath(root / tgt[len(PREFIX):], p.parent)
    p.unlink(); p.symlink_to(rel)
    fixed.append(str(p.relative_to(root)))
print(f"  rewrote {len(fixed)} symlink(s)")
for f in fixed[:20]:
    print("   ", f)
PY

broken="$(find skills -type l ! -exec test -e {} \; -print 2>/dev/null | wc -l | tr -d ' ')"
echo "  broken symlinks remaining: $broken"

# --- 6. relink + regenerate --------------------------------------------------
info "Linking skills into every Claude config dir"
./scripts/nik_install_skills.sh

info "Regenerating the README inventory"
python3 scripts/nik_inventory.py

info "Done"
git status --short
echo
echo "Review the changes, then commit:"
echo "  git add -A && git commit -m 'sync upstream + regenerate inventory'"
echo
echo "Restart Claude Code so the new skills load."
