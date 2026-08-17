#!/usr/bin/env bash
# Resolve a Claude Code marketplace NAME to the GitHub repo that publishes it.
#
# Why this exists: upstream's skill_index.tsv records a plugin as
# <name>@<marketplace>, but `claude plugin marketplace add` needs owner/repo.
# The marketplace name and the repo name are often different
# (brag -> latent-spaces/brag, humanizer -> blader/humanizer), so the mapping
# has to be discovered and then VERIFIED, never guessed.
#
# A candidate is accepted only if its .claude-plugin/marketplace.json actually
# declares `"name": "<marketplace>"`. That is the whole point — installing from
# a same-named repo that is not the real marketplace is how you end up running
# someone else's code.
#
#   ./scripts/nik_resolve_marketplaces.sh <name> [<name>...]
#   ./scripts/nik_resolve_marketplaces.sh --all      resolve every marketplace upstream lists
#
# Prints TSV:  <marketplace>\t<owner/repo or UNRESOLVED>
set -uo pipefail

# Real interpreter, not whatever is on PATH. modern-python@trailofbits shims
# `python3` to `uv run python`, which fails outside a uv project.
PY="$(command -v /opt/homebrew/bin/python3 2>/dev/null \
   || command -v /usr/bin/python3 2>/dev/null \
   || command -v python3)"


REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$REPO_ROOT/scripts/marketplace_sources.tsv"

# Known-good mappings. Anything already verified on this machine is pinned here
# so we never re-guess it, and so a future GitHub search cannot silently
# resolve a known marketplace to a different repo.
declare -a PINNED=(
  "claude-plugins-official	anthropics/claude-plugins-official"
  "thedotmack	thedotmack/claude-mem"
  "brag	latent-spaces/brag"
)

verify() {
  # verify <owner/repo> <expected-marketplace-name> -> 0 if it declares that name
  local repo="$1" want="$2" json
  json="$(gh api "repos/$repo/contents/.claude-plugin/marketplace.json" \
            --jq '.content' 2>/dev/null | base64 -d 2>/dev/null)" || return 1
  [ -n "$json" ] || return 1
  printf '%s' "$json" | "$PY" -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(1)
sys.exit(0 if d.get('name')=='$want' else 1)
" 2>/dev/null
}

resolve_one() {
  local name="$1" repo

  for row in "${PINNED[@]}"; do
    if [ "${row%%	*}" = "$name" ]; then
      printf '%s\t%s\n' "$name" "${row##*	}"
      return 0
    fi
  done

  if [ -f "$CACHE" ]; then
    repo="$(awk -F'\t' -v n="$name" '$1==n && $2!="UNRESOLVED"{print $2; exit}' "$CACHE")"
    if [ -n "$repo" ]; then
      printf '%s\t%s\n' "$name" "$repo"
      return 0
    fi
  fi

  # Search repos by name, then verify each candidate's manifest.
  while IFS= read -r cand; do
    [ -n "$cand" ] || continue
    if verify "$cand" "$name"; then
      printf '%s\t%s\n' "$name" "$cand"
      return 0
    fi
  done < <(gh api -X GET search/repositories \
             -f q="$name in:name" -f per_page=12 \
             --jq '.items[].full_name' 2>/dev/null)

  printf '%s\tUNRESOLVED\n' "$name"
  return 1
}

names=()
if [ "${1:-}" = "--all" ]; then
  git -C "$REPO_ROOT" fetch --quiet upstream main 2>/dev/null
  while IFS= read -r n; do names+=("$n"); done < <(
    git -C "$REPO_ROOT" show upstream/main:scripts/skill_index.tsv 2>/dev/null \
      | awk -F'\t' '$1=="plugin" && $3!=""{print $3}' | sort -u
  )
else
  names=("$@")
fi

[ ${#names[@]} -gt 0 ] || { echo "usage: $0 <marketplace>... | --all" >&2; exit 1; }

for n in "${names[@]}"; do
  resolve_one "$n"
done
