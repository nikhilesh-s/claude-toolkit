---
name: media-unlocker
description: Resolve public social-media URLs into locally cached media and contact sheets through the Media Unlocker MCP service.
---

# Media Unlocker

Use the Media Unlocker MCP for Instagram Reels and other supported public media URLs when visual inspection of the actual media is needed.

## MCP workflow

1. Call `unlock_media` with the URL. The local Claude default is `http://127.0.0.1:8770/mcp`; ChatGPT may use the existing Tailscale Funnel URL on HTTPS port 8443.
2. Read the returned `job_id` with `job_status` when metadata or resolver status is needed.
3. Call `get_contact_sheet` and inspect the returned image before making visual claims.

The service caches jobs under `~/.media-unlocker/jobs/`. Do not expose or commit cookies, browser databases, credentials, tokens, downloaded media, job files, or private connector hostnames.

## Instagram on this Mac

Dia is the authenticated browser source. Use Dia Chromium Profile 5 (`Nikhilesh`) only:

```text
chromium:/Users/niks/Library/Application Support/Dia/User Data/Profile 5
```

`yt-dlp` is the verified Instagram resolver and fallback. gallery-dl may report Dia cookie decryption failures; that is not a failure when yt-dlp resolves the URL and the contact sheet is created.

Do not scan other Dia profiles, switch to Safari or generic Chrome, ask for Instagram credentials, or retry Keychain operations in a loop. If a browser permission prompt appears, stop for user approval.

## Verification

The acceptance set is the 10 URLs in `apps/media-unlocker/test_wishlist_reels.sh`. Run tests serially and require a downloaded media file plus `preview/contact-sheet.jpg` for every pass. The service must keep its local port at 8770 and its optional Tailscale Funnel on 8443; do not disturb other services on port 443.

For setup or MCP registration, read `apps/media-unlocker/README.md` and use `apps/media-unlocker/setup_claude_mcp.sh` rather than editing Claude configuration files by hand.
