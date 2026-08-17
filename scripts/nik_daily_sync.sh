#!/usr/bin/env bash
# Unattended daily sync. Driven by launchd — see
# ~/Library/LaunchAgents/com.nik.claude-toolkit-sync.plist
#
# This is the safe wrapper around nik_sync_upstream.sh. Run by hand any time:
#   ./scripts/nik_daily_sync.sh            normal run
#   ./scripts/nik_daily_sync.sh --dry-run  report only, change nothing
#
# It is deliberately timid. Unattended git that fights you is worse than no
# unattended git at all, so it does nothing at all when anything looks off:
#   - another copy already running        -> exit
#   - uncommitted work in the tree        -> exit, touch nothing
#   - not on the nik branch               -> exit
#   - merge hits a conflict               -> abort the merge, restore, shout
#   - push fails                          -> keep the local commit, shout
#
# A NOTE ON WHAT THIS CANNOT DO:
# Arnav records plugins as prose in his README, not as files in the repo. Git can
# only deliver skills/. So new PLUGINS (humanizer@humanizer, brag@brag, ...) never
# arrive through a pull. This script detects them in the README diff and tells you
# to run `claude plugin install` yourself. It will not install them on its own —
# that runs third-party code, which is your call, not a cron job's.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

BRANCH="nik-claude-toolkit"
LOG_DIR="$HOME/Library/Logs/claude-toolkit"
LOG="$LOG_DIR/sync.log"
STATUS_FILE="$LOG_DIR/last-run.txt"
LOCK="$LOG_DIR/sync.lock"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

mkdir -p "$LOG_DIR"

# --- --report-plugins: every plugin upstream lists that is not installed here.
# Runs on its own, touches nothing, needs no lock.
if [ "${1:-}" = "--report-plugins" ]; then
  git fetch --quiet upstream main 2>/dev/null
  installed="$(python3 -c "
import json,os
p=os.path.expanduser('~/.claude/plugins/installed_plugins.json')
try: print('\n'.join(json.load(open(p)).get('plugins',{}).keys()))
except Exception: pass
" 2>/dev/null)"
  echo "Plugins Arnav lists that are NOT installed on this machine."
  echo "Git cannot deliver these — a plugin is not a file in the repo."
  echo "Install one with:  claude plugin install <id>"
  echo
  git show upstream/main:scripts/skill_index.tsv 2>/dev/null \
    | awk -F'\t' '$1=="plugin" && NF>=4 {print $2"@"$3"\t"$4}' | sort -u \
    | while IFS=$'\t' read -r id desc; do
        printf '%s\n' "$installed" | grep -qxF "$id" && continue
        printf '  %-42s %s\n' "$id" "$(printf '%.90s' "$desc")"
      done
  exit 0
fi

# Keep the log from growing without bound.
if [ -f "$LOG" ] && [ "$(wc -c <"$LOG" 2>/dev/null || echo 0)" -gt 1000000 ]; then
  mv -f "$LOG" "$LOG.1"
fi

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { printf '%s  %s\n' "$(ts)" "$*" >>"$LOG"; }
say() { log "$*"; [ -t 1 ] && echo "$*"; }

notify() {
  # Best effort. Never let a missing osascript fail the run.
  local title="$1" msg="$2"
  osascript -e "display notification \"${msg//\"/\'}\" with title \"${title//\"/\'}\"" \
    >/dev/null 2>&1 || true
}

finish() {
  local state="$1" detail="$2"
  printf '%s\n%s\n%s\n' "$(ts)" "$state" "$detail" >"$STATUS_FILE"
  log "RESULT: $state — $detail"
  log "----"
  exit "${3:-0}"
}

# --- single instance --------------------------------------------------------
if ! mkdir "$LOCK" 2>/dev/null; then
  # Stale lock from a killed run? Anything older than 2h is stale.
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null || rm -rf "$LOCK"
    mkdir "$LOCK" 2>/dev/null || { log "could not take lock"; exit 0; }
  else
    log "another sync is already running — skipping"
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null || rm -rf "$LOCK"' EXIT

log "=== daily sync start (dry_run=$DRY_RUN) ==="

# --- preconditions ----------------------------------------------------------
CURRENT="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
[ "$CURRENT" = "$BRANCH" ] || finish "SKIPPED" "on branch '$CURRENT', not '$BRANCH'" 0

