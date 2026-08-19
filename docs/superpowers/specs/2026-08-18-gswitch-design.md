# gswitch — multi-account Google connector for ChatGPT (design)

Date: 2026-08-18. Approved by Nik in chat.

## Problem

ChatGPT's built-in Google connector authenticates one Google account at a time.
Nik wants ChatGPT (used inside the Dia browser, one ChatGPT Plus account) to read
and write data from multiple Google accounts — personal (niksuravarjjala@gmail.com)
plus a college account added later — and switch between them with one click from a
Dock tile.

## Approach

Self-hosted MCP server on the Mac, added to ChatGPT as a Developer Mode custom
connector over a stable ngrok free static domain. The server holds OAuth tokens for
any number of Google accounts; a single "active account" file selects which one all
tools operate on. The Dock tile is a tiny AppleScript app that shows a picker of
known accounts and rewrites the active file. Tools read the active file at call
time, so a switch takes effect instantly with no reconnect in ChatGPT.

## Components

- `apps/gswitch/gswitch.py` — single Python file (PEP 723 inline deps, run via
  `uv run`). CLI subcommands:
  - `add` — Google OAuth flow in the browser; saves token to
    `~/.gswitch/accounts/<email>.json`; first account becomes active.
  - `list` / `use <email>` — inspect / set `~/.gswitch/active`.
  - `serve` — FastMCP server, streamable HTTP, `127.0.0.1:8765`, mounted at a
    secret random path `/mcp-<32 hex>` (generated once, stored in `~/.gswitch/secret`).
  - `up` — starts ngrok (`ngrok http --url=<domain> 8765`) as a subprocess plus the
    server; domain read from `~/.gswitch/ngrok_domain`.
  - `url` — prints the full connector URL for ChatGPT.
  - `selfcheck` — offline assertions on the account-store/active/secret logic.
- MCP tools (all operate on the active account, read+write):
  `active_account`, `drive_search`, `drive_read_file`, `drive_create_doc`,
  `drive_update_doc`, `gmail_search`, `gmail_read`, `gmail_send`, `gmail_draft`,
  `calendar_list_events`, `calendar_create_event`.
- OAuth scopes: `gmail.modify`, `drive`, `calendar`. Doc create/update goes through
  Drive upload-with-convert, so no Docs API scope needed.
- `GSwitch.applescript` → compiled with `osacompile` to `GSwitch.app` (build
  artifact, gitignored). Picker via `choose from list`, active account marked;
  selection rewrites `~/.gswitch/active` and posts a notification.
- `com.nik.gswitch.plist.template` + `install.sh` — installer builds the app,
  templates and loads a LaunchAgent that keeps `gswitch up` running, prints the
  manual-steps checklist.
- `EXTENSIONS.md` — provider model for non-Google services (doc only).

## Security posture (known ceiling)

ChatGPT custom connectors support only "no auth" or full OAuth server. We use
no-auth plus an unguessable secret path on a private ngrok domain. Upgrade path:
implement MCP OAuth on the server if this stops feeling safe. Tokens never leave
the Mac. Mac must be awake for the connector to work.

## Manual steps (Nik)

Google Cloud project + OAuth consent (External, both emails as test users) +
Desktop OAuth client → `~/.gswitch/client_secret.json`; ngrok account + authtoken +
free static domain; add connector in ChatGPT Settings → Connectors (Developer
Mode). College account may be blocked by university OAuth policy — probe early;
if blocked, no workaround exists.

## Out of scope

Docker, databases, multi-user, server-side OAuth, non-Google providers (documented
in EXTENSIONS.md only).
