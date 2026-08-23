#!/usr/bin/env bash
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
MCP_NAME="media-unlocker"
MCP_URL="${MEDIAUNLOCK_MCP_URL:-http://127.0.0.1:8770/mcp}"

register_profile() {
  local config_dir="$1"
  echo "==> $config_dir"
  if CLAUDE_CONFIG_DIR="$config_dir" "$CLAUDE_BIN" mcp get "$MCP_NAME" >/dev/null 2>&1; then
    CLAUDE_CONFIG_DIR="$config_dir" "$CLAUDE_BIN" mcp remove --scope user "$MCP_NAME"
  fi
  CLAUDE_CONFIG_DIR="$config_dir" "$CLAUDE_BIN" mcp add \
    --scope user \
    --transport http \
    "$MCP_NAME" "$MCP_URL"
}

register_profile "${CLAUDE_CONFIG_DIR_DEFAULT:-$HOME/.claude}"
register_profile "${CLAUDE_CONFIG_DIR_NEBULA:-$HOME/.claude-nebula}"

echo
echo "Registered $MCP_NAME at $MCP_URL for both Claude profiles."
