#!/bin/bash
# Health check for everything in this toolkit. Run: ~/claude-toolkit/status.sh
# Read-only — reports state, changes nothing.

bold=$(tput bold 2>/dev/null); dim=$(tput dim 2>/dev/null); off=$(tput sgr0 2>/dev/null)
ok="✅"; bad="❌"; warn="⚠️ "

echo
echo "${bold}SKILLS${off}  ${dim}(~/claude-toolkit/skills → ~/.claude/skills)${off}"
for d in "$HOME"/claude-toolkit/skills/*/; do
  s=$(basename "$d")
  link="$HOME/.claude/skills/$s"
  if [ ! -L "$link" ]; then
    printf "  %s %-14s not linked into ~/.claude/skills\n" "$bad" "$s"
  elif [ ! -r "$link/SKILL.md" ]; then
    printf "  %s %-14s symlink is broken\n" "$bad" "$s"
  else
    name=$(awk '/^name:/{print $2; exit}' "$link/SKILL.md")
    printf "  %s %-14s loads as %s@skills-dir\n" "$ok" "$s" "$name"
  fi
done

echo
echo "${bold}PLUGINS${off}"
claude plugin list 2>/dev/null | awk '
  /❯/   { name=$2 }
  /Status:/ { if ($0 ~ /enabled/) printf "  ✅ %s\n", name; else printf "  ❌ %s — %s\n", name, $0 }
'

echo
echo "${bold}SERVICES${off}  ${dim}(neither autostarts — restart them after a reboot)${off}"
code=$(curl -s -o /dev/null -m 3 -w "%{http_code}" http://127.0.0.1:37701 2>/dev/null)
if [ "$code" = "200" ]; then
  echo "  $ok claude-mem worker   :37701"
else
  echo "  $warn claude-mem worker   down  ${dim}→ npx claude-mem start${off}"
fi
code=$(curl -s -o /dev/null -m 3 -w "%{http_code}" http://localhost:20128/ 2>/dev/null)
if [ -n "$code" ] && [ "$code" != "000" ]; then
  echo "  $ok omniroute           :20128"
else
  echo "  $warn omniroute           down  ${dim}→ omniroute serve --daemon --no-open${off}"
fi

echo
echo "${bold}SERENA${off}"
flag=$(jq -r '.enabledPlugins["zeroize-audit@trailofbits"] | if . == null then "unset" else tostring end' "$HOME/.claude/settings.json" 2>/dev/null)
if [ "$flag" = "false" ]; then
  echo "  $warn deactivated (zeroize-audit plugin flag off) — flip to true in settings.json to restore"
elif pgrep -f "serena start-mcp-server" >/dev/null 2>&1; then
  echo "  $ok running"
else
  echo "  $ok enabled, not running (starts on demand)"
fi

echo
echo "${bold}MCP${off}"
if claude mcp list 2>/dev/null | grep -q "omniroute"; then
  echo "  $ok omniroute registered"
else
  echo "  $warn omniroute not registered — needs an account at http://localhost:20128/login first"
  echo "     ${dim}see the OmniRoute section of README.md${off}"
fi

echo
echo "${dim}Full details: ~/claude-toolkit/README.md${off}"
echo
