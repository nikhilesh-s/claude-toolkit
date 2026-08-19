# gswitch

Use multiple Google accounts (personal + college) from one ChatGPT Plus account.
A self-hosted MCP server on this Mac holds OAuth tokens for each Google account;
ChatGPT connects to it once as a Developer-Mode connector. A Dock tile
(`GSwitch.app`) picks which account is "active" — every tool call reads the
active account at call time, so switching is instant and needs no reconnect.
Works with ChatGPT in any browser, including Dia.

Tools exposed to ChatGPT (all act on the active account):
`active_google_account`, `drive_search`, `drive_read_file`, `drive_create_doc`,
`drive_update_doc`, `gmail_search`, `gmail_read`, `gmail_send`, `gmail_draft`,
`calendar_list_events`, `calendar_create_event`.

## One-time setup

### 1. Google Cloud (~10 min, once — both accounts share it)

Do this signed in as **niksuravarjjala@gmail.com** at https://console.cloud.google.com :

1. Create project (name: `gswitch`).
2. **APIs & Services → Library**: enable **Gmail API**, **Google Drive API**,
   **Google Calendar API**.
3. **APIs & Services → OAuth consent screen**: External → app name `gswitch`,
   your email for both contact fields → scopes: skip (requested at runtime) →
   **Test users: add niksuravarjjala@gmail.com AND your college email** → save.
   Stay in "Testing" mode — no verification needed.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** →
   type **Desktop app** → download the JSON → save it as
   `~/.gswitch/client_secret.json`.

### 2. ngrok (free static domain)

1. Sign up free at https://dashboard.ngrok.com , install: `brew install ngrok`.
2. Run the `ngrok config add-authtoken ...` command the dashboard shows you.
3. Dashboard → **Domains** → claim your free static domain
   (looks like `something.ngrok-free.app`).
4. `echo "something.ngrok-free.app" > ~/.gswitch/ngrok_domain`

### 3. Install

```bash
cd ~/claude-toolkit/apps/gswitch && ./install.sh
```

Builds `GSwitch.app` (drag to Dock), installs the `gswitch` CLI, and — once
`~/.gswitch/ngrok_domain` exists — loads a LaunchAgent that keeps server+ngrok
running across reboots.

### 4. Add accounts

```bash
gswitch add
```

Browser opens → pick the Google account → approve (it will warn "Google hasn't
verified this app" — Continue; it's your own app). Repeat later for the college
account. **Probe the college account early**: if the university blocks
third-party OAuth, `add` fails at consent and no route exists around it.

### 5. Connect ChatGPT

```bash
gswitch url
```

In ChatGPT: **Settings → Apps & Connectors → Advanced → Developer mode** on,
then **Create connector**: name `gswitch`, MCP server URL = output of
`gswitch url`, Authentication = **No authentication**, trust checkbox → Create.
In a chat, enable the gswitch connector under Tools (Developer mode).

## Daily use

Click **GSwitch** in the Dock → pick account → done. ChatGPT's next tool call
uses that account. Ask ChatGPT "which google account is active?" to confirm.

CLI equivalents: `gswitch list`, `gswitch use <email>`.

## Security notes

- The connector uses **no auth + an unguessable secret URL path**
  (`/mcp-<32 hex>`, stored in `~/.gswitch/secret`, wrong path → 404).
  <!-- ponytail: secret-path auth; upgrade path = MCP OAuth on the server -->
  Don't paste the URL anywhere but ChatGPT's connector settings.
- OAuth tokens never leave this Mac (`~/.gswitch/accounts/`, mode 600).
- Mac asleep / ngrok down ⇒ connector offline in ChatGPT until it's back.
- ChatGPT asks for confirmation before every write tool (send mail, edit doc).

## Troubleshooting

- Log: `~/.gswitch/gswitch.log`. Restart:
  `launchctl kickstart -k gui/$(id -u)/com.nik.gswitch`
- "no active Google account" from ChatGPT → run `gswitch add`.
- New secret (leaked URL): delete `~/.gswitch/secret`, restart, re-run
  `gswitch url`, update the connector URL in ChatGPT.

## Other providers

See [EXTENSIONS.md](EXTENSIONS.md) for adding non-Google services
(Notion, GitHub, Microsoft 365, …) to the same switcher.
