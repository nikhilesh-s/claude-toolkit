# Media Unlocker

Local, self-hosted MCP connector for Claude, Claude Nebula, Codex, and ChatGPT that turns public social-media links into media an agent can actually inspect.

It is built for the College & Dorm Wishlist workflow: paste an Instagram Reel/TikTok/YouTube/X/Reddit/Vimeo/Loom/Pinterest/direct-media URL into ChatGPT, let the connector resolve the media, then return a contact sheet of representative frames for visual product identification.

## Supported clients

- **Claude default:** local MCP at `http://127.0.0.1:8770/mcp`.
- **Claude Nebula:** the same local MCP, registered in `~/.claude-nebula`.
- **Codex:** the canonical `skills/media-unlocker/SKILL.md` is linked by the toolkit skill installer.
- **ChatGPT:** the existing Tailscale Funnel exposes the MCP over HTTPS on port 8443.

Register the local MCP in both Claude profiles with the supported Claude CLI:

```bash
cd ~/claude-toolkit/apps/media-unlocker
bash setup_claude_mcp.sh
claude mcp list
CLAUDE_CONFIG_DIR="$HOME/.claude-nebula" claude mcp list
```

The helper is idempotent and uses only the local endpoint. Run it again after restoring a Mac or recreating either Claude profile.

## Resolver chain

1. **gallery-dl** first. It supports Instagram Reels and can reuse a logged-in browser session through browser cookies.
2. **yt-dlp** fallback. This is the verified Instagram resolver on Nik's Mac.
3. Optional **self-hosted Cobalt** fallback via `MEDIAUNLOCK_COBALT_URL`.
4. **FFmpeg** extracts representative frames and builds one contact sheet.

The public Cobalt API is deliberately **not** called: Cobalt's own API docs say hosted instances such as `api.cobalt.tools` are not intended for use by other projects without explicit permission. If you want Cobalt, self-host it and set the environment variable.

## Why this is better than a paid video app

- Free/open-source resolver stack.
- Media stays on your Mac.
- ChatGPT gets a visual preview instead of only a transcript.
- Instagram authentication comes from Dia Profile 5 (`Nikhilesh`) rather than storing an Instagram password.
- Works as a local Claude/Claude Nebula/Codex MCP workflow and as a ChatGPT custom MCP connector over the existing Tailscale pattern.

## Network layout

The local MCP server listens on `127.0.0.1:8770`.

Its public Tailscale Funnel uses HTTPS **8443** by default, so it does not overwrite another Funnel already using HTTPS 443. Tailscale officially allows Funnel on 443, 8443, and 10000.

The resulting connector URL is:

```text
https://<your-tailnet-hostname>:8443/mcp
```

Override the public port with `MEDIAUNLOCK_FUNNEL_PORT` if needed.

## Install on Nik's Mac

```bash
cd ~/claude-toolkit/apps/media-unlocker
bash setup.sh
mediaunlock doctor
bash setup_claude_mcp.sh
```

Then publish it through the existing Tailscale install:

```bash
mediaunlock funnel
mediaunlock url
```

In ChatGPT web, add the printed `/mcp` URL as a custom connector named **Media Unlocker**. Keep the connector URL private.

## Wishlist Reel regression set

The 10 URLs in `test_wishlist_reels.sh` are the current real-world acceptance tests for the College & Dorm Wishlist flow. The verified run passed all 10 serially with yt-dlp and created all 10 contact sheets. The script is the authoritative URL manifest; keep its order and do not substitute other profiles or browsers.

Test all 10 at once:

```bash
cd ~/claude-toolkit/apps/media-unlocker
chmod +x test_wishlist_reels.sh
./test_wishlist_reels.sh
```

Do not switch to Safari, generic Chrome, or another Dia profile. If macOS blocks browser-cookie access, stop and ask the user to approve the exact permission; do not export cookies or commit browser data, tokens, or account credentials.

## MCP tools

### `unlock_media(url, browser='safari', refresh=false)`
Downloads/resolves the media, caches it under `~/.media-unlocker/jobs/<job_id>/`, extracts metadata, and builds a preview. Returns a `job_id`.

### `get_contact_sheet(job_id)`
Returns one image containing representative frames from the video (or the still image itself). This is the tool ChatGPT should visually inspect to identify the product, color, model, text overlays, etc.

### `job_status(job_id)`
Returns cached resolver metadata.

## Intended ChatGPT instruction

Add this to the wishlist workflow instructions:

> When I send a social-media or media URL for the College & Dorm Wishlist, use Media Unlocker first. Call `unlock_media`, then inspect `get_contact_sheet`. Identify only what the media supports. If the exact product/model is uncertain, search the web using visible brand/model clues. Then update the College & Dorm Wish List Google Doc, preserving the original media URL as the source link.

## Known compatibility checkpoint

The Python MCP SDK has an open 2026 issue involving image tool results in **stateless** Streamable HTTP mode. The current connector deliberately keeps the first implementation simple so the real ChatGPT client can be tested on your Mac. If `get_contact_sheet` is the only failing step while text tools work, the resolver itself is fine; the next patch should switch the image-return layer rather than changing gallery-dl/FFmpeg.

This is why the branch should be tested before merging into the main toolkit branch.

## Security / limits

- Only public `http`/`https` URLs are accepted; localhost/private-network targets are rejected.
- Downloads are stored locally under `~/.media-unlocker`.
- Private/login-only posts work only if your browser session has access and gallery-dl can read those cookies.
- DRM-protected media is not bypassed.
- Default media cap is 250 MB (`MEDIAUNLOCK_MAX_MEDIA_MB`).
- The Mac must be awake and Tailscale connected for ChatGPT to reach the server.
