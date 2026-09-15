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

## Auth (one time)

| What | Why | How |
|---|---|---|
| Claude login | extraction (`claude -p`, your Claude Max plan) | `CLAUDE_CONFIG_DIR=~/.claude-nebula claude login` |
| Google, personal account | Google Docs/Sheets export on every Save | `linkintake google-auth` (Desktop OAuth client, loopback on port 8792, refuses `.edu` accounts) then `linkintake google-setup` (pick/create the destination docs, folders and sheet; exact IDs persisted) |

Files: `~/.link-intake/google/client.json` (OAuth client id/secret) and `token.json` (refresh token), both mode 600.
Nothing reads gswitch, workspace-mcp or the Tailscale Funnel; the gswitch Cloud project is reused only as the
OAuth app registration.

## Sync behaviour

Save = (1) local canonical record committed, (2) Master Intake row, (3) destination write, (4) a bounded sweep
of older pending records. Google failures never fail the save: `export.status` becomes `partial` or
`export_pending` with the exact error, and the next successful save or `linkintake sync` retries oldest first.
Every remote row/entry carries the Record ID and is checked before appending, so retries cannot duplicate.
Per record: `export.master_sync` and `export.destination_sync` each track status, remote file id/ref,
last_attempt, last_error, synced_at. Google calls time out at 15 s each.

## CLI

```bash
linkintake ingest <url> -d personal_ig -i "I like the cinematic wide shots and pacing near the beginning."
linkintake ingest <url> -d wishlist -i "identify this desk lamp" --save
linkintake save <id> [--force]         # pending record -> store + Google + cleanup
linkintake reprocess <id> -i "..."     # new instruction/destination, media cache reused
linkintake batch tests/urls.txt --save # URL | destination | instruction per line
linkintake sync [id]                   # retry pending/partial Google exports (oldest first, bounded)
linkintake sync-status [id]            # Google auth state, pending records, last errors
linkintake resolve <id> --merge|--new  # decide a possible duplicate, then sync
linkintake entities wishlist|scholarships
linkintake list                        # history (also the Raycast Intake History command)
linkintake google-auth | google-setup  # one time
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

## Duplicates: three different things

| Layer | Identity | Behaviour |
|---|---|---|
| Idempotency | Record ID | a retry never writes the same record twice remotely (row/entry checked for the id first) |
| Exact intake | canonical URL + destination + normalized instruction | blocked unless you confirm (`--force` / Save Anyway) |
| Semantic entity | Wishlist: product; Scholarships: organization + program + cycle year | `created` / `merged` / `possible_duplicate` (`~/.link-intake/entities/`) |

Master Intake is an audit log: every intake keeps its own row even when several intakes merge into one Wishlist
or Scholarship row. Supplement Ideas, Design Inspo and Personal Instagram are never semantically deduplicated.

**Wishlist rule.** Match order: identifier (ASIN/SKU/model no.) → official product URL → brand + model
(+ variant) → same brand + similar name = `possible_duplicate` (never auto-merged). Variant (color/size/
wattage) is part of identity: same line, different variant = a separate row linked by `product_group`; a record
with no variant enriches the single existing line, or asks when several variants exist. Merges keep every source
URL and Record ID, replace a value only with a more specific or higher-confidence one, never with "TBD"/unknown,
and log price observations with date and source.

**Scholarship rule.** Same organization + program + cycle year = merge (later/official source updates deadline,
amount, eligibility in place, with per-field provenance). Different year = separate row. Year unknown on one
side, or same organization with a similar program name = `possible_duplicate`.

`possible_duplicate` writes nothing to Google until you decide: `linkintake resolve <id> --merge|--new`, or
the Merge into Existing / Keep as Separate Item actions in Raycast. History shows it as "review".

## Destinations (fixed)

| Destination | Where | Format |
|---|---|---|
| Master Intake | doc *Intake Master* (every save) | table: Date, Destination, Source, Title / Creator, User Instruction, Extracted Insight, Tags, Status, URL, Record ID |
| Wishlist | your existing Wishlist doc, new tab *Intake Staging* only | table: Date Added, Item, Brand, Model, Variant / Color / Size, Price, Why I Saved It, Notes, Source, Record ID (blank when unsupported) |
| Supplement Ideas | doc *Supplement Inspiration Bank* in College Applications | entry: Date, Record ID, Source, What I liked, Idea, Context, Tags (Personal Statement, Why Major, …), URL |
| Design Inspo | doc *Design Inspiration Bank* in Media | entry: Date, Record ID, Tags, Instruction, What stood out, Reusable ideas, Visual notes, Source |
| Personal Instagram Inspiration | doc *Personal Instagram Inspiration* | entry: Date, Record ID, Instruction, Summary, Takeaways, Shots, Lighting, Transitions, Pacing, Hooks, Techniques, Unknowns, Source |
| Scholarships | sheet *Scholarship Tracker* in College Applications / Scholarships | row: Scholarship, Organization, Amount, Deadline, Eligibility, Required Materials, Application Link, Status, Priority, Notes, Source, Date Added, Record ID (needs Sheets API enabled; pending until then) |
| Inbox | Master Intake only | |

## Tests

```bash
uv run python tests/test_router.py   # offline: canonical URLs, classes, dedupe, depth
uv run python tests/test_sync.py     # offline: idempotency, partial, pending retry, remote merge, needs_decision
uv run python tests/test_entities.py # offline: wishlist/scholarship merge matrix
uv run python tests/test_history.py  # offline: history rows, re-save refused
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
