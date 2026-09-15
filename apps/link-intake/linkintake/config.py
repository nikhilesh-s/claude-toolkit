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
        # auto = sync on every save when ~/.link-intake/google/{client,token}.json exist; off = never.
        "export_mode": "auto",
        "account": "",  # personal email recorded by google-auth
        # Exact Drive IDs chosen once by `linkintake google-setup`. Never discovered by name at save time.
        "targets": {
            "master_doc": "",
            "wishlist_doc": "",
            "wishlist_tab_id": "",
            "college_folder": "",
            "supplement_doc": "",
            "media_folder": "",
            "design_doc": "",
            "personal_ig_doc": "",
            "scholarships_folder": "",
            "scholarship_sheet": "",
        },
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
