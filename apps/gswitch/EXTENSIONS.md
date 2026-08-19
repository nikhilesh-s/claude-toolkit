# Extending gswitch beyond Google

gswitch is thin: a control script, a LaunchAgent, and a Dock app wrapped around
[taylorwilsdon/workspace-mcp][upstream] published over Tailscale Funnel. Only the
MCP server itself is Google-specific — the pattern generalizes to any service
with a remote MCP server.

## The reusable pattern

1. **Run an MCP server locally** that speaks streamable HTTP.
2. **Publish it with Tailscale Funnel** — `tailscale funnel --bg http://localhost:PORT`
   gives a permanent HTTPS URL for free, with no domain purchase and no tunnel
   process to babysit.
3. **Add it in ChatGPT** under Settings → Apps & Connectors → Advanced →
   Developer mode.
4. **One connector entry per identity.** This is the part worth copying. ChatGPT
   binds each connector entry to the account that completed its OAuth flow, so
   two entries pointing at the same URL give you two accounts simultaneously.
   Beats any in-server "active account" switch: no wrong-account writes, and both
   are usable in one conversation.

## Adding a second service alongside Google

Funnel can only serve one target per port path, so a second MCP server needs its
own port and its own funnel path:

```bash
tailscale funnel --bg --set-path=/notion http://localhost:8766
```

Then copy [`com.nik.gswitch.plist.template`](com.nik.gswitch.plist.template) to a
new label (`com.nik.notion`), point it at the other server, and add a second
connector entry in ChatGPT for `https://<host>/notion/mcp`. The Dock app's menu
is driven by the `gswitch` script, so extending it means adding a case there.

## Candidates worth the trouble

- **Microsoft 365** (Outlook, OneDrive) — closest analog to this setup, including
  the same risk that a university or employer tenant blocks third-party OAuth.
- **Notion, Linear, GitHub** — most have official remote MCP servers now, so you
  may not need to self-host at all; try adding their hosted URL as a connector
  directly before running anything locally.
- **IMAP** for non-Gmail mailboxes — credentials are just host, user, and an app
  password, so no OAuth dance.

## What does not work, regardless of provider

- **Consolidating accounts upstream.** For Google, all of these were tested and
  rejected: Gmail delegation is invisible to the API, POP/Gmailify import is
  being discontinued in January 2027, Drive shared-with-me search is unreliable
  through the native connector, and the Calendar connector ignores secondary
  calendars. Expect equivalent gaps elsewhere — verify before designing around
  sharing.
- **Enterprise-managed identities.** A tenant admin can block third-party OAuth
  outright, and that is enforced server-side. Always test the login before
  building.

[upstream]: https://github.com/taylorwilsdon/google_workspace_mcp
