"""Config lives in ~/.link-intake/config.json. Nothing secret goes here except a creds *path*."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

STATE_DIR = Path(os.environ.get("LINKINTAKE_STATE_DIR", Path.home() / ".link-intake"))
CONFIG_PATH = STATE_DIR / "config.json"

DEFAULTS: dict = {
    "google": {
        # off  = save locally, mark export_pending (Claude exports later through its Drive connector).
        # rest = optional fallback: write via the stdlib REST client using creds_path.
        "export_mode": "off",
        # OAuth token JSON (client_id, client_secret, refresh_token, token_uri). Only used when
        # export_mode = rest. Empty = ~/.link-intake/google-creds.json if it exists.
        "creds_path": "",
        # Drive folder that new intake docs are created in. Empty = My Drive root.
        "folder_id": "",
        "docs": {
            "intake_master": "",
            "supplement_ideas": "",
            "design_inspo": "",
            "personal_ig": "",
            "inbox": "",
            # Existing College/Dorm Wishlist doc (see skills/college-wishlist-media). Not restructured.
            "wishlist": "17W59ZIgOeFVw3Wk-I1n8Jfjd_kcJ77GFqR9-tn3gW5Q",
        },
        "wishlist_tab_id": "t.8rdi8wnl84he",  # Media Queue tab = staging section
        "sheets": {"scholarships": ""},
    },
    "media_unlocker": {
        "mcp_url": "http://127.0.0.1:8770/mcp",
        "jobs_dir": "~/.media-unlocker/jobs",
        # Verified Instagram cookie source on this Mac (skills/media-unlocker/SKILL.md).
        "browser": "chromium:~/Library/Application Support/Dia/User Data/Profile 5",
    },
    "llm": {
        # auto | anthropic | claude | none
        "backend": "auto",
        "model": "claude-opus-5",
        "claude_cli": "/opt/homebrew/bin/claude",
        "claude_config_dir": "~/.claude-nebula",  # the Claude Max login on this Mac
    },
    "cleanup": {"enabled": True},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load() -> dict:
    try:
        return _merge(DEFAULTS, json.loads(CONFIG_PATH.read_text()))
    except FileNotFoundError:
        return copy.deepcopy(DEFAULTS)


def save(cfg: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def set_path(cfg: dict, dotted: str, value) -> dict:
    node = cfg
    *parents, leaf = dotted.split(".")
    for p in parents:
        node = node.setdefault(p, {})
    node[leaf] = value
    return cfg


def expand(p: str) -> Path:
    return Path(os.path.expanduser(p))
