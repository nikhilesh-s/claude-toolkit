# Extending gswitch beyond Google

gswitch's switching mechanism is provider-agnostic. Three parts, only one is
Google-specific:

1. **Account store + active file** (`~/.gswitch/accounts/*.json`, `~/.gswitch/active`)
   — generic. Any credential blob keyed by an account name works.
2. **Dock picker** (`GSwitch.app`) — generic. It only lists filenames and writes
   the active file. A Notion or GitHub account added to the store shows up
   automatically.
3. **Tools in `gswitch.py`** — Google-specific. This is the only part a new
   provider adds.

## Recipe for a new provider (e.g. Notion, GitHub, Dropbox, Microsoft 365)

1. **Namespace the account files**: store non-Google accounts as
   `<provider>:<account>.json` (e.g. `github:nikhilesh-s.json`). The picker and
   `active` file need no changes.
2. **Auth**: whatever the provider uses — OAuth device flow, personal access
   token pasted into a `gswitch add-<provider>` subcommand, etc. Save the
   credential JSON in the accounts dir, chmod 600.
3. **Tools**: add `<provider>_search`, `<provider>_read`, … functions in
   `gswitch.py` decorated with `@tool`, each resolving credentials from the
   active account the same way `_creds()` does. If the active account isn't for
   that provider, return a clear error string ("active account is Google;
   switch to a GitHub account first") — same pattern as the missing-account
   error today.
4. **Scoping choice**: either one shared "active account" across all providers
   (current model — simplest, matches the Dock picker), or per-provider active
   files (`active-google`, `active-github`) if you want ChatGPT to use Google
   *and* GitHub in one chat. The second needs a small picker change (two-level
   menu).

## What stays hard regardless of provider

- ChatGPT still talks to ONE connector URL — new providers ride the same
  server, port, and secret path. No ChatGPT-side changes except nothing.
- Enterprise/school tenants (Microsoft 365, Slack) can block third-party OAuth
  exactly like Google Workspace can — probe with a real login before building.
- Rate limits and token refresh are per-provider homework.

## Ideas that fit this frame

- **Microsoft 365** (Outlook/OneDrive) via MSAL device-code flow — closest
  analog to the Google setup, including the college-tenant risk.
- **Notion / Linear / GitHub** via personal access tokens — no OAuth dance at
  all; `add-<provider>` just prompts for the token.
- **IMAP** for any non-Gmail mailbox — stdlib `imaplib`, credentials =
  host+user+app-password.
