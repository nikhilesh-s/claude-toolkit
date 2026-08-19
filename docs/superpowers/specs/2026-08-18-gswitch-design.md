# gswitch — second Google account for ChatGPT (design)

Date: 2026-08-18. Revised after research; original custom-server design superseded.

## Problem

ChatGPT allows one native Google connection per account. Nik (ChatGPT Plus, uses
ChatGPT in the Dia browser) wants read+write access to both his personal Google
account and a college `.edu` account.

## What the research changed

The first design (custom FastMCP server + active-account file + ngrok + Dock
switcher) was rewritten after checking current facts:

- ChatGPT's **native** Google connector gained write actions in June 2026 (Gmail
  send Jun 5, Drive write Jun 15, Calendar event creation). The personal account
  therefore needs no custom work at all.
- Multi-account is still unsupported natively and unacknowledged by OpenAI
  (feature request opened 2026-08-14, no staff reply).
- Every Google-side consolidation trick fails: Gmail delegation is invisible to
  the API, POP/Gmailify import is discontinued Jan 2027, Drive shared-with-me
  search through the connector is unreliable, and the Calendar connector has an
  open bug ignoring secondary calendars.
- `taylorwilsdon/workspace-mcp` (actively maintained, 3k stars, official ChatGPT
  Developer Mode guide) already does everything the custom server did and more,
  so the custom server was deleted.
- **A ChatGPT connector entry binds to the Google account that completed its
  OAuth flow.** Registering the connector twice gives both accounts in one
  conversation. This removes the need for account switching entirely — the
  original design's central mechanism was solving a non-problem.
- An OAuth client left in *Testing* publishing status expires refresh tokens
  every 7 days. The app must be published (unverified is fine).
- ngrok free is 1 GB/month with an interstitial; Tailscale Funnel is free with a
  stable hostname and no domain purchase.

## Design

- **Personal account**: ChatGPT's native Google connector. No code.
- **College account**: `uvx workspace-mcp --transport streamable-http --tool-tier
  core --tools gmail drive calendar docs` (19 tools) on port **8765** (8000 is
  occupied by another local service), under a launchd KeepAlive agent, with
  `MCP_ENABLE_OAUTH21=true` and `WORKSPACE_EXTERNAL_URL` /
  `GOOGLE_OAUTH_REDIRECT_URI` pointed at the Tailscale Funnel hostname.
- **Exposure**: `tailscale funnel --bg http://localhost:8765`, a persistent
  config rather than a managed process.
- **`gswitch`** (bash): `doctor`, `config`, `funnel`, `install`, `start`, `stop`,
  `restart`, `status`, `url`, `logs`. Health check matches the `workspace-mcp`
  service name so a foreign app on the port cannot be mistaken for it.
- **`GSwitch.app`**: Dock control panel (start/stop/restart, copy connector URL,
  setup check, open log) — kept at Nik's request, repurposed from switcher to
  control panel.
- Secrets: client secret in `~/.gswitch/config` (600), tokens in
  `~/.gswitch/creds/`.

## Verified

Server boots via `uvx`, `/health` returns `workspace-mcp` v1.25.0, 19 tools
listed over streamable HTTP including `send_gmail_message`, `create_doc`,
`create_drive_file`, `modify_doc_text`. `gswitch status`/`doctor` report
correctly in both up and down states, and degrade cleanly with Tailscale absent.

## Open risk

The college Google Workspace tenant may block unverified third-party OAuth apps;
this is enforced Google-side and unavoidable. Must be tested before relying on
it. Fallback: a second ChatGPT account signed in with the college Google login.

## Out of scope

Non-Google providers (documented in EXTENSIONS.md), always-on hosting, phone
access while the Mac sleeps.
