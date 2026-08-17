#!/bin/bash
# Finds the skills/plugins whose name or description best match a query,
# from scripts/skill_index.tsv. One cheap grep instead of reasoning over the
# full catalog. Usage: ./which-skill.sh <word> [word...]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
INDEX="$HERE/skill_index.tsv"

if [ ! -f "$INDEX" ]; then
  echo "No index yet. Run: uv run python $HERE/build_skill_index.py > $INDEX" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <word> [word...]" >&2
  exit 1
fi

# Build one case-insensitive grep pattern per word, require every word to
# match somewhere in the line (name, source, or description).
PATTERN_ARGS=()
for word in "$@"; do
  PATTERN_ARGS+=(-e "$word")
done

# Score by number of matched query words, most matches first, name column only
# gets extra weight since a name hit is a stronger signal than a description hit.
awk -F'\t' -v words="$*" '
BEGIN {
  n = split(tolower(words), w, " ")
}
{
  line = tolower($0)
  name = tolower($2)
  score = 0
  for (i = 1; i <= n; i++) {
    if (index(name, w[i]) > 0) score += 3
    else if (index(line, w[i]) > 0) score += 1
  }
  if (score > 0) print score "\t" $0
}
' "$INDEX" | sort -t$'\t' -k1,1rn | cut -f2- | head -10 | \
  awk -F'\t' '{printf "%-8s %-40s %-28s %s\n", $1, $2, $3, $4}'