if [ -n "$(git status --porcelain)" ]; then
  finish "SKIPPED" "working tree has uncommitted changes — left untouched" 0
fi

# --- fetch ------------------------------------------------------------------
if ! git fetch --quiet upstream main 2>>"$LOG"; then
  notify "Claude toolkit sync failed" "Could not fetch from Arnav's repo. See sync.log."
  finish "FETCH FAILED" "git fetch upstream main failed (network or auth)" 1
fi

BEFORE="$(git rev-parse HEAD)"
BASE="$(git merge-base HEAD upstream/main)"
UP="$(git rev-parse upstream/main)"

if [ "$BASE" = "$UP" ]; then
  finish "UP TO DATE" "no new upstream commits" 0
fi

# --- what is coming ---------------------------------------------------------
NEW_COMMITS="$(git log --oneline --no-merges "$BASE..$UP" 2>/dev/null)"
ADDED_SKILLS="$(git diff --name-status --diff-filter=A "$BASE" "$UP" -- skills/ \
  | awk -F/ '{print $2}' | sort -u | grep -v '^$' || true)"
REMOVED_SKILLS="$(git diff --name-status --diff-filter=D "$BASE" "$UP" -- skills/ \
  | awk -F/ '{print $2}' | sort -u | grep -v '^$' || true)"

log "upstream commits:"
printf '%s\n' "$NEW_COMMITS" | sed 's/^/    /' >>"$LOG"
[ -n "$ADDED_SKILLS" ]   && { log "skills added:";   printf '%s\n' "$ADDED_SKILLS"   | sed 's/^/    + /' >>"$LOG"; }
[ -n "$REMOVED_SKILLS" ] && { log "skills removed:"; printf '%s\n' "$REMOVED_SKILLS" | sed 's/^/    - /' >>"$LOG"; }

# --- plugins upstream added that are not installed here ---------------------
# Upstream keeps a machine-readable catalogue at scripts/skill_index.tsv:
#     <kind>\t<name>\t<source>\t<description>
# Plugin rows give the install id directly as <name>@<source>. Diffing that file
# is far more reliable than scraping prose out of the README.
installed_plugin_ids() {
  python3 -c "
import json,os
p=os.path.expanduser('~/.claude/plugins/installed_plugins.json')
try: print('\n'.join(json.load(open(p)).get('plugins',{}).keys()))
except Exception: pass
" 2>/dev/null
}

PLUGIN_HITS="$(git diff "$BASE" "$UP" -- scripts/skill_index.tsv 2>/dev/null \
  | grep '^+plugin' | sed 's/^+//' \
  | awk -F'\t' 'NF>=3 && $2!="" && $3!="" {print $2"@"$3}' \
  | sort -u || true)"

MISSING_PLUGINS=""
if [ -n "$PLUGIN_HITS" ]; then
  INSTALLED="$(installed_plugin_ids)"
  while IFS= read -r cand; do
    [ -n "$cand" ] || continue
    printf '%s\n' "$INSTALLED" | grep -qxF "$cand" || MISSING_PLUGINS="$MISSING_PLUGINS$cand"$'\n'
  done <<<"$PLUGIN_HITS"
fi

if [ "$DRY_RUN" = 1 ]; then
  say "DRY RUN — would merge $(printf '%s\n' "$NEW_COMMITS" | grep -c . ) commit(s)"
  [ -n "$ADDED_SKILLS" ] && say "would add skills: $(echo $ADDED_SKILLS)"
  [ -n "$MISSING_PLUGINS" ] && say "plugins to install by hand: $(echo $MISSING_PLUGINS)"
  finish "DRY RUN" "nothing changed" 0
fi

# --- merge ------------------------------------------------------------------
git config merge.ours.driver true

if ! git merge --no-edit upstream/main >>"$LOG" 2>&1; then
  log "merge conflict — aborting and restoring $BEFORE"
  git merge --abort >>"$LOG" 2>&1 || git reset --hard "$BEFORE" >>"$LOG" 2>&1
  notify "Claude toolkit sync needs you" "Upstream merge conflicted. Repo restored. Run the sync by hand."
  finish "CONFLICT" "merge aborted, repo restored to $BEFORE — resolve by hand with ./scripts/nik_sync_upstream.sh" 1
