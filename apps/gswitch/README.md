# gswitch

Gives ChatGPT read **and write** access to a second Google account (your college
`.edu`) alongside your personal one, in the same conversation. Works with ChatGPT
in any browser, including Dia.

## How it works, and why there's no "switching"

ChatGPT allows one native Google connection per account, so your personal Gmail /
Drive / Calendar is already covered by ChatGPT's built-in Google app — including
sending mail and creating files, which it gained in June 2026. That side needs no
work.

For the second account, gswitch runs [taylorwilsdon/workspace-mcp][upstream]
locally and publishes it over Tailscale Funnel, so ChatGPT can add it as a
Developer Mode custom connector.

The important detail: **each ChatGPT connector entry binds to whichever Google
account completed its OAuth flow.** Add the connector twice, sign in as a
different Google account each time, and ChatGPT talks to both accounts at once —
no switching, no active-account toggle. The Dock tile is therefore a control
panel (start/stop/status/URL), not a switcher.

`GSwitch.app` in the Dock shows connector state and offers: start, stop, restart,
copy connector URL, run the setup check, open the log.

Tools exposed: **45** (the `extended` tier), covering Gmail
(search/read/send/draft/labels/filters), Drive
(search/read/create/update/folders/permissions), Calendar (list/create/update/
delete events), and Docs — including reading and writing **comments**
(`list_document_comments`, `manage_document_comment`), **formatting and
highlights** (`modify_doc_text` takes bold, italic, text colour and background
colour; `update_paragraph_style` handles headings), find-and-replace, and
markdown export. The `core` tier was rejected because it drops comments and
paragraph styling entirely. Adjust `SERVICES` and `TIER` in [`gswitch`](gswitch)
to add Sheets, Slides, Tasks, Contacts, or Chat, or to go to `complete` (57
tools, adds images, headers/footers, tables, and raw batch updates).

## Setup

### 1. Local install

```bash
cd ~/claude-toolkit/apps/gswitch && ./setup.sh
```

Builds `GSwitch.app` (drag it to your Dock), installs the `gswitch` CLI, and
prints a checklist of what's still missing. Re-run `gswitch doctor` any time.

### 2. Tailscale

```bash
brew install --cask tailscale
```

Open Tailscale, sign in (any method), and let it connect. Then:

```bash
gswitch funnel
```

This publishes the local port on a permanent `https://<machine>.<tailnet>.ts.net`
address. Free, no domain purchase, and the URL survives reboots.

**Enable HTTPS certificates first**, at
https://login.tailscale.com/admin/dns under *HTTPS Certificates*. Without it
`tailscale funnel` hangs silently instead of erroring: it retries in the
background and only completes once HTTPS is on. If the command appears to do
nothing, that is why. Confirm with `tailscale funnel status`.

### 3. Google Cloud OAuth client

Do this **once, under your personal account only** — a Google Cloud project is
just an app registration, not a data connection. Any Google account can later
sign in *through* it. There is no college Cloud project, and your existing
personal ChatGPT connectors are untouched.

Signed in as **niksuravarjjala@gmail.com** at https://console.cloud.google.com,
in the `gswitch` project:

1. **APIs & Services → Library**: enable **Gmail API**, **Google Drive API**,
   **Google Calendar API**, **Google Docs API**.
2. **APIs & Services → OAuth consent screen** (a.k.a. Google Auth Platform):
   App name `gswitch`, your email for support and contact, audience **External**.
3. **Audience → Test users**: add both your personal and college addresses.
4. **IMPORTANT — Audience → Publishing status → Publish app.** Confirm the
   unverified-app warning. Leaving the app in *Testing* expires refresh tokens
   after **7 days**, which means re-authorizing every week forever. Published +
   unverified has no expiry and is correct for a two-person setup; you'll just
   click through an "unverified app" screen once per account.
5. **Clients → Create client → Web application**. Under **Authorized redirect
   URIs** add exactly what `gswitch url` prints with `/oauth2callback` instead of
   `/mcp`, for example
   `https://your-machine.your-tailnet.ts.net/oauth2callback`. Create, then copy
   the Client ID and Client secret.

```bash
gswitch config     # paste Client ID + secret; stored at ~/.gswitch/config, mode 600
gswitch install    # writes the LaunchAgent and starts the server
```

### 4. Add the connector in ChatGPT — once per Google account

```bash
gswitch url        # prints and copies the connector URL
```

In ChatGPT (web): **Settings → Apps & Connectors → Advanced → Developer mode**,
then **Create connector**:

- Name: `Google (college)`
- MCP server URL: the copied URL
- Authentication: **OAuth**
- Complete the Google sign-in **as the college account**

Repeat with name `Google (personal)` if you ever want that account through
gswitch too — same URL, sign in as the personal account. The two entries stay
independent.

In a chat, enable the connector(s) under Tools. Write actions ask for
confirmation once per conversation.

## Daily use

Click **GSwitch** in the Dock for state and controls. Equivalents on the command
line: `gswitch status`, `gswitch start|stop|restart`, `gswitch url`,
`gswitch logs`, `gswitch doctor`.

The server runs under launchd and restarts itself, but the Mac must be awake for
ChatGPT to reach it — fine when you're using ChatGPT on this Mac, a problem if
you want it from your phone. If that becomes a real need, move the server to a
host that doesn't sleep; nothing else about the setup changes.

## Notes and known limits

- Runs on port **8765**; port 8000 is occupied by another local service on this
  Mac. `server_up()` matches the `workspace-mcp` service name, not just a 200,
  so a foreign app on the port can't be mistaken for this one.
- OAuth tokens live in `~/.gswitch/creds/`, the client secret in
  `~/.gswitch/config` (mode 600). Nothing leaves the machine.
- **College account risk:** universities frequently block unverified third-party
  OAuth apps. If step 4's sign-in returns "Access blocked: your admin has
  restricted access" or `admin_policy_enforced`, your school blocks this and no
  self-hosted server can get around it — the block is enforced on Google's side.
  The fallback is a second ChatGPT account signed in with the college Google
  login.
- Don't paste the connector URL anywhere but ChatGPT.

## Troubleshooting

```bash
gswitch doctor     # what's missing
gswitch logs 100   # recent server output
```

Server won't start: check `gswitch logs` for a Google OAuth error, usually a
redirect-URI mismatch — the URI in Google Cloud must match `gswitch url` exactly,
with `/oauth2callback` in place of `/mcp`.

Connector worked, then stopped after a week: the OAuth app is still in *Testing*.
Publish it (step 3.4).

## Other providers

See [EXTENSIONS.md](EXTENSIONS.md) for adding non-Google services.

[upstream]: https://github.com/taylorwilsdon/google_workspace_mcp
