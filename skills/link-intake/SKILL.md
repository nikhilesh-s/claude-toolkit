---
name: link-intake
description: Ingest almost any URL (Reel, TikTok, YouTube, article, PDF, Google Doc) with a destination and a one-line instruction, extract only what Nik cares about, and export a lightweight record to the Intake Master Google Doc plus a destination bank. Wraps Media Unlocker; never stores whole media.
---

# Link Intake

Use this skill when Nik pastes a link and says where it should go and what matters about it, or asks to
process a backlog of links. The implementation is code in `apps/link-intake/`; this file only tells you
how to drive it. Do not re-implement classification, media resolution, extraction, or Google writes here.

## The one command

```bash
linkintake ingest <url> --dest <destination> --instruction "<10-15 words>"        # review only
linkintake ingest <url> --dest <destination> --instruction "<...>" --save         # review + save + export
linkintake save <record-id> [--force]                                             # save a reviewed record
linkintake reprocess <record-id> [--instruction "..."] [--dest ...]
linkintake batch tests/urls.txt [--save]      # lines: URL | destination | instruction
linkintake sync [id] | sync-status [id] | google-auth | google-setup
linkintake list | show <id> | doctor | config
```

Add `--json` before the subcommand for machine-readable output. Destinations: `wishlist`,
`supplement_ideas`, `design_inspo`, `scholarships`, `personal_ig` (Personal Instagram Inspiration), `inbox`.

## What it does (so you can explain or debug it)

1. **Router** canonicalizes the URL (strips tracking params, normalizes youtu.be/shorts, etc.) and assigns a
   source class: `google_workspace | social_media | video | web_page | direct_file | unknown`. Platform is metadata.
2. **Adapter** builds context: social/direct media via the existing Media Unlocker MCP
   (`unlock_media` → `job_status` → `get_contact_sheet`, see `skills/media-unlocker/SKILL.md`); video via
   yt-dlp metadata + subtitles (no download) plus a contact sheet when visuals matter; web pages via a plain
   fetch; Google Docs/Sheets/Slides via the Google API; PDFs are passed to the model as documents.
3. **Depth** is inferred from source + destination + instruction (visual? transcript? product research?).
   Not exposed in the UI.
4. **Extraction** is one structured-output model call through the `claude` CLI (your Claude login; the
   Anthropic SDK is used instead only if `ANTHROPIC_API_KEY` is set). The instruction is preserved verbatim.
   Output: short summary, 4-6 takeaways (first screen), full focused result, uncertainty, frame-by-frame visual
   notes with approximate timestamps, structured fields (Wishlist/Scholarships schemas; optional shooting fields
   for Personal Instagram Inspiration), and confidence = how well the evidence supports the answer. Stills-only
   evidence must not produce pacing or camera-motion claims; those land in `uncertainty`.
5. **Save** = local canonical record in `~/.link-intake/records/` (always, first), media cleanup of jobs this
   intake created, then Google sync: one row in the **Intake Master** doc, then the destination write
   (Wishlist → *Intake Staging* tab of the existing Wishlist doc; Supplement/Design/Instagram → entry appended to
   their bank docs; Scholarships → *Scholarship Tracker* sheet), then a bounded retry of older pending records.
   Google failures never fail a save; they set `export.status` to `partial`/`export_pending` with the error.
6. **Google is a direct REST client with the personal account's token** (`~/.link-intake/google/`), set up once
   by `linkintake google-auth` + `google-setup`. Never read gswitch, workspace-mcp, or the Funnel. Every remote
   entry carries the Record ID and is checked before appending, so `linkintake sync` is always safe to re-run.
7. **Duplicates, three layers.** Idempotency (Record ID: retries never write twice); exact intake (URL +
   destination + instruction: needs `--force`); semantic entity (Wishlist product / Scholarship cycle: `created`,
   `merged`, or `possible_duplicate`). Master Intake keeps every intake. A `possible_duplicate` writes nothing to
   Google until `linkintake resolve <id> --merge|--new`. Supplement/Design/Instagram never merge.
8. **Did it save?** `linkintake list` (or Raycast → Intake History) is local-first truth: saved time, sync
   status per part, resolution action, last error.

## Bulk ingest ("Use Link Intake to process my saved links")

Same pipeline, three commands, dry-run by default. Sources are read only (AppleScript `get` only; Reminders and
Notes are never edited, completed, deleted or moved).

```bash
linkintake bulk scan [--sources reminders,notes,manifest,file:<path>] [--lists "00 Inbox,Wishlist"] [--include-completed] [--notes-limit N]
linkintake bulk review                       # list candidates needing a decision
linkintake bulk review --approve c003 c007   # or: --dest c003 wishlist  |  --instruction c003 "…"  |  --skip c009  |  --approve-all [--origin manifest]
linkintake bulk run                          # dry-run preview of what would be processed
linkintake bulk run --execute [--limit N] [--delay 2]   # sequential, resumable, never stops on a failed item
linkintake bulk status
```

How to run it as Claude:
1. `bulk scan` and read the summary: found / already ingested / ready / review / invalid. Show Nik the review
   candidates (URL, source list or note, surrounding text, destination guess with confidence, proposed
   instruction, reason).
2. Never guess for a review item: ask Nik, then apply `bulk review --dest/--instruction/--approve/--skip`.
3. `bulk run` (dry-run) and show the list; only after Nik approves, `bulk run --execute`.
4. Report processed / saved / merged / possible duplicates / already ingested / failed / Google pending / skipped,
   and point at `linkintake list` (History shows bulk run id and source).

Inference rules live in `linkintake/bulk.py`: list/folder name is the strongest signal, then the wording next to
the URL, then a generic instruction (which alone is never enough to auto-run). Both destination and intent
confidence must be >= 0.80 to be `ready`. The same URL with different nearby wording becomes separate candidates
(different intents); identical wording from several places collapses into one candidate with provenance. Exact
existing intakes are marked `existing`; a same-URL, same-destination, new-instruction candidate goes to review.

## Rules

- Never edit `apps/media-unlocker/test_wishlist_reels.sh`; it is the Reel regression manifest (bulk `manifest` source reads it).
- Never run `bulk run --execute` on the full backlog without Nik's explicit approval of the dry-run.
- Never commit cookies, tokens, downloaded media, `~/.link-intake`, `~/.media-unlocker`, or connector hostnames.
- If `linkintake doctor` shows no working LLM backend, tell Nik the fix is
  `CLAUDE_CONFIG_DIR=~/.claude-nebula claude login` and stop; do not fabricate an extraction. Records still
  save locally with `status: needs_review`.
- The Wishlist doc is not restructured: only its Media Queue tab receives staging blocks.
- Prefer reprocessing with a sharper instruction over hand-editing exported docs.

## Raycast

`apps/link-intake/raycast/` is the human front end ("Intake Link"). It calls the same CLI; keep them in sync.
