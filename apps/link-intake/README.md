# Link Intake

Paste a URL, say where it goes and what you care about; get back a focused extraction and a lightweight
record in Google Docs. Raycast is the front end; `linkintake` is the CLI; Media Unlocker does media.

```
Raycast "Intake Link"  ──►  linkintake ingest  ──►  router ──► adapter ──► depth ──► extract ──► review
                                                   (class)   (context)   (flags)   (LLM)
                       ◄──  linkintake save    ◄──  local record + Intake Master row + destination export + cleanup
```

## Install (this Mac)

```bash
cd ~/claude-toolkit/apps/link-intake && ./setup.sh      # uv sync, ~/.local/bin/linkintake, Raycast deps, doctor
linkintake doctor
```

Raycast: `cd raycast && npm run dev` once (registers the dev extension), or Raycast → *Import Extension* →
pick `apps/link-intake/raycast`. The command is **Intake Link**. It reads the clipboard URL, remembers
the last destination, and calls the CLI at `~/.local/bin/linkintake` (changeable in the extension preferences).

## Auth

| What | Why | How |
|---|---|---|
| Claude login | extraction step (`claude -p`, your Claude Max plan) | `CLAUDE_CONFIG_DIR=~/.claude-nebula claude login`. No API key needed; `ANTHROPIC_API_KEY` is only an alternative. |
| Google | **not required for V1** | Records save locally with `export: {status: export_pending}`. A Claude session with a Google Drive connector runs `linkintake exports`, writes the rows/blocks, then `linkintake mark-exported <id>`. The stdlib REST exporter remains as an optional fallback (`google.export_mode=rest` + `google.creds_path`). |

## CLI

```bash
linkintake ingest <url> -d personal_ig -i "I like the cinematic wide shots and pacing near the beginning."
linkintake ingest <url> -d wishlist -i "identify this desk lamp" --save
linkintake save <id> [--force]         # pending record -> store + Google + cleanup
linkintake reprocess <id> -i "..."     # new instruction/destination, media cache reused
linkintake batch tests/urls.txt --save # URL | destination | instruction per line
linkintake exports                     # records awaiting Google export, as payloads for Claude
linkintake mark-exported <id> --master-url … --destination-url …
linkintake list | show <id> | doctor | config [--set k=v] | cleanup <id>
```

`--json` (before the subcommand) prints the record for Raycast / Claude / Codex.
Destinations: `wishlist` `supplement_ideas` `design_inspo` `scholarships` `personal_ig` `inbox`.

## What the review shows

First screen: short source summary, 4-6 takeaways, structured fields in the sidebar, confidence, an uncertainty
line. `⌘⇧D` opens the full result, frame-by-frame visual notes with approximate timestamps, source text and
technical metadata. Nothing is dropped; the record keeps all of it.

**Confidence** (0-1, shown as a percent) = how confident we are that the focused extraction accurately answers
the instruction from the evidence available. It is not inflated when only stills exist, the transcript is missing,
or the requested detail (cut timing, camera motion, audio) cannot be observed; those go in `uncertainty`.
Below 0.6, or when the model flags it, the record is `needs_review`.

**Frame timestamps** are approximate: Media Unlocker samples frames evenly across the video, and Link Intake
recomputes each frame's time from the media duration (ffprobe while the file is cached, else resolver metadata).
Limitation: Media Unlocker's `contact-sheet.jpg` currently contains only the first frame, so the 12 per-frame
JPEGs are sent instead; sub-second cuts, camera motion and audio cannot be observed from stills, and the model is
told to say so rather than guess.

## Record shape

`~/.link-intake/records/<id>.json` — `source{original_url, canonical_url, source_class, platform, title,
creator, published_at}`, `intent{destination, user_instruction}` (verbatim), `context{short_source_summary,
caption_or_text, transcript, visual_notes}`, `extraction{takeaways, focused_result, uncertainty, structured_data, confidence}`,
`artifacts{contact_sheet, media_unlocker_job_id, job_preexisting, frames[{file,t}]}`, `status ready|needs_review|failed`,
`export{master, destination}`, `duplicate_of[]`, `exact_duplicate`. `pending/` holds unsaved reviews,
`previews/` one compressed contact sheet per record, `index.jsonl` powers dedupe and `list`.

## Storage rules

- Save is local-first: `~/.link-intake/records/` is canonical; Google is a mirror written later.
- Media (MP4s, images, per-frame JPEGs) is cache. After a successful save, media of Media Unlocker jobs
  **created by this intake** is deleted; `manifest.json`, resolver `*.json` and `contact-sheet.jpg` stay.
  Jobs that already existed (the 10-Reel regression set) are never touched.
- Duplicate identity = canonical URL + destination + normalized instruction. Same Reel saved to two
  destinations with different notes is two records. Exact repeats need `--force`.

## Destinations

| Destination | Export | Extraction |
|---|---|---|
| Wishlist | staging block appended to the existing Wishlist doc's *Media Queue* tab (doc not restructured) | structured: product_item, brand, model, color_style, size_spec, price, notes — never invented |
| Supplement Ideas | doc *Supplemental Reel / Content Bank* | freeform, the idea you pointed at + why |
| Design Inspo | doc *Design Inspo Bank* | freeform, the visual concept |
| Scholarships | sheet *Scholarships Intake* (scholarship, organization, deadline, amount, eligibility, required materials, link, notes) | structured |
| Personal Instagram Inspiration | doc *Personal Instagram Inspiration* | takeaways + optional fields: format, key_shots, composition, lighting_color, editing_or_sequence, techniques_to_recreate, unknowns |
| Inbox / Unsorted | doc *Intake Inbox* | none (no LLM call), context preserved |

Every export also appends one row to **Intake Master** (Date · Destination · Source · Title/Creator ·
My Instruction · Extracted Result · Context/Summary · Status · Original URL). Exports happen from a Claude
session through its Drive connector (see `skills/link-intake/SKILL.md`); the CLI only prepares payloads.

## Tests

```bash
uv run python tests/test_router.py   # offline: canonical URLs, classes, dedupe, depth
tests/smoke_real.sh                  # the one E2E test: Reel -> personal_ig -> extract -> save (local, export pending)
tests/regression_reels.sh            # all 10 wishlist Reels as Wishlist intents (cache reused, nothing deleted)
```

Backlog: copy `tests/urls.example.txt` to `tests/urls.txt`, paste links, `linkintake batch tests/urls.txt`.

## Layout

```
linkintake/router.py        classify + canonicalize        linkintake/extract.py      LLM backends + schema
linkintake/adapters/        media_unlocker, video, web_page, google_workspace, direct_file
linkintake/depth.py         visual/transcript/research      linkintake/destinations.py exports
linkintake/pipeline.py      orchestration                   linkintake/google_api.py   stdlib REST client
linkintake/store.py         local records                   linkintake/cleanup.py      media cache cleanup
raycast/                    Raycast extension               ../../skills/link-intake/SKILL.md
```
