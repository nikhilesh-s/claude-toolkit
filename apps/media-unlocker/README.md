# Media Unlocker

Local, self-hosted MCP connector for ChatGPT that turns public social-media links into media ChatGPT can actually inspect.

It is built for the College & Dorm Wishlist workflow: paste an Instagram Reel/TikTok/YouTube/X/Reddit/Vimeo/Loom/Pinterest/direct-media URL into ChatGPT, let the connector resolve the media, then return a contact sheet of representative frames for visual product identification.

## Resolver chain

1. **gallery-dl** first. It supports Instagram Reels and can reuse a logged-in browser session through browser cookies.
2. **yt-dlp** fallback.
3. Optional **self-hosted Cobalt** fallback via `MEDIAUNLOCK_COBALT_URL`.
4. **FFmpeg** extracts representative frames and builds one contact sheet.

The public Cobalt API is deliberately **not** called: Cobalt's own API docs say hosted instances such as `api.cobalt.tools` are not intended for use by other projects without explicit permission. If you want Cobalt, self-host it and set the environment variable.

## Why this is better than a paid video app

- Free/open-source resolver stack.
- Media stays on your Mac.
- ChatGPT gets a visual preview instead of only a transcript.
- Instagram authentication can come from Safari/Chrome browser cookies rather than storing your Instagram password.
- Works as a normal ChatGPT custom MCP connector over the same Tailscale pattern already used by your local connectors.

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
```

Then publish it through the existing Tailscale install:

```bash
mediaunlock funnel
mediaunlock url
```

In ChatGPT web, add the printed `/mcp` URL as a custom connector named **Media Unlocker**. Keep the connector URL private.

## Test the Instagram Reel from the wishlist chat

```bash
mediaunlock test 'https://www.instagram.com/reel/DalkeLOBAmg/?igsi=NTc4MTIwNjQ2YQ=='
```

If Safari is not the browser where Instagram is logged in:

```bash
MEDIAUNLOCK_BROWSER=chrome mediaunlock test 'https://www.instagram.com/reel/DalkeLOBAmg/?igsi=NTc4MTIwNjQ2YQ=='
```

If macOS blocks browser-cookie access, grant the terminal/agent Full Disk Access or export an Instagram cookies file and adapt the gallery-dl invocation. Do **not** commit cookies, tokens, or account credentials to this repo.

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