fi

# --- post-merge repair ------------------------------------------------------
git submodule update --init --recursive >>"$LOG" 2>&1

python3 - >>"$LOG" 2>&1 <<'PY'
import os, pathlib
root = pathlib.Path(os.getcwd())
PREFIX = '/Users/arnavkakani/claude-toolkit/'
n = 0
for p in root.rglob('*'):
    if '.git' in p.parts or not p.is_symlink():
        continue
    t = os.readlink(p)
    if t.startswith(PREFIX):
        rel = os.path.relpath(root / t[len(PREFIX):], p.parent)
        p.unlink(); p.symlink_to(rel); n += 1
print(f"rewrote {n} absolute symlink(s)")
PY

./scripts/nik_install_skills.sh >>"$LOG" 2>&1

# --- plugins ----------------------------------------------------------------
# Nik asked for full parity with Arnav, kept automatic. Git cannot carry a
# plugin, so this runs the real installer: it resolves each marketplace to a
# verified GitHub repo and installs into BOTH profiles.
#
# This downloads and enables third-party code without review. That is the
# explicit intent here. To go back to review-first, set AUTO_INSTALL_PLUGINS=0
# below — the run will then only report what is missing.
AUTO_INSTALL_PLUGINS=1

PLUGIN_NOTE=""
if [ "$AUTO_INSTALL_PLUGINS" = 1 ] && [ -n "$MISSING_PLUGINS" ]; then
  log "auto-installing plugins Arnav added:"
  printf '%s' "$MISSING_PLUGINS" | sed 's/^/    /' >>"$LOG"
  if ./scripts/nik_install_plugins.sh >>"$LOG" 2>&1; then
    PLUGIN_NOTE=", installed $(printf '%s' "$MISSING_PLUGINS" | grep -c .) plugin(s)"
    log "plugin install finished"
  else
    PLUGIN_NOTE=", plugin install FAILED (see log)"
    log "plugin install failed"
    notify "Claude toolkit" "A plugin install failed. See sync.log."
  fi
fi

python3 scripts/nik_inventory.py >>"$LOG" 2>&1

BROKEN="$(find skills -type l ! -exec test -e {} \; -print 2>/dev/null | wc -l | tr -d ' ')"
log "broken symlinks after repair: $BROKEN"

# --- commit + push ----------------------------------------------------------
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -q -m "daily sync: upstream/main + regenerate inventory

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" >>"$LOG" 2>&1
fi

PUSH_NOTE=""
if ! git push --quiet origin "$BRANCH" >>"$LOG" 2>&1; then
  PUSH_NOTE=" (push to origin FAILED — commit is local only)"
  log "push failed"
  notify "Claude toolkit sync" "Merged locally but the push failed. See sync.log."
fi

# --- report -----------------------------------------------------------------
N_ADDED="$(printf '%s\n' "$ADDED_SKILLS" | grep -c . || true)"
N_REMOVED="$(printf '%s\n' "$REMOVED_SKILLS" | grep -c . || true)"
SUMMARY="added $N_ADDED skill(s), removed $N_REMOVED"

if [ -n "$MISSING_PLUGINS" ] && [ "$AUTO_INSTALL_PLUGINS" = 1 ]; then
  notify "Claude toolkit updated" \
    "$N_ADDED skill(s) + $(printf '%s' "$MISSING_PLUGINS" | grep -c .) plugin(s) from Arnav. Restart Claude Code."
elif [ -n "$MISSING_PLUGINS" ]; then
  log "PLUGINS NEEDING MANUAL INSTALL (git cannot deliver these):"
  printf '%s' "$MISSING_PLUGINS" | sed 's/^/    /' >>"$LOG"
  notify "Claude toolkit: new plugin to install" \
    "Arnav added: $(printf '%s' "$MISSING_PLUGINS" | tr '\n' ' '). Run nik_install_plugins.sh."
elif [ "$N_ADDED" -gt 0 ]; then
  notify "Claude toolkit updated" "$N_ADDED new skill(s) from Arnav. Restart Claude Code."
fi

finish "SYNCED" "$SUMMARY$PLUGIN_NOTE$PUSH_NOTE" 0
