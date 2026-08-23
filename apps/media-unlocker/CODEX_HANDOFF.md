# Codex handoff — Media Unlocker

You are the low-cost implementation/runtime-debugging executor for this task. The architecture is already decided. Do not redesign it unless a concrete local failure proves a component cannot work.

## Model / token policy

Use the cheapest capable execution model available. Prefer **Sol Light** first. If it cannot complete a concrete step or repeatedly fails, escalate only that step to **Luna High**. Do not spend tokens on broad repo exploration, product research, architectural brainstorming, or verbose explanations.

ChatGPT is handling the intelligence-heavy work: architecture, diagnosis, product identification, wishlist semantics, and final decisions. Your job is mechanical execution, local testing, and minimal code fixes.

## Repo / branch

Repo: `~/claude-toolkit`
Branch: `feat/media-unlocker`
App: `apps/media-unlocker`
PR: #1

Do not merge the PR. Do not touch unrelated files. Do not inspect the whole repo unless a command fails because of an unknown repo-level dependency.

Start with exactly:

```bash
cd ~/claude-toolkit
git fetch origin
git switch feat/media-unlocker
git pull --ff-only origin feat/media-unlocker
cd apps/media-unlocker
```

## Goal

Get Media Unlocker working end-to-end on Nik's Mac so ChatGPT can receive a social-media URL, resolve the media locally, and inspect representative frames.

Existing intended pipeline:

1. `gallery-dl` first, with logged-in browser cookies for Instagram.
2. `yt-dlp` fallback.
3. optional self-hosted Cobalt fallback only if configured.
4. FFmpeg extracts frames and builds a contact sheet.
5. local MCP server exposes `unlock_media`, `get_contact_sheet`, and `job_status`.
6. Tailscale Funnel exposes the MCP endpoint on HTTPS port 8443.

Do not replace this stack just because another library exists.

## Real acceptance URLs

All four must be treated as regression cases:

```text
https://www.instagram.com/reel/DalkeLOBAmg/?igsi=NTc4MTIwNjQ2YQ==
https://www.instagram.com/reel/DbHRk63PlaC/?igsi=NTc4MTIwNjQ2YQ==
https://www.instagram.com/reel/DaVOALgzEMc/?igsi=NTc4MTIwNjQ2YQ==
https://www.instagram.com/reel/Dbb3EHnvOXg/?igsi=NTc4MTIwNjQ2YQ==
```

## Execution order

Run:

```bash
bash setup.sh
mediaunlock doctor
chmod +x test_wishlist_reels.sh
./test_wishlist_reels.sh
```

If Safari cookie access fails, try only this fallback next:

```bash
MEDIAUNLOCK_BROWSER=chrome ./test_wishlist_reels.sh
```

Do not ask Nik to paste Instagram credentials. Do not commit cookies, tokens, browser data, generated media, or secrets.

### If the resolver works

Then run the actual MCP service and exercise the pipeline locally. Use the existing CLI/server code rather than inventing a separate test harness unless needed.

Verify:

- `unlock_media` succeeds for at least one real Reel.
- downloaded media exists under `~/.media-unlocker/jobs/...`.
- FFmpeg creates `preview/contact-sheet.jpg`.
- `job_status` returns useful metadata.
- `get_contact_sheet` works over the actual MCP transport if possible.

Then run:

```bash
mediaunlock funnel
mediaunlock url
```

Confirm the printed connector URL uses `:8443/mcp` and does not disturb any existing Funnel on 443.

### If MCP image return fails but media/contact-sheet generation works

Do **not** rewrite the resolver. Isolate the failure to the image transport. Make the smallest possible compatibility fix that lets ChatGPT retrieve the contact sheet. Preserve the existing tool names if practical.

### If Instagram resolution fails

Capture the exact `gallery-dl` and `yt-dlp` errors. Check, in this order only:

1. whether the selected browser is actually logged into Instagram,
2. whether browser-cookie access is blocked by macOS permissions,
3. current installed `gallery-dl` / `yt-dlp` versions,
4. whether the Reel resolves with the alternate logged-in browser,
5. whether a minimal tool upgrade fixes it.

Do not add Selenium/Playwright/browser automation unless both existing resolvers demonstrably cannot access the Reels with valid cookies.

## Code-change rules

- Make minimal changes only in `apps/media-unlocker/` unless absolutely necessary.
- Preserve current security checks against localhost/private-network URL targets.
- Preserve the media size cap.
- Do not use Cobalt's public hosted API.
- Do not change ports used by existing apps.
- Run `python -m py_compile server.py` and shell syntax checks after edits.
- Run the existing smoke test and the real Reel regression script after edits.
- Commit each coherent fix to `feat/media-unlocker` with a short descriptive message.
- Never merge PR #1.

## Reporting format — keep it short

When done, return only:

1. **Result:** working / partially working / blocked.
2. **What passed:** concise list.
3. **Exact blocker:** if any, include the relevant error text.
4. **Files changed + commit SHA(s).**
5. **One next action for ChatGPT/Nik**, only if needed.

Do not write a long retrospective. Do not research what the products in the Reels are. ChatGPT will do that after the media pipeline works.
