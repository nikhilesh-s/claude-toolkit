# Media Unlocker

Local, self-hosted MCP connector for ChatGPT that turns public social-media links into media ChatGPT can actually inspect.

It is built for the College & Dorm Wishlist workflow: paste an Instagram Reel/TikTok/YouTube/X/Reddit/Vimeo/Loom/Pinterest/direct-media URL into ChatGPT, let the connector resolve the media, then return a contact sheet of representative frames for visual product identification.

## Resolver chain

1. **gallery-dl** first (best broad social-media coverage; uses your logged-in browser cookies for Instagram).
2. **yt-dlp** fallback.
3. Optional **self-hosted Cobalt** fallback via `MEDIAUNLOCK_COBALT_URL`.
4. **FFmpeg** extracts representative frames and builds one contact sheet.

The public Cobalt API is deliberately **not** called: Cobalt's own API docs say hosted instances such as `api.cobalt.tools` are not intended for use by other projects without explicit permission. If you want Cobalt, self-host it and set the environment variable.

## Why this is better than a paid video app

- Free/open-source resolver stack.
- Media stays on your Mac.
- ChatGPT gets a visual preview instead of only a transcript.
- Instagram authentication can come from Safari/Chrome browser cookies rather than storing your Instagram password.
- Works as a normal ChatGPT Developer Mode custom connector over the same Tailscale Funnel pattern already used by `gswitch`.

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

In ChatGPT web: Developer mode → Plugins → `+` → Server URL → paste the `/mcp` URL. Name it **Media Unlocker**. No OAuth is needed because this server is yours; keep the connector URL private.

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

## Security / limits

- Only public `http`/`https` URLs are accepted; localhost/private-network targets are rejected.
- Downloads are stored locally under `~/.media-unlocker`.
- Private/login-only posts work only if your browser session has access and gallery-dl can read those cookies.
- DRM-protected media is not bypassed.
- Default media cap is 250 MB (`MEDIAUNLOCK_MAX_MEDIA_MB`).
- The Mac must be awake and Tailscale connected for ChatGPT to reach the server.
